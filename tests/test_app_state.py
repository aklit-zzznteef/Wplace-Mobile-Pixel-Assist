import sys
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pixel_assist import AppState


class FakeAdb:
    serial = "TEST"

    def __init__(self, image):
        self.image = image
        self.taps = []
        self.presses = []

    def screenshot(self):
        return self.image.copy()

    def tap(self, x, y):
        self.taps.append((x, y))

    def press(self, x, y, duration_ms=45):
        self.presses.append((x, y, duration_ms))
        self.taps.append((x, y))

class AppStateTests(unittest.TestCase):
    def test_concave_region_excludes_notch_and_boundary_markers(self):
        from PIL import ImageDraw
        image = Image.new("RGB", (200, 200), "white")
        draw = ImageDraw.Draw(image)
        for x, y in [(20, 20), (150, 20), (98, 40), (150, 150)]:
            draw.rectangle((x, y, x + 3, y + 3), fill="black")
        state = AppState(FakeAdb(image))
        state.capture()
        result = state.detect_mixed({
            "roi": [0, 0, 200, 200], "sample": [21, 21],
            "colours": [[0, 0, 0]], "tolerance": 0,
            "polygon": [[0, 0], [100, 0], [100, 100], [200, 100], [200, 200], [0, 200]],
        })
        self.assertEqual([[21, 21], [151, 151]], [m["center"] for m in result["markers"]])
        with self.assertRaisesRegex(ValueError, "inside the selected region"):
            state.detect_mixed({
                "roi": [0, 0, 200, 200], "sample": [151, 21],
                "colours": [[0, 0, 0]],
                "polygon": [[0, 0], [100, 0], [100, 100], [200, 100], [200, 200], [0, 200]],
            })

    def test_rejects_large_uniform_sample(self):
        state = AppState(FakeAdb(Image.new("RGB", (200, 200), "black")))
        state.capture()
        with self.assertRaisesRegex(ValueError, "too large"):
            state.detect_mixed({"roi": [0, 0, 200, 200], "sample": [100, 100], "tolerance": 10, "colours": [[0, 0, 0]]})

    def test_capture_resets_completed_status(self):
        state = AppState(FakeAdb(Image.new("RGB", (50, 50), "white")))
        state.queue_status = {"state": "complete", "completed": 2, "total": 2, "message": "done"}
        state.capture()
        self.assertEqual("idle", state.status()["state"])

    def test_grouped_mixed_queue_picks_once_per_colour(self):
        adb = FakeAdb(Image.new("RGB", (200, 200), "white"))
        state = AppState(adb)
        state.capture()
        from detector import Component

        state.markers = [
            Component(49, 49, 51, 51, 9),
            Component(59, 59, 61, 61, 9),
            Component(79, 79, 81, 81, 9),
        ]
        state.marker_colours = [(220, 20, 30), (220, 20, 30), (20, 40, 220)]
        state.start_mixed_queue(
            {
                "indices": [0, 1, 2],
                "eyedropper": [10, 180],
                "minDelay": 0.01,
                "maxDelay": 0.01,
            }
        )
        state.worker.join(timeout=2)

        self.assertEqual(
            [
                (10, 180), (50, 50), (50, 50), (60, 60),
                (10, 180), (80, 80), (80, 80),
            ],
            adb.taps,
        )
        self.assertEqual([(10, 180, 45), (10, 180, 45)], adb.presses)
        self.assertEqual("complete", state.status()["state"])


if __name__ == "__main__":
    unittest.main()
