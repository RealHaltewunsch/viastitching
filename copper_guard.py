"""Preserve actual foreign-net terminal connectivity, without exclusion bands.

Zone copper is represented by its minimum-width core. New holes may split off
unconnected copper slivers; those are allowed. Only a loss of a previously
existing connection between fixed pads/vias is rejected. Tracks and other
copper layers can provide alternate paths.
"""
import pcbnew
import math
from .native_geometry import copy,make,rings,inflate,ellipse,point,ERROR,GUARD

class CopperGuard:
    def __init__(self, geometry):
        self.geometry=geometry;self.records=[];self.fixed={};self.terminals={};self.baseline={};self.pending=None
        self.graph_checks=0;self.rejected=0;self.certificates=[];self.rejected_points=set()
    def add(self, netcode, layer, fill, clearance, thickness):
        for poly in rings(inflate(fill,-thickness//2)):
            shape=make(poly)
            self.records.append({'net':netcode,'layer':layer,'shape':shape,'box':shape.BBox(),
                                 'expanded':None,'thickness':thickness,'radius':self.geometry.diameter//2+clearance+thickness//2+GUARD,'active':True})
    def prepare(self):
        nets={r['net'] for r in self.records};g=self.geometry
        objects=list(g.board.GetTracks())+[p for f in g.board.GetFootprints() for p in f.Pads()]
        for i,item in enumerate(objects):
            g.pulse_at('Foreign copper connectivity',i)
            net=item.GetNetCode()
            if net not in nets:continue
            seeds=[]
            for layer in sorted(set(item.GetLayerSet().Seq())&set(g.layers)):
                shape=pcbnew.SHAPE_POLY_SET();item.TransformShapeToPolygon(shape,layer,0,ERROR,pcbnew.ERROR_OUTSIDE)
                local=g.local_shape(shape)
                self.fixed.setdefault((net,layer),pcbnew.SHAPE_POLY_SET()).Append(local)
                for poly in rings(local):
                    if poly.outer:
                        interior=next((p for p in poly.centers() if poly.contains(p)),poly.outer[0])
                        seeds.append((layer,interior))
            if isinstance(item,(pcbnew.PAD,pcbnew.PCB_VIA)) and seeds:
                self.terminals.setdefault(net,[]).append((item.m_Uuid.AsString(),seeds))
        for shape in self.fixed.values():shape.Simplify()
        for net in sorted(nets):self.baseline[net]=self.signature(net)
    def signature(self, net, trials=None):
        g=self.geometry;trials=trials or {};components={};parents=[];members={}
        def find(a):
            while parents[a]!=a:parents[a]=parents[parents[a]];a=parents[a]
            return a
        def join(a,b):
            a,b=find(a),find(b)
            if a!=b:parents[b]=a
        for layer in g.layers:
            copper=copy(self.fixed.get((net,layer),pcbnew.SHAPE_POLY_SET()))
            for idx,r in enumerate(self.records):
                if r['active'] and r['net']==net and r['layer']==layer:
                    if idx in trials:expanded=inflate(trials[idx],r['thickness']//2)
                    else:
                        if r['expanded'] is None:r['expanded']=inflate(r['shape'],r['thickness']//2)
                        expanded=r['expanded']
                    copper.Append(expanded)
            copper.Simplify();parts=[]
            for subpoly in range(copper.OutlineCount()):
                node=len(parents);parents.append(node);parts.append((node,copper,subpoly))
            components[layer]=parts
        for label,seeds in self.terminals.get(net,()):
            hits=[]
            for layer,p in seeds:
                for node,copper,subpoly in components[layer]:
                    if copper.Contains(point(p),subpoly,0,True):hits.append(node);break
            if not hits:raise ValueError('Cannot resolve foreign copper terminal connectivity')
            for node in hits[1:]:join(hits[0],node)
            members[label]=hits[0]
        groups={}
        for label,node in members.items():groups.setdefault(find(node),set()).add(label)
        return tuple(frozenset(labels) for labels in groups.values())
    def disconnected(self,net,trials):
        self.graph_checks+=1;self.geometry.pulse_at('Foreign copper connectivity',self.graph_checks)
        after=self.signature(net,trials);owner={label:i for i,group in enumerate(after) for label in group}
        return any(len({owner[label] for label in group})>1 for group in self.baseline[net])
    def forbidden_box(self,bounds):
        a,b,c,d=bounds
        return any(all((x-p[0])**2+(y-p[1])**2<=r*r for x,y in ((a,b),(a,d),(c,b),(c,d))) for p,r in self.certificates)
    def certified(self,p):
        return p in self.rejected_points or any((p[0]-q[0])**2+(p[1]-q[1])**2<=r*r for q,r in self.certificates)
    def certify(self,p,net):
        """Prove a disk of forbidden centers using monotone copper removal.

        If a SMALLER clearance hole still disconnects the terminals, every
        full-size hole containing that smaller polygon also disconnects them.
        Use its actual farthest vertex (not an approximate radius) to bound the
        center displacement. This certificate remains valid as holes accumulate.
        """
        radii=[r['radius'] for r in self.records if r['active'] and r['net']==net]
        if not radii:return
        for divisor in (2,4,8,16):
            shrink=min(radii)//divisor;trials={};radius=shrink
            for idx,r in enumerate(self.records):
                if not r['active'] or r['net']!=net:continue
                box=r['box'];reach=r['radius']-shrink
                if not box.GetLeft()-reach<=p[0]<=box.GetRight()+reach or not box.GetTop()-reach<=p[1]<=box.GetBottom()+reach:continue
                hole=ellipse(p,reach,reach,outside=True)
                vertices=[v for poly in rings(hole) for v in poly.outer]
                far=math.isqrt(max(((x-p[0])**2+(y-p[1])**2 for x,y in vertices),default=0))+1
                radius=min(radius,r['radius']-far-2*ERROR-2*GUARD)
                trial=copy(r['shape']);trial.BooleanSubtract(hole);trials[idx]=trial
            if radius>0 and self.disconnected(net,trials):
                self.certificates.append((p,radius));return
    def allows(self, p):
        if self.certified(p):self.pending=None;return False
        trials={};changed_nets=set()
        for idx,r in enumerate(self.records):
            if not r['active']:continue
            radius=r['radius'];box=r['box']
            if not box.GetLeft()-radius<=p[0]<=box.GetRight()+radius or not box.GetTop()-radius<=p[1]<=box.GetBottom()+radius:continue
            hole=ellipse(p,radius,radius,outside=True);trial=copy(r['shape']);trial.BooleanSubtract(hole)
            trials[idx]=trial
            # A core splitting/vanishing is only suspicious, not a rejection.
            # Check the complete net including fixed tracks and other layers.
            if trial.OutlineCount()!=1:changed_nets.add(r['net'])
        for net in changed_nets:
            if self.disconnected(net,trials):
                self.rejected+=1;self.rejected_points.add(p);self.certify(p,net);self.pending=None;return False
        self.pending=(p,trials);return True
    def commit(self,p):
        if self.pending is None or self.pending[0]!=p:
            if not self.allows(p):raise ValueError('Foreign copper connectivity changed before commit')
        for idx,trial in self.pending[1].items():
            record=self.records[idx]
            if trial.OutlineCount()==1:
                record['shape']=trial;record['box']=trial.BBox();record['expanded']=None
            else:
                record['active']=False
                for poly in rings(trial):
                    child=dict(record);child['active']=True;child['shape']=make(poly);child['box']=child['shape'].BBox();child['expanded']=None;self.records.append(child)
        self.pending=None
