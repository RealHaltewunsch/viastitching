"""Immutable copper-proximity field and deterministic raster thinning."""
import math
from .adaptive_fill import Region, ViaIndex, segment_distance


def validate_density(start, end, multiple):
    if not all(math.isfinite(v) for v in (start,end,multiple)) or not 1 <= start < end:
        raise ValueError('Invalid density distances')
    if multiple < 1 or int(multiple) != multiple:
        raise ValueError('Density multiple must be a positive integer')


class DensityField:
    def __init__(self, polygons, pitch, start=1, end=3, multiple=3):
        validate_density(start,end,multiple)
        self.pitch, self.start, self.end, self.multiple = pitch,start,end,int(multiple)
        self.regions, self.buckets, self.cache = [], {}, {}
        self.cell_size = max(1,end)
        for outline, holes in polygons:
            scale = lambda ring: [(x/pitch[0],y/pitch[1]) for x,y in ring]
            region = Region(0,scale(outline),[scale(h) for h in holes])
            idx = len(self.regions); self.regions.append(region)
            a,b,c,d = region.bounds
            for x in range(math.floor(a/self.cell_size),math.floor(c/self.cell_size)+1):
                for y in range(math.floor(b/self.cell_size),math.floor(d/self.cell_size)+1):
                    self.buckets.setdefault((x,y),[]).append(idx)

    def distance(self, point):
        p = point[0]/self.pitch[0],point[1]/self.pitch[1]
        cx,cy = (math.floor(v/self.cell_size) for v in p)
        ids = set()
        for x in range(cx-1,cx+2):
            for y in range(cy-1,cy+2): ids.update(self.buckets.get((x,y),()))
        best = self.end
        for i in ids:
            r = self.regions[i]
            a,b,c,d = r.bounds
            if math.hypot(max(a-p[0],0,p[0]-c),max(b-p[1],0,p[1]-d)) >= best: continue
            if r.contains(p): return 0
            for a,b in r.nearby_edges(p,best):
                best = min(best,segment_distance(p,a,b))
        return best

    def factor(self, point):
        key = tuple(point)
        if key not in self.cache:
            t = min(1,max(0,(self.distance(point)-self.start)/(self.end-self.start)))
            self.cache[key] = 1+(self.multiple-1)*t
        return self.cache[key]


def board_density(board, pitch, start, end, multiple):
    import pcbnew
    enabled = set(l for l in board.GetEnabledLayers().Seq() if pcbnew.IsCopperLayer(l))
    objects = [t for t in board.GetTracks() if not isinstance(t,pcbnew.PCB_VIA)]
    objects.extend(p for f in board.GetFootprints() for p in f.Pads())
    polygons, seen = [], set()
    error = max(1,int(min(pcbnew.FromMM(.001),min(pitch)/1000)))
    for item in objects:
        for layer in sorted(enabled.intersection(item.GetLayerSet().Seq())):
            poly = pcbnew.SHAPE_POLY_SET()
            item.TransformShapeToPolygon(poly,layer,0,error,pcbnew.ERROR_OUTSIDE)
            def points(chain):
                return tuple((chain.CPoint(i).x,chain.CPoint(i).y) for i in range(chain.PointCount()))
            for i in range(poly.OutlineCount()):
                outline = points(poly.COutline(i))
                holes = tuple(points(poly.CHole(i,j)) for j in range(poly.HoleCount(i)))
                key = outline,holes
                if len(outline)>=3 and key not in seen:
                    seen.add(key); polygons.append(key)
    return DensityField(polygons,pitch,start,end,multiple)


class DensityViaIndex(ViaIndex):
    def __init__(self, field):
        super().__init__(field.pitch)
        self.field = field

    def nearby(self, point, distance):
        factor = self.field.factor(point)
        for other,ids in super().nearby_points(point,distance*self.field.multiple):
            d = math.hypot(*((point[i]-other[i])/self.pitch[i] for i in (0,1)))
            d /= max(factor,self.field.factor(other))
            if d <= distance: yield d,ids

    def blocks_box(self, bounds, minimum):
        # The base-pitch proof is conservative. Variable-radius rejection is
        # performed on actual candidates; never discard a partly free box.
        return super().blocks_box(bounds,minimum)


def ordered_candidates(candidates, field):
    """Keep original positions and stable row/column phase, including jitter."""
    near,far,transition = [],[],[]
    for row,col,point in candidates:
        factor = field.factor(point)
        if factor <= 1: near.append((row,col,point))
        elif factor >= field.multiple:
            if row % field.multiple == 0 and col % field.multiple == 0:
                far.append((row,col,point))
        else: transition.append((factor,row,col,point))
    return [(True,p) for _,_,p in near]+[(False,p) for _,_,p in far]+[
        (False,p) for _,_,_,p in sorted(transition)]
