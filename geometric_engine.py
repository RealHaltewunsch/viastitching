"""Geometry-led via placement. Integer positions; no raster enumeration.

The geometry backend supplies permitted via-center polygons. A rectangle is
refined only when a geometric center fails and the rectangle is not provably
excluded by existing spacing disks. No retry count or wall-clock cutoff is used.
"""
from collections import deque
from itertools import chain
from dataclasses import dataclass
from fractions import Fraction
from math import isfinite

STEP = 10000  # KiCad integer units: 0.01 mm.

def nearest(value, step=STEP):
    """Round rational local coordinates, with a fixed half-up convention."""
    return ((value.numerator * 2 + value.denominator * step) //
            (2 * value.denominator * step)) * step if isinstance(value, Fraction) else ((2 * int(value) + step) // (2 * step)) * step

def ceil_div(a,b): return -((-a)//b)

def canonical_ring(points):
    points=tuple(points)
    if points and points[0]==points[-1]:points=points[:-1]
    if not points:return ()
    k=min(range(len(points)),key=lambda i:points[i])
    forward=points[k:]+points[:k]
    backward=(forward[0],)+tuple(reversed(forward[1:]))
    return min(forward,backward)

def ring_contains(p,ring):
    inside=False;x,y=p
    for i,a in enumerate(ring):
        b=ring[(i+1)%len(ring)];cross=(b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0])
        if cross==0 and min(a[0],b[0])<=x<=max(a[0],b[0]) and min(a[1],b[1])<=y<=max(a[1],b[1]):return True
        if (a[1]>y)!=(b[1]>y):
            if (cross>0)==(b[1]>a[1]):inside=not inside
    return inside

@dataclass(frozen=True)
class Polygon:
    outer: tuple
    holes: tuple = ()
    @property
    def bounds(self):
        return min(x for x,y in self.outer),min(y for x,y in self.outer),max(x for x,y in self.outer),max(y for x,y in self.outer)
    def contains(self,p):
        return ring_contains(p,self.outer) and not any(ring_contains(p,r) for r in self.holes)
    def centers(self):
        """Spalt centers from a few cross-sections, not all 0.01-mm rows."""
        a,b,c,d=self.bounds
        center=(nearest(Fraction(a+c,2)),nearest(Fraction(b+d,2)))
        yield center
        # Vertex-event intervals contain linearly moving boundaries. Their
        # mid-sections expose narrow channels even if the bbox center is outside.
        events=sorted({p[1] for r in (self.outer,)+self.holes for p in r})
        ys=[Fraction(b+d,2)]
        pairs=list(zip(events,events[1:]))
        if len(pairs)>24:
            pairs=[pairs[i*(len(pairs)-1)//23] for i in range(24)]
        ys.extend(Fraction(x+y,2) for x,y in pairs)
        candidates=[]
        for yy in ys:
            y=nearest(yy);crossings=[]
            for ring in (self.outer,)+self.holes:
                for i,(x1,y1) in enumerate(ring):
                    x2,y2=ring[(i+1)%len(ring)]
                    if min(y1,y2)<=y<max(y1,y2):
                        crossings.append(Fraction(x1*(y2-y1)+(y-y1)*(x2-x1),y2-y1))
            crossings.sort()
            for left,right in zip(crossings[::2],crossings[1::2]):
                p=(nearest((left+right)/2),y)
                # Prefer the middle of the region over a remote sliver.
                score=(p[0]-center[0])**2+(p[1]-center[1])**2
                candidates.append((score,p))
        for _,p in sorted(set(candidates)):yield p

class Spacing:
    """Exact elliptical density metric, accelerated by nearby buckets."""
    def __init__(self,pitch,minimum):
        self.sx,self.sy=map(int,pitch)
        self.minimum=Fraction(str(minimum));self.n=self.minimum.numerator;self.d=self.minimum.denominator
        self.rx=ceil_div(self.sx*self.n,self.d);self.ry=ceil_div(self.sy*self.n,self.d)
        self.buckets={};self.points=[]
    def add(self,p):
        p=tuple(map(int,p));self.points.append(p)
        self.buckets.setdefault((p[0]//self.rx,p[1]//self.ry),[]).append(p)
    def nearby(self,bounds):
        a,b,c,d=bounds
        left,right=(a-self.rx)//self.rx,(c+self.rx)//self.rx
        bottom,top=(b-self.ry)//self.ry,(d+self.ry)//self.ry
        # Broad queries and tiny tolerance values must never walk millions of
        # empty hash cells. Visit the occupied cells instead when that is cheaper.
        if (right-left+1)*(top-bottom+1)>max(1,len(self.buckets)*4):
            for (x,y),points in self.buckets.items():
                if left<=x<=right and bottom<=y<=top:yield from points
        else:
            for x in range(left,right+1):
                for y in range(bottom,top+1):yield from self.buckets.get((x,y),())
    def square(self,p,q):
        dx=p[0]-q[0];dy=p[1]-q[1]
        return self.d**2*((dx*self.sy)**2+(dy*self.sx)**2)
    def within(self,p,q):return self.square(p,q)<=self.n**2*self.sx**2*self.sy**2
    def excludes(self,p,q):
        return self.square(p,q)<self.n**2*self.sx**2*self.sy**2
    def allows(self,p):return not any(self.excludes(p,q) for q in self.nearby((p[0],p[1],p[0],p[1])))
    def covers_box(self,bounds):
        a,b,c,d=bounds;corners=((a,b),(a,d),(c,b),(c,d))
        # A convex ellipse covering all corners covers the entire rectangle.
        return any(all(self.excludes(p,q) for p in corners) for q in self.nearby(bounds))

@dataclass
class PlacementStats:
    placed: int = 0
    regions: int = 0
    geometry_probes: int = 0
    refined_boxes: int = 0
    cancelled: bool = False

class Cancelled(Exception): pass

class Engine:
    def __init__(self,backend,pitch,minimum=.8,maximum=1.5,pulse=None,physical_radius=0,density=None):
        if any(not isinstance(v,int) or v<=0 for v in pitch):raise ValueError('Positive integer pitch required')
        if not isfinite(float(minimum)) or not isfinite(float(maximum)) or not 0<float(minimum)<=1<=float(maximum):raise ValueError('Invalid distance limits')
        self.density=density if density is not None and density.multiple>1 else None
        self.backend=backend;self.pitch=pitch;self.minimum=minimum;self.maximum=maximum
        self.pulse=pulse or (lambda stats:True);self.stats=PlacementStats()
        self.physical=Spacing((max(1,physical_radius),)*2,1);self.physical_radius=physical_radius
        self.envelopes={};self.active_envelopes=[]
    def spacing(self, minimum):
        return self.density.spacing(minimum) if self.density else Spacing(self.pitch,minimum)
    def radii(self, index, p):
        return index.radii(p) if self.density else (index.rx,index.ry)
    def centers(self, poly):
        if self.density:
            yield from sorted(dict.fromkeys(poly.centers()),key=self.density.factor)
        else:
            yield from poly.centers()
    def tick(self):
        if not self.pulse(self.stats):self.stats.cancelled=True;raise Cancelled()
    def find(self,shape,index,preferred=None,maximum_from=None):
        stack=[shape]
        limit=self.spacing(self.maximum) if maximum_from is not None else None
        while stack:
            self.tick();piece=stack.pop()
            for poly in self.backend.polygons(piece):
                a,b,c,d=poly.bounds
                lo,bt=ceil_div(a,STEP)*STEP,ceil_div(b,STEP)*STEP
                hi,tp=(c//STEP)*STEP,(d//STEP)*STEP
                if lo>hi or bt>tp:continue
                bounds=(lo,bt,hi,tp)
                if limit is not None and self.density and limit.outside_box(bounds,maximum_from):continue
                if limit is not None and not self.density:
                    closest=(max(lo,min(hi,maximum_from[0])),max(bt,min(tp,maximum_from[1])))
                    if not limit.within(closest,maximum_from):continue
                if index.covers_box(bounds) or (self.physical_radius and self.physical.covers_box(self.backend.world_bounds(bounds))) or any(e.covers_box(self.backend.world_bounds(bounds)) for e in self.active_envelopes):continue
                seen=set()
                candidates=chain((preferred,) if preferred is not None else (),self.centers(poly))
                if lo==hi and bt==tp:candidates=chain(((lo,bt),),candidates)
                for p in candidates:
                    if p in seen:continue
                    seen.add(p);self.stats.geometry_probes+=1
                    if poly.contains(p) and index.allows(p) and (limit is None or limit.within(p,maximum_from)) and (not self.physical_radius or self.physical.allows(self.backend.world(p))) and all(e.allows(self.backend.world(p)) for e in self.active_envelopes):return p
                if lo==hi and bt==tp:continue
                self.stats.refined_boxes+=1
                # Split candidate ranges at half-step boundaries. Geometric
                # clipping discards empty halves before any point refinement.
                if hi-lo>=tp-bt and hi>lo:
                    mid=((lo//STEP+hi//STEP)//2)*STEP+STEP//2
                    cuts=[(a,b,mid,d),(mid,b,c,d)]
                else:
                    mid=((bt//STEP+tp//STEP)//2)*STEP+STEP//2
                    cuts=[(a,b,c,mid),(a,mid,c,d)]
                for cut in reversed(cuts):
                    clipped=self.backend.clip(self.backend.make(poly),cut)
                    if not self.backend.empty(clipped):stack.append(clipped)
        return None
    def run_region(self,shape,anchors=()):
        self.active_envelopes=[self.envelopes.setdefault(key,Spacing((radius,radius),1)) for key,radius in getattr(self.backend,"active_envelopes",())]
        self.stats.regions+=1;index=self.spacing(self.minimum)
        for p in sorted(anchors):index.add(p)
        remaining=self.backend.copy(shape)
        for p in index.points:remaining=self.backend.subtract_disk(remaining,p,*self.radii(index,p))
        ox,oy=self.backend.world((0,0))
        for e in self.active_envelopes:
            for world in e.nearby(self.backend.world_bounds(self.backend.bounds(shape))):remaining=self.backend.subtract_disk(remaining,(world[0]-ox,world[1]-oy),e.rx,e.ry)
        protected=getattr(self.density,'protected',None)
        priority=self.backend.intersection(remaining,protected) if protected is not None else None
        edge_stage=priority is not None
        queue=deque();seen=set()
        while not self.backend.empty(remaining):
            self.tick();p=None
            search_area=priority if edge_stage else remaining
            # Grow on the nominal spacing from local accepted points. A blocked
            # ideal is projected to nearby geometry, never retried randomly.
            while queue:
                ideal,parent=queue.popleft()
                if ideal in seen:continue
                seen.add(ideal)
                scale=self.density.multiple if self.density else 1
                shift=max(.05,float(self.maximum)-1)*(float(self.density.factor(parent)) if self.density else 1)
                rx,ry=int(self.pitch[0]*shift),int(self.pitch[1]*shift)
                local=self.backend.clip(search_area,(ideal[0]-rx,ideal[1]-ry,ideal[0]+rx,ideal[1]+ry))
                if self.density:
                    scale=float(max(self.density.factor(parent),self.density.upper_factor((ideal[0]-rx,ideal[1]-ry,ideal[0]+rx,ideal[1]+ry))))
                local=self.backend.within_disk(local,parent,int(self.pitch[0]*float(self.maximum)*scale),int(self.pitch[1]*float(self.maximum)*scale))
                if self.backend.empty(local):continue
                p=self.find(local,index,preferred=ideal,maximum_from=parent)
                if p is not None:break
            if p is None:p=self.find(search_area,index)
            if p is None and edge_stage:
                # The protected band is filled first under the same acceptance
                # rules. Revisit its growth targets against the interior now.
                edge_stage=False;seen.clear()
                for parent in index.points:
                    factor=self.density.factor(parent)
                    sx,sy=(nearest(v*factor) for v in self.pitch)
                    for dx,dy in ((sx,0),(0,sy),(-sx,0),(0,-sy)):
                        queue.append(((nearest(parent[0]+dx),nearest(parent[1]+dy)),parent))
                continue
            if p is None:break  # Geometric proof: no remaining lattice center.
            index.add(p)
            world=self.backend.world(p)
            if self.physical_radius:self.physical.add(world)
            for e in self.active_envelopes:e.add(world)
            self.stats.placed+=1
            yield world
            remaining=self.backend.subtract_disk(remaining,p,*self.radii(index,p))
            if edge_stage:priority=self.backend.subtract_disk(priority,p,*self.radii(index,p))
            for e in self.active_envelopes:
                if e.rx>min(self.radii(index,p)):
                    remaining=self.backend.subtract_disk(remaining,p,e.rx,e.ry)
                    if edge_stage:priority=self.backend.subtract_disk(priority,p,e.rx,e.ry)
            factor=self.density.factor(p) if self.density else 1
            sx,sy=(nearest(value*factor) for value in self.pitch) if self.density else self.pitch
            for dx,dy in ((sx,0),(0,sy),(-sx,0),(0,-sy)):
                queue.append(((nearest(p[0]+dx),nearest(p[1]+dy)),p))
