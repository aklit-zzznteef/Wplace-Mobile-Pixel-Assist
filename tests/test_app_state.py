import sys
import unittest
from pathlib import Path
from unittest.mock import patch

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

class RecordingStopEvent:
    def __init__(self):
        self.waits = []
        self.stopped = False

    def clear(self):
        self.stopped = False

    def is_set(self):
        return self.stopped

    def wait(self, timeout):
        self.waits.append(timeout)
        return self.stopped

    def set(self):
        self.stopped = True


class AppStateTests(unittest.TestCase):
    def test_rejects_large_uniform_sample(self):
        state = AppState(FakeAdb(Image.new("RGB", (200, 200), "black")))
        state.capture()
        with self.assertRaisesRegex(ValueError, "too large"):
            state.detect({"roi": [0, 0, 200, 200], "sample": [100, 100], "tolerance": 10})

    def test_capture_resets_completed_status(self):
        state = AppState(FakeAdb(Image.new("RGB", (50, 50), "white")))
        state.queue_status = {"state": "complete", "completed": 2, "total": 2, "message": "done"}
        state.capture()
        self.assertEqual("idle", state.status()["state"])

    def test_mixed_queue_uses_eyedropper_sample_and_place_taps(self):
        adb = FakeAdb(Image.new("RGB", (200, 200), "white"))
        state = AppState(adb)
        state.capture()
        from detector import Component

        state.markers = [Component(49, 49, 51, 51, 9), Component(79, 79, 81, 81, 9)]
        state.marker_colours = [(220, 20, 30), (20, 40, 220)]
        state.start_mixed_queue(
            {
                "indices": [0, 1],
                "eyedropper": [10, 180],
                "groupByColour": False,
                "minDelay": 0.01,
                "maxDelay": 0.01,
            }
        )
        state.worker.join(timeout=2)

        self.assertEqual(
            [(10, 180), (50, 50), (50, 50), (10, 180), (80, 80), (80, 80)],
            adb.taps,
        )
        self.assertEqual([(10, 180, 45), (10, 180, 45)], adb.presses)
        self.assertEqual("complete", state.status()["state"])

    def test_ungrouped_mixed_queue_uses_only_configured_delays(self):
        adb = FakeAdb(Image.new("RGB", (200, 200), "white"))
        state = AppState(adb)
        state.capture()
        from detector import Component
        state.markers = [Component(49, 49, 51, 51, 9), Component(79, 79, 81, 81, 9)]
        state.marker_colours = [(220, 20, 30), (20, 40, 220)]
        stop_event = RecordingStopEvent()
        state.stop_event = stop_event
        with patch("pixel_assist.random.uniform", return_value=0.01):
            state.start_mixed_queue(
                {
                    "indices": [0, 1],
                    "eyedropper": [10, 180],
                    "groupByColour": False,
                    "minDelay": 0.01,
                    "maxDelay": 0.08,
                }
            )
            state.worker.join(timeout=2)

        self.assertEqual([0.01] * 5, stop_event.waits)

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
                "groupByColour": True,
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
