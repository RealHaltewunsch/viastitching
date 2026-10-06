"""Candidate generation independent of wx, pcbnew and board mutation.

Coordinates and dimensions use the caller's units (KiCad internal units in the
plugin). The grid phase deliberately matches the 0.3.x implementation.
"""
from dataclasses import dataclass
import math
import random


@dataclass(frozen=True)
class Grid:
    bounds: tuple
    diameter: float
    pitch: tuple
    offset: tuple = (0, 0)
    style: str = 'Standard'

    def validate(self):
        values = (*self.bounds, self.diameter, *self.pitch, *self.offset)
        if not all(math.isfinite(x) for x in values):
            raise ValueError('Placement parameters must be finite')
        if self.diameter <= 0 or min(self.pitch) <= 0:
            raise ValueError('Via diameter and spacing must be positive')
        if self.bounds[0] > self.bounds[2] or self.bounds[1] > self.bounds[3]:
            raise ValueError('Invalid placement bounds')
        if self.style not in ('Standard', 'Stagger', 'Randomize', 'Spiral', 'Maximize'):
            raise ValueError('Unknown grid style')


def grid_candidates(grid, rng=None):
    """Yield integer positions, preserving legacy order, offsets and jitter."""
    grid.validate()
    rng = random if rng is None else rng
    left, top, right, bottom = grid.bounds
    radius = grid.diameter // 2
    left, top, right, bottom = left+radius, top+radius, right-radius, bottom-radius
    sx, sy = grid.pitch
    dx, dy = grid.offset
    phase = (left+dx) % sx
    start_x = left if phase == 0 else left+sx-phase
    phase = (top+dy) % sy
    y = top if phase == 0 else top+sy-phase
    row = 0
    while y <= bottom:
        x = start_x + (sx//2 if grid.style == 'Stagger' and row % 2 else 0)
        while x <= right:
            if grid.style == 'Randomize':
                yield (int(x+rng.uniform(-1, 1)*sx/5),
                       int(y+rng.uniform(-1, 1)*sy/5))
            else:
                yield int(x), int(y)
            x += sx
        row += 1
        y += sy


@dataclass(frozen=True)
class Decision:
    position: tuple
    reason: str = 'accepted'

    @property
    def accepted(self):
        return self.reason == 'accepted'


def evaluate_candidates(candidates, validate):
    """Classify candidates without creating vias or altering a board.

    A validator returns None for an accepted position or a stable rejection
    category. Creation is exclusively the consumer's responsibility.
    """
    for position in candidates:
        yield Decision(position, validate(position) or 'accepted')


def spiral_candidates(bounds, pitch, center=None):
    """Archimedean spiral with unit turn spacing in normalized coordinates.

    The common separation index rejects locally crowded proposals; the radius
    grows monotonically and each complete turn advances one normalized unit.
    """
    left, top, right, bottom = bounds
    sx, sy = pitch
    if min(sx, sy) <= 0 or not all(math.isfinite(v) for v in (*bounds,*pitch)):
        raise ValueError('Invalid spiral geometry')
    cx, cy = center if center is not None else ((left+right)/2,(top+bottom)/2)
    yield int(cx), int(cy)
    maximum = max(math.hypot((x-cx)/sx,(y-cy)/sy)
                  for x in (left,right) for y in (top,bottom))
    angle = 2*math.pi
    while angle/(2*math.pi) <= maximum:
        radius = angle/(2*math.pi)
        x,y = cx+sx*radius*math.cos(angle), cy+sy*radius*math.sin(angle)
        if left <= x <= right and top <= y <= bottom:
            yield int(x),int(y)
        angle += 2*math.asin(min(1,1/(2*radius)))


def packing_candidates(bounds, separation):
    """Finite deterministic hexagonal proposals, then three gap-seeking phases.

    The validator/accepted-point index must enforce separation. This is a
    heuristic, not an assertion of globally optimal packing.
    """
    if not math.isfinite(separation) or separation <= 0:
        raise ValueError('Minimum separation must be positive')
    left,top,right,bottom = bounds
    dy = separation*math.sqrt(3)/2
    for shift_x,shift_y in ((0,0),(.5,.5),(.25,.25),(.75,.75)):
        row=0; y=top+shift_y*dy
        while y<=bottom:
            x=left+(shift_x+.5*(row%2))*separation
            while x<=right:
                yield int(x),int(y)
                x+=separation
            row+=1; y+=dy


class SeparationIndex:
    """Spatial index for prospective points, independent of board mutation."""
    def __init__(self, pitch):
        self.pitch=pitch
        self.cells={}

    def _scaled(self, point):
        return point[0]/self.pitch[0],point[1]/self.pitch[1]

    def permits(self, point):
        x,y=self._scaled(point); cx,cy=math.floor(x),math.floor(y)
        for i in range(cx-1,cx+2):
            for j in range(cy-1,cy+2):
                if any(math.hypot(x-a,y-b)<1-1e-6 for a,b in self.cells.get((i,j),())):
                    return False
        return True

    def add(self, point):
        x,y=self._scaled(point)
        self.cells.setdefault((math.floor(x),math.floor(y)),[]).append((x,y))


def centered_segment(left, right, spacing):
    """Centers of the largest equally spaced set fitting a usable interval."""
    if spacing<=0 or not all(math.isfinite(v) for v in (left,right,spacing)):
        raise ValueError('Invalid interval or spacing')
    if right<left:
        return
    count=math.floor((right-left)/spacing)+1
    start=(left+right-(count-1)*spacing)/2
    for i in range(count):
        yield int(round(start+i*spacing))


class BoundsIndex:
    """Conservative broad-phase index; very large boxes use a shared list."""
    def __init__(self, cell_size):
        self.cell_size=cell_size
        self.cells={};self.large=[]

    def _cells(self,bounds):
        a,b,c,d=(math.floor(v/self.cell_size) for v in bounds)
        return a,b,c,d

    def add(self, bounds, item):
        a,b,c,d=self._cells(bounds)
        if (c-a+1)*(d-b+1)>256:
            self.large.append(item);return
        for x in range(a,c+1):
            for y in range(b,d+1):self.cells.setdefault((x,y),[]).append(item)

    def query(self,bounds):
        a,b,c,d=self._cells(bounds)
        found={id(item):item for item in self.large}
        if (c-a+1)*(d-b+1)>4096:
            for bucket in self.cells.values():
                found.update((id(item),item) for item in bucket)
        else:
            for x in range(a,c+1):
                for y in range(b,d+1):
                    found.update((id(item),item) for item in self.cells.get((x,y),()))
        return found.values()
