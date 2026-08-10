import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from detector import (
    connected_components,
    connected_colour_components,
    find_coloured_markers,
    find_geometry_markers,
    find_markers,
    track_template_point,
)


class DetectorTests(unittest.TestCase):
    def test_dimensions_only_detection_has_no_palette_dependency(self):
        image = Image.new("RGB", (90, 50), (240, 240, 240))
        draw = ImageDraw.Draw(image)
        unusual_first = (1, 2, 3)
        unusual_second = (117, 43, 209)
        draw.rectangle((5, 5, 8, 8), fill=unusual_first)
        draw.rectangle((25, 5, 28, 8), fill=unusual_second)
        draw.rectangle((45, 5, 49, 9), fill=(77, 88, 99))

        sample, markers = find_geometry_markers(image, (6, 6))

        self.assertEqual((4, 4), (sample.width, sample.height))
        self.assertEqual(
            [((6, 6), unusual_first), ((26, 6), unusual_second)],
            [(item.center, item.rgb) for item in markers],
        )

    def test_all_colour_components_keep_touching_different_colours_separate(self):
        image = Image.new("RGB", (12, 8), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((2, 2, 4, 4), fill=(10, 20, 30))
        draw.rectangle((5, 2, 7, 4), fill=(40, 50, 60))

        components = connected_colour_components(image)
        small = sorted(
            (item.component.center, item.rgb)
            for item in components
            if item.component.area == 9
        )

        self.assertEqual(
            [((3, 3), (10, 20, 30)), ((6, 3), (40, 50, 60))],
            small,
        )

    def test_tracks_a_calibrated_icon_that_moved_in_the_toolbar(self):
        reference = Image.new("RGB", (220, 120), "white")
        current = Image.new("RGB", (220, 120), "white")
        reference_draw = ImageDraw.Draw(reference)
        current_draw = ImageDraw.Draw(current)
        reference_draw.ellipse((91, 51, 109, 69), outline=(40, 70, 100), width=3)
        reference_draw.line((96, 60, 104, 60), fill=(40, 70, 100), width=2)
        current_draw.ellipse((108, 57, 126, 75), outline=(40, 70, 100), width=3)
        current_draw.line((113, 66, 121, 66), fill=(40, 70, 100), width=2)

        point, error = track_template_point(
            reference, current, (100, 60), search_radius=40
        )

        self.assertEqual((117, 66), point)
        self.assertEqual(0.0, error)

    def test_connected_components_uses_four_connectivity(self):
        mask = np.zeros((6, 6), dtype=bool)
        mask[1:3, 1:3] = True
        mask[3:5, 3:5] = True
        components = connected_components(mask)
        self.assertEqual(2, len(components))
        self.assertEqual([4, 4], sorted(component.area for component in components))

    def test_marker_sample_filters_full_sized_cells(self):
        image = Image.new("RGB", (80, 60), "white")
        draw = ImageDraw.Draw(image)
        target = (12, 129, 110)
        draw.rectangle((10, 10, 12, 12), fill=target)
        draw.rectangle((30, 10, 32, 12), fill=target)
        draw.rectangle((50, 8, 58, 16), fill=target)

        rgb, sample, markers = find_markers(image, (11, 11), tolerance=0)

        self.assertEqual(target, rgb)
        self.assertEqual((3, 3), (sample.width, sample.height))
        self.assertEqual([(11, 11), (31, 11)], [marker.center for marker in markers])

    def test_larger_square_is_not_accepted_as_a_mini_marker(self):
        image = Image.new("RGB", (80, 50), "white")
        draw = ImageDraw.Draw(image)
        target = (12, 129, 110)
        draw.rectangle((5, 5, 8, 8), fill=target)      # sampled 4x4 marker
        draw.rectangle((25, 5, 28, 8), fill=target)    # another 4x4 marker
        draw.rectangle((45, 5, 49, 9), fill=target)    # larger 5x5 pixel

        _, sample, markers = find_markers(image, (6, 6), tolerance=0)

        self.assertEqual((4, 4), (sample.width, sample.height))
        self.assertEqual([(6, 6), (26, 6)], [marker.center for marker in markers])

    def test_mixed_detection_rejects_larger_palette_coloured_square(self):
        image = Image.new("RGB", (80, 50), "white")
        draw = ImageDraw.Draw(image)
        red = (220, 20, 30)
        blue = (20, 40, 220)
        draw.rectangle((5, 5, 8, 8), fill=red)         # sampled 4x4 marker
        draw.rectangle((25, 5, 28, 8), fill=blue)      # valid 4x4 marker
        draw.rectangle((45, 5, 49, 9), fill=blue)      # larger 5x5 pixel

        sample, markers = find_coloured_markers(
            image, (6, 6), [red, blue], tolerance=0
        )

        self.assertEqual((4, 4), (sample.width, sample.height))
        self.assertEqual(
            [((6, 6), red), ((26, 6), blue)],
            [(marker.center, marker.rgb) for marker in markers],
        )

    def test_tolerance_accepts_small_rendering_variation(self):
        image = Image.new("RGB", (40, 30), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((5, 5, 7, 7), fill=(100, 80, 60))
        draw.rectangle((20, 5, 22, 7), fill=(106, 76, 64))

        _, _, markers = find_markers(image, (6, 6), tolerance=7)

        self.assertEqual(2, len(markers))

    def test_nearby_marker_is_used_when_click_hits_large_same_colour_region(self):
        image = Image.new("RGB", (100, 80), "white")
        draw = ImageDraw.Draw(image)
        target = (60, 60, 60)
        draw.rectangle((0, 0, 48, 79), fill=target)
        draw.rectangle((55, 35, 63, 43), fill=target)
        draw.rectangle((75, 35, 83, 43), fill=target)

        rgb, sample, markers = find_markers(
            image,
            (47, 39),
            tolerance=0,
            max_sample_dimension=20,
            nearby_search_radius=20,
        )

        self.assertEqual(target, rgb)
        self.assertEqual((59, 39), sample.center)
        self.assertEqual([(59, 39), (79, 39)], [marker.center for marker in markers])

    def test_coloured_markers_only_include_allowed_colours(self):
        image = Image.new("RGB", (90, 50), "white")
        draw = ImageDraw.Draw(image)
        red = (220, 20, 30)
        blue = (20, 40, 220)
        locked = (30, 200, 60)
        draw.rectangle((5, 5, 7, 7), fill=red)
        draw.rectangle((25, 5, 27, 7), fill=blue)
        draw.rectangle((45, 5, 47, 7), fill=locked)

        sample, markers = find_coloured_markers(
            image,
            (6, 6),
            [red, blue],
            tolerance=0,
        )

        self.assertEqual((3, 3), (sample.width, sample.height))
        self.assertEqual(
            [((6, 6), red), ((26, 6), blue)],
            [(marker.center, marker.rgb) for marker in markers],
        )

    def test_elongated_components_are_not_markers(self):
        image = Image.new("RGB", (100, 60), "white")
        draw = ImageDraw.Draw(image)
        target = (60, 60, 60)
        draw.rectangle((5, 5, 9, 9), fill=target)
        draw.rectangle((25, 5, 29, 9), fill=target)
        # 4x8 fits the old independent width/height/area ranges for a 5x5
        # sample, but its 2:1 aspect ratio must now reject it.
        draw.rectangle((50, 5, 53, 12), fill=target)

        _, _, markers = find_markers(image, (7, 7), tolerance=0)

        self.assertEqual([(7, 7), (27, 7)], [marker.center for marker in markers])


if __name__ == "__main__":
    unittest.main()
