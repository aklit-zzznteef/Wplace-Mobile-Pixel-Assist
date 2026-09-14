"""Local, review-first ADB pixel queue assistant for Pixel Mobile Assist.

The UI is served only on 127.0.0.1 and opens in the user's normal browser.
Pixel Mobile Assist captures the phone, detects sampled mini-square markers, previews
all proposed taps, and queues only approved positions.  It never presses Paint.
"""

from __future__ import annotations

import argparse
import io
import json
import random
import secrets
import shutil
import socket
import subprocess
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from PIL import Image, ImageDraw

from detector import (
    Component,
    find_coloured_markers,
    offset_components,
    track_template_point,
)


APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
UI_PATH = APP_DIR / "ui.html"

class LocalHTTPServer(ThreadingHTTPServer):
    """Loopback server that refuses a second listener on the same port."""

    allow_reuse_address = False

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def find_adb(explicit: str | None = None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    if CONFIG_PATH.exists():
        try:
            configured = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if configured.get("adb_path"):
                candidates.append(Path(configured["adb_path"]).expanduser())
        except (OSError, json.JSONDecodeError):
            pass
    on_path = shutil.which("adb")
    if on_path:
        candidates.append(Path(on_path))
    downloads = Path.home() / "Downloads"
    if downloads.exists():
        candidates.extend(downloads.glob("scrcpy*/**/adb.exe"))
        candidates.extend(downloads.glob("**/scrcpy*/adb.exe"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "Could not find adb.exe. Start with --adb C:\\path\\to\\scrcpy\\adb.exe"
    )


class AdbClient:
    def __init__(self, adb_path: Path, serial: str | None = None) -> None:
        self.adb_path = adb_path
        self.serial = serial or self._first_device()

    def _base(self) -> list[str]:
        command = [str(self.adb_path)]
        if self.serial:
            command.extend(["-s", self.serial])
        return command

    def _first_device(self) -> str:
        result = subprocess.run(
            [str(self.adb_path), "devices"],
            check=True,
            capture_output=True,
            text=True,
            timeout=8,
        )
        devices = [
            line.split()[0]
            for line in result.stdout.splitlines()[1:]
            if line.strip().endswith("\tdevice")
        ]
        if not devices:
            raise RuntimeError("No authorized Android device is visible to ADB")
        return devices[0]

    def screenshot(self) -> Image.Image:
        result = subprocess.run(
            self._base() + ["exec-out", "screencap", "-p"],
            check=True,
            capture_output=True,
            timeout=15,
        )
        return Image.open(io.BytesIO(result.stdout)).convert("RGB")

    def tap(self, x: int, y: int) -> None:
        subprocess.run(
            self._base() + ["shell", "input", "tap", str(x), str(y)],
            check=True,
            capture_output=True,
            timeout=8,
        )

    def press(self, x: int, y: int, duration_ms: int = 45) -> None:
        """Send a human-like short press without adding queue sleep time."""
        subprocess.run(
            self._base()
            + [
                "shell",
                "input",
                "swipe",
                str(x),
                str(y),
                str(x),
                str(y),
                str(duration_ms),
            ],
            check=True,
            capture_output=True,
            timeout=8,
        )

class AppState:
    def __init__(self, adb: AdbClient) -> None:
        self.adb = adb
        self.lock = threading.RLock()
        self.image: Image.Image | None = None
        self.image_version = 0
        self.roi: tuple[int, int, int, int] | None = None
        self.markers: list[Component] = []
        self.marker_colours: list[tuple[int, int, int]] = []
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.queue_status: dict[str, Any] = {
            "state": "idle",
            "completed": 0,
            "total": 0,
            "message": "Ready",
        }

    def capture(self) -> dict[str, Any]:
        image = self.adb.screenshot()
        with self.lock:
            if self.worker and self.worker.is_alive():
                raise RuntimeError("Stop the active queue before taking a new capture")
            self.image = image
            self.image_version += 1
            self.roi = None
            self.markers = []
            self.marker_colours = []
            self.queue_status = {
                "state": "idle",
                "completed": 0,
                "total": 0,
                "message": "New screen captured",
            }
            version = self.image_version
        return {"width": image.width, "height": image.height, "version": version}

    def screen_png(self) -> bytes:
        with self.lock:
            if self.image is None:
                raise RuntimeError("Capture the phone screen first")
            output = io.BytesIO()
            self.image.save(output, format="PNG")
            return output.getvalue()

    def detect_mixed(self, payload: dict[str, Any]) -> dict[str, Any]:
        roi_values = payload.get("roi")
        sample_values = payload.get("sample")
        colour_values = payload.get("colours")
        tolerance = int(payload.get("tolerance", 5))
        if not isinstance(roi_values, list) or len(roi_values) != 4:
            raise ValueError("roi must contain four coordinates")
        if not isinstance(sample_values, list) or len(sample_values) != 2:
            raise ValueError("sample must contain two coordinates")
        if not isinstance(colour_values, list) or not colour_values:
            raise ValueError("Select at least one unlocked account colour")
        if len(colour_values) > 128:
            raise ValueError("Too many account colours")
        colours: list[tuple[int, int, int]] = []
        for value in colour_values:
            if not isinstance(value, list) or len(value) != 3:
                raise ValueError("Each account colour must contain RGB values")
            rgb = tuple(int(channel) for channel in value)
            if any(channel < 0 or channel > 255 for channel in rgb):
                raise ValueError("Account colour channels must be between 0 and 255")
            colours.append(rgb)  # type: ignore[arg-type]

        with self.lock:
            if self.image is None:
                raise RuntimeError("Capture the phone screen first")
            image = self.image.copy()
        left, top, right, bottom = map(int, roi_values)
        left = max(0, min(image.width - 1, left))
        top = max(0, min(image.height - 1, top))
        right = max(left + 1, min(image.width, right))
        bottom = max(top + 1, min(image.height, bottom))
        sample_x, sample_y = map(int, sample_values)
        if not (left <= sample_x < right and top <= sample_y < bottom):
            raise ValueError("The sampled marker must be inside the canvas region")
        tolerance = max(0, min(40, tolerance))

        crop = image.crop((left, top, right, bottom))
        region_mask = None
        polygon = payload.get("polygon")
        if polygon is not None:
            if not isinstance(polygon, list) or not 3 <= len(polygon) <= 200:
                raise ValueError("Region needs 3 to 200 corners")
            points = []
            for point in polygon:
                if not isinstance(point, list) or len(point) != 2:
                    raise ValueError("Each region corner needs two coordinates")
                x, y = map(int, point)
                if not (0 <= x <= image.width and 0 <= y <= image.height):
                    raise ValueError("Region corner is outside the screen")
                points.append((x - left, y - top))
            region_mask = Image.new("L", crop.size, 0)
            ImageDraw.Draw(region_mask).polygon(points, fill=255)
            if not region_mask.getpixel((sample_x - left, sample_y - top)):
                raise ValueError("Sample inside the selected region")
        max_marker_dimension = max(24, min(crop.width, crop.height) // 20)
        nearby_search_radius = max(32, min(crop.width, crop.height) // 18)
        sample, local_markers = find_coloured_markers(
            crop,
            (sample_x - left, sample_y - top),
            colours,
            tolerance=tolerance,
            max_sample_dimension=max_marker_dimension,
            nearby_search_radius=nearby_search_radius,
        )
        max_sample_width = max(24, crop.width // 10)
        max_sample_height = max(24, crop.height // 10)
        max_sample_area = max(576, (crop.width * crop.height) // 100)
        if (
            sample.width > max_sample_width
            or sample.height > max_sample_height
            or sample.area > max_sample_area
        ):
            raise ValueError(
                f"The sampled area is {sample.width}x{sample.height}, much too large for a "
                "mini-square. Click the solid interior of one small marker."
            )

        markers: list[Component] = []
        marker_colours: list[tuple[int, int, int]] = []
        response_markers: list[dict[str, Any]] = []
        for item in local_markers:
            if region_mask is not None:
                c = item.component
                if region_mask.crop((c.left, c.top, c.right + 1, c.bottom + 1)).getextrema()[0] != 255:
                    continue
            component = offset_components([item.component], left, top)[0]
            markers.append(component)
            marker_colours.append(item.rgb)
            response_markers.append(
                {
                    "bounds": [component.left, component.top, component.right, component.bottom],
                    "center": list(component.center),
                    "area": component.area,
                    "rgb": list(item.rgb),
                }
            )
        with self.lock:
            self.roi = (left, top, right, bottom)
            self.markers = markers
            self.marker_colours = marker_colours
        return {
            "sampleSize": [sample.width, sample.height, sample.area],
            "markers": response_markers,
            "colourCounts": {
                ",".join(map(str, rgb)): marker_colours.count(rgb)
                for rgb in sorted(set(marker_colours))
            },
        }

    def start_mixed_queue(self, payload: dict[str, Any]) -> dict[str, Any]:
        indices = payload.get("indices")
        eyedropper = payload.get("eyedropper")
        minimum = float(payload.get("minDelay", 0.01))
        maximum = float(payload.get("maxDelay", 0.08))
        if not isinstance(indices, list) or not all(isinstance(i, int) for i in indices):
            raise ValueError("indices must be a list of marker numbers")
        if not isinstance(eyedropper, list) or len(eyedropper) != 2:
            raise ValueError("Calibrate the eyedropper button before starting a mixed queue")
        picker_x, picker_y = map(int, eyedropper)
        picker_point = (picker_x, picker_y)
        minimum = max(0.01, min(5.0, minimum))
        maximum = max(minimum, min(5.0, maximum))

        with self.lock:
            if self.worker and self.worker.is_alive():
                raise RuntimeError("A tap queue is already running")
            if self.image is None:
                raise RuntimeError("Capture the phone screen first")
            if picker_point is not None and not (
                0 <= picker_point[0] < self.image.width
                and 0 <= picker_point[1] < self.image.height
            ):
                raise ValueError("Eyedropper coordinate is outside the phone screen")
            if len(set(indices)) != len(indices):
                raise ValueError("Duplicate marker indices are not allowed")
            if any(index < 0 or index >= len(self.markers) for index in indices):
                raise ValueError("A marker index is outside the reviewed mixed detection set")
            tasks = [
                (self.markers[index].center, self.marker_colours[index])
                for index in indices
            ]
            if not tasks:
                raise ValueError("No reviewed pixels were selected")
            reference_image = self.image.copy()
            self.stop_event.clear()
            self.queue_status = {
                "state": "running",
                "completed": 0,
                "total": len(tasks),
                "message": "Grouped mixed queue started; Paint will not be pressed",
            }
            self.worker = threading.Thread(
                target=self._mixed_grouped_queue_worker,
                args=(tasks, picker_point, reference_image, minimum, maximum),
                daemon=True,
            )
            self.worker.start()
        return dict(self.queue_status)

    def _mixed_grouped_queue_worker(
        self,
        tasks: list[tuple[tuple[int, int], tuple[int, int, int]]],
        eyedropper: tuple[int, int],
        reference_image: Image.Image,
        minimum: float,
        maximum: float,
    ) -> None:
        """Pick once per matched colour, then place the whole colour group."""
        started = time.perf_counter()
        measurements: dict[str, dict[str, float | int]] = {}
        requested_wait = 0.0

        def timed(category, action, *args, **kwargs):
            before = time.perf_counter()
            failed = False
            try:
                return action(*args, **kwargs)
            except Exception:
                failed = True
                raise
            finally:
                duration = time.perf_counter() - before
                item = measurements.setdefault(category, {"count": 0, "seconds": 0.0, "maxMs": 0.0, "failures": 0})
                item["count"] += 1
                item["seconds"] += duration
                item["maxMs"] = max(item["maxMs"], duration * 1000)
                item["failures"] += int(failed)

        def report(state, completed, total, message):
            elapsed = time.perf_counter() - started
            buckets = {
                name: {**item, "averageMs": item["seconds"] * 1000 / item["count"]}
                for name, item in measurements.items()
            }
            metrics = {
                "elapsedSeconds": elapsed,
                "pixelsPerSecond": completed / elapsed if elapsed else 0,
                "requestedWaitSeconds": requested_wait,
                "otherSeconds": max(0, elapsed - sum(item["seconds"] for item in measurements.values())),
                "buckets": buckets,
            }
            self._set_status(state, completed, total, message, metrics)
            if state != "running":
                print("Queue timing: " + json.dumps({"state": state, "completed": completed, **metrics}), flush=True)

        groups: dict[tuple[int, int, int], list[tuple[int, int]]] = {}
        for center, rgb in tasks:
            groups.setdefault(rgb, []).append(center)
        ordered_groups = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
        completed = 0
        live_eyedropper = eyedropper

        def wait_between_actions() -> bool:
            nonlocal requested_wait
            delay = random.uniform(minimum, maximum)
            requested_wait += delay
            return timed("delay", self.stop_event.wait, delay)

        try:
            for group_number, (rgb, centers) in enumerate(ordered_groups, start=1):
                if self.stop_event.is_set():
                    report("stopped", completed, len(tasks), "Stopped; Paint was not pressed")
                    return
                representative = centers[0]
                if group_number > 1:
                    current_image = timed("screenshot", self.adb.screenshot)
                    live_eyedropper, _ = timed("tracking", track_template_point,
                        reference_image,
                        current_image,
                        eyedropper,
                        search_center=live_eyedropper,
                    )
                timed("eyedropper", self.adb.press, *live_eyedropper)
                if wait_between_actions():
                    report("stopped", completed, len(tasks), "Stopped after eyedropper activation")
                    return
                timed("sample", self.adb.tap, *representative)
                if wait_between_actions():
                    report("stopped", completed, len(tasks), "Stopped after group color sample")
                    return

                for center in centers:
                    timed("placement", self.adb.tap, *center)
                    completed += 1
                    report(
                        "running",
                        completed,
                        len(tasks),
                        f"Color group {group_number}/{len(ordered_groups)} RGB {rgb}: "
                        f"pixel {completed}/{len(tasks)}",
                    )
                    if completed < len(tasks) and wait_between_actions():
                        report("stopped", completed, len(tasks), "Stopped; Paint was not pressed")
                        return
            report(
                "complete",
                completed,
                len(tasks),
                f"Grouped mixed queue complete across {len(ordered_groups)} colors. "
                "Review the phone and press Paint yourself if correct.",
            )
        except Exception as exc:
            report("error", completed, len(tasks), f"ADB failed: {exc}")

    def _set_status(self, state: str, completed: int, total: int, message: str, timing: dict[str, Any] | None = None) -> None:
        with self.lock:
            self.queue_status = {
                "state": state,
                "completed": completed,
                "total": total,
                "message": message,
                "timing": timing,
            }

    def status(self) -> dict[str, Any]:
        with self.lock:
            return dict(self.queue_status)

    def stop(self) -> dict[str, Any]:
        self.stop_event.set()
        with self.lock:
            if self.queue_status["state"] == "running":
                self.queue_status["message"] = "Stop requested…"
            return dict(self.queue_status)


def make_handler(state: AppState, token: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "PixelMobileAssist/1.0"

        def log_message(self, format_string: str, *args: object) -> None:
            print(f"[{self.log_date_time_string()}] {format_string % args}")

        def _authorized(self) -> bool:
            parsed = urlparse(self.path)
            query_token = parse_qs(parsed.query).get("token", [""])[0]
            header_token = self.headers.get("X-Pixel-Assist-Token", "")
            return secrets.compare_digest(query_token or header_token, token)

        def _json(self, status: int, data: dict[str, Any]) -> None:
            body = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _error(self, status: int, exc: Exception) -> None:
            self._json(status, {"ok": False, "error": str(exc)})

        def _payload(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 100_000:
                raise ValueError("Request is too large")
            body = self.rfile.read(length)
            return json.loads(body or b"{}")

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if not self._authorized():
                self._error(HTTPStatus.FORBIDDEN, PermissionError("Invalid session token"))
                return
            try:
                if parsed.path == "/":
                    html = UI_PATH.read_text(encoding="utf-8").replace("__SESSION_TOKEN__", token)
                    body = html.encode("utf-8")
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)
                elif parsed.path == "/api/screen":
                    body = state.screen_png()
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)
                elif parsed.path == "/api/status":
                    self._json(HTTPStatus.OK, {"ok": True, **state.status()})
                else:
                    self._error(HTTPStatus.NOT_FOUND, FileNotFoundError("Not found"))
            except Exception as exc:
                self._error(HTTPStatus.BAD_REQUEST, exc)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if not self._authorized():
                self._error(HTTPStatus.FORBIDDEN, PermissionError("Invalid session token"))
                return
            try:
                payload = self._payload()
                if parsed.path == "/api/capture":
                    result = state.capture()
                elif parsed.path == "/api/detect-mixed":
                    result = state.detect_mixed(payload)
                elif parsed.path == "/api/queue-mixed":
                    result = state.start_mixed_queue(payload)
                elif parsed.path == "/api/stop":
                    result = state.stop()
                else:
                    self._error(HTTPStatus.NOT_FOUND, FileNotFoundError("Not found"))
                    return
                self._json(HTTPStatus.OK, {"ok": True, **result})
            except (ValueError, RuntimeError) as exc:
                self._error(HTTPStatus.BAD_REQUEST, exc)
            except Exception as exc:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, exc)

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review-first ADB pixel queue assistant")
    parser.add_argument("--adb", help="Path to adb.exe (usually inside the scrcpy folder)")
    parser.add_argument("--serial", help="ADB device serial when more than one is attached")
    parser.add_argument("--port", type=int, default=8765, help="Local dashboard port")
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    adb_path = find_adb(args.adb)
    adb = AdbClient(adb_path, args.serial)
    CONFIG_PATH.write_text(json.dumps({"adb_path": str(adb_path)}, indent=2), encoding="utf-8")

    token = secrets.token_urlsafe(24)
    state = AppState(adb)
    try:
        server = LocalHTTPServer(("127.0.0.1", args.port), make_handler(state, token))
    except OSError as exc:
        raise RuntimeError(
            f"Cannot start the local dashboard on port {args.port}. Close any older "
            "Pixel Mobile Assist window, or start with --port 8766."
        ) from exc
    url = f"http://127.0.0.1:{args.port}/?token={token}"
    print(f"Pixel Mobile Assist connected to {adb.serial}")
    print(f"Dashboard: {url}")
    print("Keep this terminal open. Press Ctrl+C here to stop the server.")
    if not args.no_open:
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopping Pixel Mobile Assist…")
    finally:
        state.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)
