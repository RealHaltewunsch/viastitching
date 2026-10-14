"""Immutable track/pad proximity and variable spacing for geometric placement.

Distances use normalized X/Y coordinates. Zones and vias never enter the field.
All contours are captured before placement; only point-query results are cached.
"""
import math
from fractions import Fraction
from .geometric_engine import Polygon, Spacing, ceil_div

FACTOR_SCALE = 1000000

def validate_density(start, end, multiple):
    if not all(math.isfinite(float(v)) for v in (start, end, multiple)) or not 1 <= start < end:
        raise ValueError('Density start must be at least 100%; full distance must be greater than start')
    if multiple < 1 or int(multiple) != multiple:
        raise ValueError('Maximum density spacing factor must be a positive integer')

def segment_distance(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    square = dx*dx+dy*dy
    t = min(1, max(0, ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/square)) if square else 0
    return math.hypot(p[0]-a[0]-t*dx, p[1]-a[1]-t*dy)

class DensityField:
    def __init__(self, polygons, pitch, start=1, end=3, multiple=3, pulse=None):
        validate_density(start, end, multiple)
        if len(pitch) != 2 or any(not isinstance(v, int) or v <= 0 for v in pitch):
            raise ValueError('Positive integer pitch required')
        self.pitch, self.start, self.end, self.multiple = pitch, start, end, int(multiple)
        self.polygons, self.buckets, self.cache = [], {}, {}
        self.oversized = []
        self.cell = max(1, end)
        for polygon in polygons:
            if pulse and not pulse(len(self.polygons)):
                from .geometric_engine import Cancelled
                raise Cancelled()
            scale = lambda ring: tuple((x/pitch[0], y/pitch[1]) for x, y in ring)
            poly = Polygon(scale(polygon.outer), tuple(scale(r) for r in polygon.holes))
            idx = len(self.polygons); self.polygons.append(poly)
            a,b,c,d = poly.bounds
            left,right=math.floor(a/self.cell),math.floor(c/self.cell)
            bottom,top=math.floor(b/self.cell),math.floor(d/self.cell)
            # A long object or tiny nominal pitch must not allocate an enormous
            # two-dimensional bucket grid. Bbox-test oversized objects directly.
            if (right-left+1)*(top-bottom+1)>256:
                self.oversized.append(idx)
                continue
            for x in range(left, right+1):
                for y in range(bottom, top+1):
                    self.buckets.setdefault((x,y), []).append(idx)

    def distance(self, point):
        p = point[0]/self.pitch[0], point[1]/self.pitch[1]
        cx, cy = (math.floor(v/self.cell) for v in p)
        ids = set(self.oversized)
        for x in range(cx-1, cx+2):
            for y in range(cy-1, cy+2): ids.update(self.buckets.get((x,y), ()))
        best = self.end
        for i in sorted(ids):
            poly = self.polygons[i]; a,b,c,d = poly.bounds
            if math.hypot(max(a-p[0], 0, p[0]-c), max(b-p[1], 0, p[1]-d)) >= best: continue
            if poly.contains(p): return 0
            for ring in (poly.outer,) + poly.holes:
                for j, a in enumerate(ring):
                    best = min(best, segment_distance(p, a, ring[(j+1)%len(ring)]))
        return best

    def _factor(self, distance):
        t = min(1, max(0, (distance-self.start)/(self.end-self.start)))
        return 1+(self.multiple-1)*t

    def factor(self, point):
        key = tuple(point)
        if key not in self.cache:
            # Fixed decimal factors keep pair decisions deterministic; candidate
            # coordinates and exact squared spacing comparisons stay integral.
            self.cache[key] = Fraction(round(self._factor(self.distance(point))*FACTOR_SCALE), FACTOR_SCALE)
        return self.cache[key]

    def lower_factor(self, bounds):
        a,b,c,d = bounds
        center = ((a+c)/2, (b+d)/2)
        radius = math.hypot((c-a)/(2*self.pitch[0]), (d-b)/(2*self.pitch[1]))
        # Distance to a fixed closed set is 1-Lipschitz. A conservative factor
        # bound lets spacing disks reject whole rectangles without point scans.
        lower = self._factor(max(0, self.distance(center)-radius))
        return Fraction(max(FACTOR_SCALE, math.floor(lower*FACTOR_SCALE)-1), FACTOR_SCALE)

    def upper_factor(self, bounds):
        a,b,c,d = bounds
        center=((a+c)/2,(b+d)/2)
        radius=math.hypot((c-a)/(2*self.pitch[0]),(d-b)/(2*self.pitch[1]))
        upper=self._factor(self.distance(center)+radius)
        return Fraction(min(self.multiple*FACTOR_SCALE,math.ceil(upper*FACTOR_SCALE)+1),FACTOR_SCALE)

    def spacing(self, minimum): return AdaptiveSpacing(self, minimum)

class AdaptiveSpacing(Spacing):
    """The larger endpoint factor sets the symmetric minimum/maximum distance."""
    def __init__(self, field, minimum):
        super().__init__(field.pitch, minimum)
        self.field = field
        self.rx *= field.multiple; self.ry *= field.multiple

    def _excludes_factor(self, p, q, factor, strict=True):
        required = self.minimum*factor
        dx,dy = p[0]-q[0],p[1]-q[1]
        left = required.denominator**2*((dx*self.sy)**2+(dy*self.sx)**2)
        right = required.numerator**2*self.sx**2*self.sy**2
        return left < right if strict else left <= right

    def excludes(self, p, q):
        return self._excludes_factor(p, q, max(self.field.factor(p), self.field.factor(q)))

    def within(self, p, q):
        return self._excludes_factor(p, q, max(self.field.factor(p), self.field.factor(q)), strict=False)

    def covers_box(self, bounds):
        a,b,c,d = bounds; corners = ((a,b),(a,d),(c,b),(c,d))
        lower = self.field.lower_factor(bounds)
        return any(all(self._excludes_factor(p, q, max(lower,self.field.factor(q))) for p in corners)
                   for q in self.nearby(bounds))

    def outside_box(self, bounds, parent):
        a,b,c,d=bounds
        closest=(max(a,min(c,parent[0])),max(b,min(d,parent[1])))
        factor=max(self.field.factor(parent),self.field.upper_factor(bounds))
        return not self._excludes_factor(closest,parent,factor,strict=False)

    def radii(self, p):
        factor = self.minimum*self.field.factor(p)
        return ceil_div(self.sx*factor.numerator, factor.denominator), ceil_div(self.sy*factor.numerator, factor.denominator)


def board_density(board, pitch, start=1, end=3, multiple=3, origin=(0,0), pulse=None):
    """Snapshot actual pad/track/arc copper contours on enabled copper layers."""
    import pcbnew
    from .native_geometry import rings
    from .geometric_engine import Polygon, Cancelled
    validate_density(start,end,multiple)
    layers = {l for l in board.GetEnabledLayers().Seq() if pcbnew.IsCopperLayer(l)}
    objects = [t for t in board.GetTracks() if not isinstance(t,pcbnew.PCB_VIA)]
    objects.extend(p for f in board.GetFootprints() for p in f.Pads())
    polygons, seen = [], set()
    error = max(1, int(min(pcbnew.FromMM(.001), min(pitch)/1000)))
    for i,item in enumerate(objects):
        if pulse and not pulse(i): raise Cancelled()
        for layer in sorted(layers.intersection(item.GetLayerSet().Seq())):
            shape = pcbnew.SHAPE_POLY_SET()
            item.TransformShapeToPolygon(shape,layer,0,error,pcbnew.ERROR_OUTSIDE)
            for p in rings(shape):
                local = lambda r: tuple((x-origin[0],y-origin[1]) for x,y in r)
                poly = Polygon(local(p.outer),tuple(local(h) for h in p.holes))
                key = poly.outer,poly.holes
                if key not in seen: seen.add(key); polygons.append(poly)
    return DensityField(polygons,pitch,start,end,multiple,pulse=pulse)
