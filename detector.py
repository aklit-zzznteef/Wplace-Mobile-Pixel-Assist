"""Small-square marker detection for Pixel Mobile Assist.

The detector deliberately has no Android or GUI dependencies so it can be
tested separately.  It finds connected areas close to a sampled RGB colour,
then keeps areas whose geometry resembles the marker that the user sampled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
from PIL import Image


MAX_MARKER_ASPECT_RATIO = 1.6
DEFAULT_MARKER_SIZE_FLEX = 0.35


@dataclass(frozen=True)
class Component:
    left: int
    top: int
    right: int
    bottom: int
    area: int

    @property
    def width(self) -> int:
        return self.right - self.left + 1

    @property
    def height(self) -> int:
        return self.bottom - self.top + 1

    @property
    def center(self) -> tuple[int, int]:
        return ((self.left + self.right) // 2, (self.top + self.bottom) // 2)

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x <= self.right and self.top <= y <= self.bottom


@dataclass(frozen=True)
class ColouredComponent:
    component: Component
    rgb: tuple[int, int, int]

    @property
    def center(self) -> tuple[int, int]:
        return self.component.center


class _DisjointSet:
    def __init__(self) -> None:
        self.parent: list[int] = []

    def add(self) -> int:
        index = len(self.parent)
        self.parent.append(index)
        return index

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, first: int, second: int) -> None:
        first_root = self.find(first)
        second_root = self.find(second)
        if first_root != second_root:
            self.parent[second_root] = first_root


def colour_mask(image: Image.Image, rgb: tuple[int, int, int], tolerance: int) -> np.ndarray:
    """Return pixels whose per-channel distance is within ``tolerance``."""
    pixels = np.asarray(image.convert("RGB"), dtype=np.int16)
    target = np.asarray(rgb, dtype=np.int16)
    return np.max(np.abs(pixels - target), axis=2) <= tolerance


def connected_components(mask: np.ndarray) -> list[Component]:
    """Find 4-connected components with a run-length union algorithm."""
    if mask.ndim != 2:
        raise ValueError("mask must be a two-dimensional array")

    # Each run is [y, start_x, end_x, disjoint_set_index].
    runs: list[tuple[int, int, int, int]] = []
    previous: list[tuple[int, int, int, int]] = []
    sets = _DisjointSet()

    for y, row in enumerate(mask):
        padded = np.pad(row.astype(np.int8), (1, 1))
        changes = np.diff(padded)
        starts = np.flatnonzero(changes == 1)
        ends = np.flatnonzero(changes == -1) - 1
        current: list[tuple[int, int, int, int]] = []

        previous_index = 0
        for start, end in zip(starts.tolist(), ends.tolist()):
            set_index = sets.add()
            run = (y, start, end, set_index)
            current.append(run)
            runs.append(run)

            while previous_index < len(previous) and previous[previous_index][2] < start:
                previous_index += 1
            candidate = previous_index
            while candidate < len(previous) and previous[candidate][1] <= end:
                sets.union(set_index, previous[candidate][3])
                candidate += 1
        previous = current

    aggregates: dict[int, list[int]] = {}
    for y, start, end, set_index in runs:
        root = sets.find(set_index)
        if root not in aggregates:
            aggregates[root] = [start, y, end, y, end - start + 1]
        else:
            item = aggregates[root]
            item[0] = min(item[0], start)
            item[1] = min(item[1], y)
            item[2] = max(item[2], end)
            item[3] = max(item[3], y)
            item[4] += end - start + 1

    return [Component(*values) for values in aggregates.values()]


def _marker_geometry_limits(
    sample: Component, size_flex: float
) -> tuple[int, int, int, int, int, int]:
    min_width = max(1, int(round(sample.width * (1.0 - size_flex))))
    max_width = max(min_width, int(round(sample.width * (1.0 + size_flex))))
    min_height = max(1, int(round(sample.height * (1.0 - size_flex))))
    max_height = max(min_height, int(round(sample.height * (1.0 + size_flex))))
    min_area = max(1, int(round(sample.area * (1.0 - size_flex))))
    max_area = max(min_area, int(round(sample.area * (1.0 + size_flex))))
    return min_width, max_width, min_height, max_height, min_area, max_area


def _matches_marker_geometry(
    component: Component, limits: tuple[int, int, int, int, int, int]
) -> bool:
    min_width, max_width, min_height, max_height, min_area, max_area = limits
    return (
        min_width <= component.width <= max_width
        and min_height <= component.height <= max_height
        and min_area <= component.area <= max_area
        and max(component.width, component.height)
        <= min(component.width, component.height) * MAX_MARKER_ASPECT_RATIO
    )


def find_markers(
    image: Image.Image,
    sample_point: tuple[int, int],
    tolerance: int = 5,
    size_flex: float = DEFAULT_MARKER_SIZE_FLEX,
    max_sample_dimension: int | None = None,
    nearby_search_radius: int = 0,
) -> tuple[tuple[int, int, int], Component, list[Component]]:
    """Detect components geometrically similar to a user-sampled marker.

    Coordinates are local to ``image``.  The sampled component is always
    retained.  ``size_flex`` controls allowed proportional width/height
    variation. It allows one-pixel rasterization differences on tiny markers
    without admitting visibly larger full-size canvas pixels.
    """
    x, y = sample_point
    if not (0 <= x < image.width and 0 <= y < image.height):
        raise ValueError("sample point is outside the selected canvas region")

    rgb = image.convert("RGB").getpixel((x, y))
    components = connected_components(colour_mask(image, rgb, tolerance))
    sample = next((component for component in components if component.contains(x, y)), None)
    if (
        sample is not None
        and max_sample_dimension is not None
        and (sample.width > max_sample_dimension or sample.height > max_sample_dimension)
    ):
        # The click can be a few display pixels off when the phone screenshot is
        # scaled down in the dashboard.  A marker colour may also occur in a
        # huge background region.  In either case, use the nearest compact
        # component of the sampled colour instead of accepting the background.
        compact = [
            component
            for component in components
            if 4 <= component.area
            and component.width <= max_sample_dimension
            and component.height <= max_sample_dimension
            and max(component.width, component.height)
            <= min(component.width, component.height) * MAX_MARKER_ASPECT_RATIO
        ]

        def distance_to_bounds(component: Component) -> float:
            dx = max(component.left - x, 0, x - component.right)
            dy = max(component.top - y, 0, y - component.bottom)
            return (dx * dx + dy * dy) ** 0.5

        nearest = min(compact, key=distance_to_bounds, default=None)
        if nearest is not None and distance_to_bounds(nearest) <= nearby_search_radius:
            sample = nearest
    if sample is None:
        raise ValueError("the sampled pixel did not form a detectable marker")

    limits = _marker_geometry_limits(sample, size_flex)

    markers = [
        component
        for component in components
        if _matches_marker_geometry(component, limits)
    ]
    markers.sort(key=lambda component: (component.top, component.left))
    return rgb, sample, markers


def offset_components(
    components: Iterable[Component], x_offset: int, y_offset: int
) -> list[Component]:
    return [
        Component(
            component.left + x_offset,
            component.top + y_offset,
            component.right + x_offset,
            component.bottom + y_offset,
            component.area,
        )
        for component in components
    ]


def track_template_point(
    reference: Image.Image,
    current: Image.Image,
    reference_point: tuple[int, int],
    search_center: tuple[int, int] | None = None,
    patch_radius: int = 16,
    search_radius: int = 140,
    max_mean_error: float = 35.0,
) -> tuple[tuple[int, int], float]:
    """Relocate a small calibrated UI icon near its previous position.

    Only visually distinctive pixels from the reference patch are compared, so
    a mostly white rounded button does not match every blank part of a toolbar.
    If the patch is not distinctive or no credible match exists, the previous
    position is returned unchanged.
    """
    reference_rgb = np.asarray(reference.convert("RGB"), dtype=np.int16)
    current_rgb = np.asarray(current.convert("RGB"), dtype=np.int16)
    if reference_rgb.shape != current_rgb.shape:
        return search_center or reference_point, float("inf")

    ref_x, ref_y = reference_point
    center_x, center_y = search_center or reference_point
    left = ref_x - patch_radius
    top = ref_y - patch_radius
    right = ref_x + patch_radius + 1
    bottom = ref_y + patch_radius + 1
    if left < 0 or top < 0 or right > reference.width or bottom > reference.height:
        return (center_x, center_y), float("inf")

    patch = reference_rgb[top:bottom:2, left:right:2]
    border_colour = np.median(
        np.concatenate((patch[0], patch[-1], patch[:, 0], patch[:, -1])), axis=0
    )
    distinctive = np.max(np.abs(patch - border_colour), axis=2) >= 14
    offsets = np.argwhere(distinctive)
    if len(offsets) < 8:
        return (center_x, center_y), float("inf")

    min_x = max(patch_radius, center_x - search_radius)
    max_x = min(current.width - patch_radius - 1, center_x + search_radius)
    min_y = max(patch_radius, center_y - search_radius)
    max_y = min(current.height - patch_radius - 1, center_y + search_radius)
    if min_x > max_x or min_y > max_y:
        return (center_x, center_y), float("inf")

    candidate_x = np.arange(min_x, max_x + 1)
    candidate_y = np.arange(min_y, max_y + 1)
    scores = np.zeros((len(candidate_y), len(candidate_x)), dtype=np.int32)
    for patch_y, patch_x in offsets:
        source_y = top + int(patch_y) * 2
        source_x = left + int(patch_x) * 2
        dy = source_y - ref_y
        dx = source_x - ref_x
        expected = reference_rgb[source_y, source_x]
        actual = current_rgb[
            candidate_y[:, None] + dy,
            candidate_x[None, :] + dx,
        ]
        scores += np.sum(np.abs(actual - expected), axis=2, dtype=np.int32)

    best_y_index, best_x_index = np.unravel_index(np.argmin(scores), scores.shape)
    best = (int(candidate_x[best_x_index]), int(candidate_y[best_y_index]))
    mean_error = float(scores[best_y_index, best_x_index]) / (len(offsets) * 3)
    if mean_error > max_mean_error:
        return (center_x, center_y), mean_error
    return best, mean_error


def find_coloured_markers(
    image: Image.Image,
    sample_point: tuple[int, int],
    colours: Iterable[tuple[int, int, int]],
    tolerance: int = 5,
    size_flex: float = DEFAULT_MARKER_SIZE_FLEX,
    max_sample_dimension: int | None = None,
    nearby_search_radius: int = 0,
) -> tuple[Component, list[ColouredComponent]]:
    """Find marker-sized components for each explicitly allowed colour.

    The marker geometry is learned from ``sample_point``. Colours are supplied
    by the account profile, so unavailable/locked palette colours never become
    queue candidates.
    """
    _, sample, _ = find_markers(
        image,
        sample_point,
        tolerance=tolerance,
        size_flex=size_flex,
        max_sample_dimension=max_sample_dimension,
        nearby_search_radius=nearby_search_radius,
    )
    limits = _marker_geometry_limits(sample, size_flex)

    rgb_image = image.convert("RGB")
    pixels = np.asarray(rgb_image, dtype=np.int16)
    by_center: dict[tuple[int, int], tuple[int, ColouredComponent]] = {}
    unique_colours = sorted(set(colours))
    for rgb in unique_colours:
        target = np.asarray(rgb, dtype=np.int16)
        mask = np.max(np.abs(pixels - target), axis=2) <= tolerance
        for component in connected_components(mask):
            if not _matches_marker_geometry(component, limits):
                continue
            center = component.center
            actual = pixels[center[1], center[0]]
            distance = int(np.sum((actual - target) ** 2))
            candidate = ColouredComponent(component=component, rgb=rgb)
            previous = by_center.get(center)
            if previous is None or distance < previous[0]:
                by_center[center] = (distance, candidate)

    markers = [item[1] for item in by_center.values()]
    markers.sort(key=lambda item: (item.component.top, item.component.left))
    return sample, markers
