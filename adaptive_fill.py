"""Deterministic, bounded island refill, independent of pcbnew and wx.

Coordinates are board internal units. Spacing is measured in the metric
hypot(dx / horizontal_pitch, dy / vertical_pitch), so rectangular grids work.
"""
import math
import time
from dataclasses import dataclass


def point_in_ring(point, ring):
    x, y = point
    inside = False
    for a, b in zip(ring, ring[1:] + ring[:1]):
        if (a[1] > y) != (b[1] > y):
            if x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
                inside = not inside
    return inside


def segment_distance(point, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    t = max(0, min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length)) if length else 0
    return math.hypot(point[0] - a[0] - t * dx, point[1] - a[1] - t * dy)


@dataclass
class Region:
    layer: int
    outline: list
    holes: list

    def __post_init__(self):
        xs, ys = zip(*self.outline)
        self.bounds = (min(xs), min(ys), max(xs), max(ys))
        # Index edges by Y band once. Detailed zones can contain tens of
        # thousands of vertices; scanning every edge per candidate is quadratic.
        self.edges = [(a, b) for ring in [self.outline] + self.holes
                      for a, b in zip(ring, ring[1:] + ring[:1])]
        count = min(256, max(1, int(math.sqrt(len(self.edges))) * 2))
        self.band_height = max(1, (self.bounds[3] - self.bounds[1]) / count)
        self.bands = [[] for _ in range(count)]
        for i, (a, b) in enumerate(self.edges):
            for band in range(self._band(min(a[1], b[1])), self._band(max(a[1], b[1])) + 1):
                self.bands[band].append(i)

    def _band(self, y):
        return max(0, min(len(self.bands) - 1,
                          int((y - self.bounds[1]) / self.band_height)))

    def contains(self, point):
        x, y = point
        left, top, right, bottom = self.bounds
        if not (left <= x <= right and top <= y <= bottom):
            return False
        inside = False
        for i in self.bands[self._band(y)]:
            a, b = self.edges[i]
            if (a[1] > y) != (b[1] > y):
                if x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
                    inside = not inside
        return inside

    def nearby_edges(self, point, radius):
        x, y = point
        seen = set()
        for band in range(self._band(y - radius), self._band(y + radius) + 1):
            for i in self.bands[band]:
                if i in seen:
                    continue
                seen.add(i)
                a, b = self.edges[i]
                if (max(a[0], b[0]) >= x - radius and min(a[0], b[0]) <= x + radius
                        and max(a[1], b[1]) >= y - radius and min(a[1], b[1]) <= y + radius):
                    yield a, b

    def fits(self, point, radius):
        return self.contains(point) and all(
            segment_distance(point, a, b) >= radius
            for a, b in self.nearby_edges(point, radius))


class ViaIndex:
    """Spatial buckets; entries carry the layer/island IDs they actually touch."""
    def __init__(self, pitch):
        self.pitch = pitch
        self.buckets = {}
        self.covered = set()

    def cell(self, point):
        return tuple(math.floor(p / step) for p, step in zip(point, self.pitch))

    def add(self, point, regions):
        self.buckets.setdefault(self.cell(point), []).append((point, frozenset(regions)))
        self.covered.update(regions)

    def nearby(self, point, distance):
        cx, cy = self.cell(point)
        reach = math.ceil(distance)
        if (2 * reach + 1) ** 2 > len(self.buckets):
            buckets = self.buckets.values()
        else:
            buckets = (self.buckets.get((x, y), ())
                       for x in range(cx - reach, cx + reach + 1)
                       for y in range(cy - reach, cy + reach + 1))
        for bucket in buckets:
            for other, regions in bucket:
                d = math.hypot((other[0] - point[0]) / self.pitch[0],
                               (other[1] - point[1]) / self.pitch[1])
                if d <= distance:
                    yield d, regions


def validate_settings(pitch, diameter, minimum, maximum):
    if not all(math.isfinite(v) and v > 0 for v in (*pitch, diameter, minimum, maximum)):
        raise ValueError("Spacing, size and distance limits must be finite and positive")
    if not minimum <= 1 <= maximum:
        raise ValueError("Distance limits must include 100% of the grid spacing")


def local_candidates(target, bounds, pitch, diameter, limit=512, spacing_error=None):
    """Search one clipped grid cell, coarse to fine, preferring the grid point.

    Quantize to integer board units, remove duplicate candidates, and cap work
    even when a tiny via or extreme user setting requests impractical precision.
    """
    left, top, right, bottom = bounds
    left, right = max(left, target[0] - pitch[0] / 2), min(right, target[0] + pitch[0] / 2)
    top, bottom = max(top, target[1] - pitch[1] / 2), min(bottom, target[1] + pitch[1] / 2)
    if left > right or top > bottom:
        return
    seen = set()
    seeds = [target, ((left + right) / 2, (top + bottom) / 2)]
    resolution = [max(1, min(step / 100, diameter / 4)) for step in pitch]
    delta = [max(resolution[i], pitch[i] / 4) for i in (0, 1)]
    while True:
        nx = max(1, math.ceil((right - left) / delta[0]))
        ny = max(1, math.ceil((bottom - top) / delta[1]))
        # Do not allocate an unbounded candidate list for extreme settings.
        if (nx + 1) * (ny + 1) > limit * 4:
            return
        candidates = seeds + [(left + (right - left) * x / nx,
                               top + (bottom - top) * y / ny)
                              for x in range(nx + 1) for y in range(ny + 1)]
        candidates.sort(key=lambda p: (((p[0] - target[0]) / pitch[0]) ** 2
                                      + ((p[1] - target[1]) / pitch[1]) ** 2,
                                      spacing_error(p) if spacing_error else 0, p))
        for point in candidates:
            point = tuple(int(round(v)) for v in point)
            if point not in seen and left <= point[0] <= right and top <= point[1] <= bottom:
                seen.add(point)
                yield point
                if len(seen) >= limit:
                    return
        if delta == resolution:
            return
        delta = [max(resolution[i], delta[i] / 2) for i in (0, 1)]
        seeds = []


@dataclass
class FillResult:
    added: int = 0
    unserved: int = 0
    cancelled: bool = False
    limited: bool = False
    examined: int = 0


def refill(regions, index, origin, pitch, diameter, minimum, maximum,
           place, stagger=False, progress=None, time_limit=10.0, candidate_limit=50000,
           clock=time.monotonic):
    """Visit each island's grid cells. place(point) checks and commits a via.

    The caller indexes pre-existing and first-pass vias. An empty island may
    receive its first via without an upper-distance constraint. Physical
    collisions are always checked by place, including across different islands.
    """
    validate_settings(pitch, diameter, minimum, maximum)
    result = FillResult()
    visited = set()
    started = clock()
    last_progress = started - 1

    def stop():
        nonlocal last_progress
        now = clock()
        if progress and now - last_progress >= 0.1:
            last_progress = now
            if not progress(result.added, result.examined):
                result.cancelled = True
        if now - started >= time_limit or result.examined >= candidate_limit:
            result.limited = True
        if result.cancelled or result.limited:
            result.unserved = len(set(range(len(regions))) - index.covered)
            return True
        return False

    def cells(region):
        left, top, right, bottom = region.bounds
        y0 = math.ceil((top - origin[1]) / pitch[1] - 0.5)
        y1 = math.floor((bottom - origin[1]) / pitch[1] + 0.5)
        for row in range(y0, y1 + 1):
            shift = pitch[0] // 2 if stagger and row % 2 else 0
            x0 = math.ceil((left - origin[0] - shift) / pitch[0] - 0.5)
            x1 = math.floor((right - origin[0] - shift) / pitch[0] + 0.5)
            for col in range(x0, x1 + 1):
                yield (origin[0] + col * pitch[0] + shift, origin[1] + row * pitch[1])

    # Try ALL nominal sites before any offsets, so boundary-cell fallbacks
    # cannot steal space from an otherwise feasible nominal grid position.
    # Revisit deferred cells when new vias extend the reachable frontier.
    completed = set()
    for nominal in (True, False):
        while True:
            previous_count = result.added
            # Try unserved islands before expanding coverage on large planes.
            order = sorted(range(len(regions)), key=lambda i: (
                i in index.covered,
                (regions[i].bounds[2] - regions[i].bounds[0]) *
                (regions[i].bounds[3] - regions[i].bounds[1]), i))
            for region_id in order:
                region = regions[region_id]
                if stop():
                    return result
                left, top, right, bottom = region.bounds
                if right - left < diameter or bottom - top < diameter:
                    continue
                for target in cells(region):
                    if (region_id, target) in completed:
                        continue
                    if stop():
                        return result
                    if any(region_id in ids and d < minimum
                           for d, ids in index.nearby(target, minimum)):
                        completed.add((region_id, target))
                        continue
                    def spacing_error(point):
                        distances = [d for d, ids in index.nearby(point, maximum)
                                     if region_id in ids]
                        return abs(min(distances) - 1) if distances else 0
                    candidates = (target,) if nominal else local_candidates(
                        target, region.bounds, pitch, diameter, spacing_error=spacing_error)
                    deferred = False
                    for point in candidates:
                        if stop():
                            return result
                        result.examined += 1
                        if point in visited:
                            continue
                        # Cheap spacing rejection before polygon/clearance checks.
                        neighbors = list(index.nearby(point, maximum))
                        if any(d < minimum for d, _ in neighbors):
                            continue
                        if region_id in index.covered and not any(region_id in ids for _, ids in neighbors):
                            deferred = True
                            continue
                        if not region.fits(point, diameter / 2):
                            continue
                        # Failed physical candidates never become valid as vias are added.
                        visited.add(point)
                        if place(point):
                            touched = [i for i, r in enumerate(regions) if r.fits(point, diameter / 2)]
                            index.add(point, touched)
                            result.added += 1
                            completed.add((region_id, target))
                            break
                    if not nominal and not deferred:
                        # Geometry/physical failures cannot improve when more
                        # vias are added. Only retry cells awaiting a neighbor.
                        completed.add((region_id, target))
            if result.added == previous_count:
                break
    result.unserved = len(set(range(len(regions))) - index.covered)
    return result
