"""KiCad SWIG configuration-space geometry for the independent engine."""
import math
import hashlib
import pcbnew
from pathlib import Path
from .project_rules import ProjectRules
from .geometric_engine import Polygon, canonical_ring, ring_contains, STEP, nearest

ERROR=1000  # 0.001 mm polygon approximation, finer than candidate positions.
GUARD=2000

def point(p):return pcbnew.VECTOR2I(int(p[0]),int(p[1]))
def rings(shape):
    def pts(chain):return tuple((chain.CPoint(i).x,chain.CPoint(i).y) for i in range(chain.PointCount()))
    return [Polygon(canonical_ring(pts(shape.COutline(i))),tuple(sorted(canonical_ring(pts(shape.CHole(i,j))) for j in range(shape.HoleCount(i))))) for i in range(shape.OutlineCount()) if shape.COutline(i).PointCount()>=3]

def make(poly):
    result=pcbnew.SHAPE_POLY_SET();i=result.NewOutline()
    for x,y in poly.outer:result.Append(x,y,i)
    for ring in poly.holes:
        h=result.NewHole(i)
        for x,y in ring:result.Append(x,y,i,h)
    return result

def copy(shape):return pcbnew.SHAPE_POLY_SET(shape)
def shift(shape,dx,dy):
    result=pcbnew.SHAPE_POLY_SET()
    for p in rings(shape):result.Append(make(Polygon(tuple((x+dx,y+dy) for x,y in p.outer),tuple(tuple((x+dx,y+dy) for x,y in r) for r in p.holes))))
    return result

def inflate(shape,amount):
    result=copy(shape)
    result.Inflate(int(amount),pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS,ERROR)
    return result

def ellipse(center,rx,ry,outside=False):
    """Inscribed exclusion polygon; exact spacing remains authoritative.

    Shrinking radii by two IU ensures rounding never covers an allowed center.
    A geometric residual check handles the thin approximation strips.
    """
    if rx<=2 or ry<=2:return pcbnew.SHAPE_POLY_SET()
    original_rx,original_ry=rx,ry
    rx=max(0,rx-2);ry=max(0,ry-2)
    count=max(32,min(256,int(math.ceil(math.pi/math.sqrt(max(1,ERROR)/max(1,rx,ry))))))
    if outside:
        rx=int(math.ceil(original_rx/math.cos(math.pi/count)))+2
        ry=int(math.ceil(original_ry/math.cos(math.pi/count)))+2
    points=tuple((center[0]+int(rx*math.cos(2*math.pi*i/count)),center[1]+int(ry*math.sin(2*math.pi*i/count))) for i in range(count))
    return make(Polygon(points))

class Backend:
    def __init__(self,origin=(0,0)):self.origin=origin
    def world(self,p):return p[0]+self.origin[0],p[1]+self.origin[1]
    def world_bounds(self,b):
        a,y,c,d=b;ox,oy=self.origin;return a+ox,y+oy,c+ox,d+oy
    def polygons(self,shape):return sorted(rings(shape),key=lambda p:(p.area,p.bounds,p.outer,p.holes))
    @staticmethod
    def contains(shape,p):return shape.Contains(point(p))
    def fronts(self,shape,pitch):
        """Nested contour fronts in the anisotropic spacing metric.

        Work proportional to perimeter and contour levels, never to 0.01-mm
        board pixels. Regions already describe VIA CENTERS; no second erosion
        by via diameter/clearance is applied here.
        """
        unit=min(pitch)
        def scale(source,inverse=False):
            return make(Polygon(tuple((int(round(x*pitch[0]/unit)),int(round(y*pitch[1]/unit))) if inverse else (int(round(x*unit/pitch[0])),int(round(y*unit/pitch[1]))) for x,y in source.outer),tuple(tuple((int(round(x*pitch[0]/unit)),int(round(y*pitch[1]/unit))) if inverse else (int(round(x*unit/pitch[0])),int(round(y*unit/pitch[1]))) for x,y in r) for r in source.holes)))
        normalized=pcbnew.SHAPE_POLY_SET()
        for poly in self.polygons(shape):normalized.Append(scale(poly))
        a,b,c,d=self.bounds(normalized)
        if min(c-a,d-b)<unit:
            return list(dict.fromkeys(p for poly in self.polygons(shape) for p in poly.centers() if poly.contains(p)))
        result=[];offset=max(STEP*2,ERROR*4)
        while True:
            getattr(self,"pulse",lambda *a:None)("Contour fronts",offset//unit)
            front=inflate(normalized,-offset)
            if self.empty(front):break
            for poly in self.polygons(front):
                for ring in (poly.outer,)+poly.holes:
                    lengths=[math.hypot(ring[(i+1)%len(ring)][0]-p[0],ring[(i+1)%len(ring)][1]-p[1]) for i,p in enumerate(ring)]
                    perimeter=sum(lengths);count=max(1,int(round(perimeter/unit)));spacing=perimeter/count
                    edge=0;start=0
                    for n in range(count):
                        target=n*spacing
                        while edge<len(ring)-1 and target>start+lengths[edge]:start+=lengths[edge];edge+=1
                        p=ring[edge];q=ring[(edge+1)%len(ring)];t=(target-start)/max(1,lengths[edge])
                        result.append((nearest(round((p[0]+t*(q[0]-p[0]))*pitch[0]/unit)),nearest(round((p[1]+t*(q[1]-p[1]))*pitch[1]/unit))))
            offset+=unit
        return list(dict.fromkeys(result))
    @staticmethod
    def bounds(shape):
        b=shape.BBox();return b.GetLeft(),b.GetTop(),b.GetRight(),b.GetBottom()
    copy=staticmethod(copy)
    make=staticmethod(make)
    @staticmethod
    def empty(shape):return shape.OutlineCount()==0
    @staticmethod
    def intersection(shape,other):
        result=copy(shape);result.BooleanIntersection(other);return result
    @staticmethod
    def clip(shape,bounds):
        a,b,c,d=map(int,bounds)
        if a>=c or b>=d:return pcbnew.SHAPE_POLY_SET()
        rect=make(Polygon(((a,b),(c,b),(c,d),(a,d))))
        result=copy(shape);result.BooleanIntersection(rect);return result
    @staticmethod
    def subtract_disk(shape,center,rx,ry):
        result=copy(shape);result.BooleanSubtract(ellipse(center,rx,ry));return result
    @staticmethod
    def within_disk(shape,center,rx,ry):
        result=copy(shape);result.BooleanIntersection(ellipse(center,rx,ry,outside=True));return result

def own_clearance(item,layer):
    try:return item.GetOwnClearance(layer)
    except (AttributeError,TypeError):
        try:return item.GetEffectiveNetClass().GetClearance()
        except (AttributeError,TypeError):return 0

def via_width(item,layer):
    try:return item.GetWidth(layer)
    except TypeError:return item.GetWidth()

class BoardGeometry:
    def __init__(self,board,zone,netcode,diameter,drill,edge,all_layers=False,object_clearance=None,pulse=None):
        self.board=board;self.zone=zone;self.netcode=netcode;self.diameter=diameter;self.drill=drill
        self.edge=edge;self.all_layers=all_layers;self.pulse=pulse or (lambda stage,n:True)
        # Local integer origin BEFORE offset/boolean operations removes absolute
        # board phase and avoids floating-point sums involving world positions.
        box=zone.GetBoundingBox();self.origin=(box.GetLeft()//STEP*STEP,box.GetTop()//STEP*STEP)
        self.backend=Backend(self.origin);self.backend.pulse=self.pulse_at
        self.layers=[l for l in board.GetEnabledLayers().Seq() if pcbnew.IsCopperLayer(l)]
        ds=board.GetDesignSettings()
        self.hole_gap=getattr(ds,'m_HoleToHoleMin',pcbnew.FromMM(.254))
        self.hole_clearance=getattr(ds,'m_HoleClearance',pcbnew.FromMM(.2))
        self.object_clearance=max(object_clearance or 0,getattr(ds,'m_MinClearance',0))
        reference=pcbnew.PCB_VIA(board);reference.SetNetCode(netcode)
        reference.SetWidth(diameter);reference.SetDrill(drill);reference.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        self.net_clearance={layer:own_clearance(reference,layer) for layer in self.layers}
        self.reference=reference
        filename=board.GetFileName()
        self.rules=ProjectRules(str(Path(filename).with_suffix(".kicad_dru")) if filename else None)
        self.rule_context=self.rules.context(self.context(reference))
        self.net_clearance={l:max(c,self.rules.inherited_clearance(self.rule_context)) for l,c in self.net_clearance.items()}
        self.anchors=[];self.physical_holes=pcbnew.SHAPE_POLY_SET()
        self.pair_radius=drill+self.hole_gap
        self.envelope_regions=[]
        # Imported here to avoid a module-level geometry/guard dependency cycle.
        from .copper_guard import CopperGuard
        self.guard=CopperGuard(self)
        self.topology=self.build()
        self.free=copy(self.topology);self.free.BooleanSubtract(self.physical_holes)
        self.guard.prepare();self.backend.accepts=self.guard.allows;self.backend.accept=self.guard.commit;self.backend.forbidden_box=self.guard.forbidden_box
    @staticmethod
    def context(item):
        try:name=item.GetEffectiveNetClass().GetName()
        except (AttributeError,TypeError):name="Default"
        return {"NetClass":str(name),"NetName":str(item.GetNetname())}
    def required(self,kind,item,layer=None):
        layer_name=self.board.GetStandardLayerName(layer) if layer is not None else None
        return self.rules.minimum(kind,self.rule_context,self.rules.context(self.context(item)),layer_name)
    def local(self,p):return p[0]-self.origin[0],p[1]-self.origin[1]
    def local_shape(self,s):return shift(s,-self.origin[0],-self.origin[1])
    def pulse_at(self,stage,n):
        if not self.pulse(stage,n):
            from .geometric_engine import Cancelled
            raise Cancelled()
    def build(self):
        radius=self.diameter//2
        copper=[]
        # Same-net fills on enabled layers, bounded to the selected zone's
        # copper footprint. At least two vs all is an electrical criterion.
        selected=pcbnew.SHAPE_POLY_SET()
        for l in self.zone.GetLayerSet().Seq():
            if l in self.layers:selected.BooleanAdd(self.local_shape(self.zone.GetFilledPolysList(l)))
        if self.backend.empty(selected):raise ValueError("Fill the selected copper zone before placement")
        selected=inflate(selected,-radius-GUARD)
        for l in self.layers:
            self.pulse_at("Copper layers",l)
            poly=pcbnew.SHAPE_POLY_SET()
            for z in self.board.Zones():
                is_rule=z.GetIsRuleArea() if hasattr(z,'GetIsRuleArea') else z.GetIsKeepout()
                if not is_rule and z.GetNetCode()==self.netcode and l in z.GetLayerSet().Seq():poly.BooleanAdd(self.local_shape(z.GetFilledPolysList(l)))
            copper.append(inflate(poly,-radius-GUARD))
        domain=pcbnew.SHAPE_POLY_SET()
        if self.all_layers:
            if copper:
                domain=copy(copper[0])
                for poly in copper[1:]:domain.BooleanIntersection(poly)
        else:
            for i,a in enumerate(copper):
                for b in copper[i+1:]:
                    pair=copy(a);pair.BooleanIntersection(b);domain.BooleanAdd(pair)
        domain.BooleanIntersection(selected)
        outline=pcbnew.SHAPE_POLY_SET()
        try:valid=self.board.GetBoardPolygonOutlines(outline,False)
        except TypeError:valid=self.board.GetBoardPolygonOutlines(outline)
        if not valid:raise ValueError('A closed board outline is required')
        domain.BooleanIntersection(inflate(self.local_shape(outline),-radius-self.edge-GUARD))
        if self.backend.empty(domain):return domain
        obstacles=pcbnew.SHAPE_POLY_SET()
        objects=list(self.board.GetTracks())+[p for f in self.board.GetFootprints() for p in f.Pads()]
        # Reject far objects before expensive shape conversion, conservatively.
        bounds=domain.BBox()
        for i,item in enumerate(objects):
            self.pulse_at('Copper obstacles',i)
            if isinstance(item,pcbnew.PCB_VIA):
                p=self.local((item.GetPosition().x,item.GetPosition().y))
                hole=ellipse(p,(self.drill+item.GetDrillValue())//2+max(self.hole_gap,self.required("hole_to_hole",item))+GUARD,(self.drill+item.GetDrillValue())//2+max(self.hole_gap,self.required("hole_to_hole",item))+GUARD)
                if item.GetNetCode()==self.netcode:
                    self.anchors.append(p);self.physical_holes.Append(hole)
                    continue
                obstacles.Append(hole)
            item_box=item.GetBoundingBox()
            moved=pcbnew.BOX2I(point(self.local((item_box.GetLeft(),item_box.GetTop()))),point((item_box.GetWidth(),item_box.GetHeight())))
            common=set(item.GetLayerSet().Seq())&set(self.layers)
            clearances={l:max(self.object_clearance,own_clearance(item,l),self.rules.inherited_clearance(self.rules.context(self.context(item))),self.net_clearance[l],self.required("clearance",item,l),self.required("physical_clearance",item,l)) for l in common}
            moved.Inflate(radius+max(clearances.values(),default=0)+self.hole_gap+GUARD)
            if not bounds.Intersects(moved):continue
            if item.GetNetCode()!=self.netcode:
                for l in sorted(common):
                    poly=pcbnew.SHAPE_POLY_SET()
                    clearance=clearances[l]
                    item.TransformShapeToPolygon(poly,l,radius+clearance+GUARD,ERROR,pcbnew.ERROR_OUTSIDE)
                    obstacles.Append(self.local_shape(poly))
            if isinstance(item,pcbnew.PAD) and item.GetNetCode()==self.netcode:
                # Same-net copper overlap is electrically legal, but drilling
                # into a component pad is not permitted for stitching. Exclude
                # the entire drill disk on every traversed copper layer, using
                # the actual pad contour rather than its bounding rectangle.
                for l in sorted(common):
                    poly=pcbnew.SHAPE_POLY_SET()
                    item.TransformShapeToPolygon(poly,l,self.drill//2+GUARD,ERROR,pcbnew.ERROR_OUTSIDE)
                    obstacles.Append(self.local_shape(poly))
            if isinstance(item,pcbnew.PAD) and max(item.GetDrillSize().x,item.GetDrillSize().y)>0:
                # Exact oblong/rotated drill contour. Own-net pads need only
                # hole separation; foreign pads also require hole-to-copper.
                poly=pcbnew.SHAPE_POLY_SET()
                margin=self.drill//2+max(self.hole_gap,self.required("hole_to_hole",item))+GUARD
                if item.GetNetCode()!=self.netcode:margin=max(margin,radius+max(self.hole_clearance,max((self.required("hole_clearance",item,l) for l in self.layers),default=0),max((self.required("physical_hole_clearance",item,l) for l in self.layers),default=0))+GUARD)
                item.TransformHoleToPolygon(poly,margin,ERROR,pcbnew.ERROR_OUTSIDE)
                (self.physical_holes if item.GetNetCode()==self.netcode else obstacles).Append(self.local_shape(poly))
        # Foreign pours refill around vias; preserve their terminal connectivity.
        for z in self.board.Zones():
            self.pulse_at("Other copper fills",0)
            is_rule=z.GetIsRuleArea() if hasattr(z,'GetIsRuleArea') else z.GetIsKeepout()
            if is_rule or z.GetNetCode()==self.netcode:continue
            for l in set(z.GetLayerSet().Seq()) & set(self.layers):
                fill=self.local_shape(z.GetFilledPolysList(l))
                clearance=max(self.object_clearance,self.net_clearance[l],own_clearance(z,l),self.rules.inherited_clearance(self.rules.context(self.context(z))),self.required('clearance',z,l))
                # Zone filling cuts clearance holes automatically. Preserve
                # actual terminal connections instead of discarding a blanket
                # boundary band or prohibiting overlapping hole envelopes.
                self.guard.add(z.GetNetCode(),l,fill,clearance,z.GetMinThickness())
        for z in list(self.board.Zones())+[z for f in self.board.GetFootprints() for z in f.Zones()]:
            is_rule=z.GetIsRuleArea() if hasattr(z,'GetIsRuleArea') else z.GetIsKeepout()
            if is_rule and z.GetDoNotAllowVias() and set(z.GetLayerSet().Seq())&set(self.layers):obstacles.Append(inflate(self.local_shape(z.Outline()),radius+GUARD))
        obstacles.Simplify();self.physical_holes.Simplify()
        domain.BooleanSubtract(obstacles);domain.Simplify()
        return domain
    def regions(self):
        for polygon in self.backend.polygons(self.topology):
            region=make(polygon);region.BooleanIntersection(self.free)
            if self.backend.empty(region):continue
            # Via centers inside a drilled hole still belong to its surrounding
            # free component. Ignore own-hole contours only for anchor ownership;
            # the full hole exclusion remains in the placement geometry.
            anchors=[p for p in self.anchors if ring_contains(p,polygon.outer)]
            self.backend.active_envelopes=[]
            for key,core,r in self.envelope_regions:
                membership=make(polygon);membership.BooleanIntersection(core)
                if not self.backend.empty(membership):self.backend.active_envelopes.append((key,r))
            yield region,anchors
