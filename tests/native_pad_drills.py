"""Manufacturing regression: stitching drills must never overlap same-net pads.

Electrical DRC permits same-net via-in-pad, so this policy needs an explicit
geometry check independent of ordinary clearance DRC.
"""
from native_geometric import *
from native_fixtures import board_fixture,layers,point,mm

def checks():
 b,z=board_fixture()
 allg=geo.BoardGeometry(b,z,z.GetNetCode(),mm(.6),mm(.3),mm(.1),all_layers=True)
 assert not allg.backend.empty(allg.free)
 assert not allg.free.Contains(geo.point(allg.local((mm(3),mm(3))))),"All-layer mode bypassed existing same-net SMD pad"
 b.SetCopperLayerCount(4);pads=[]
 cases=[('rectangle',pcbnew.PAD_SHAPE_RECT,(6,6),(2,1),0,pcbnew.F_Cu),
        ('circle',pcbnew.PAD_SHAPE_CIRCLE,(12,6),(1.6,1.6),0,pcbnew.B_Cu),
        ('rotated',pcbnew.PAD_SHAPE_RECT,(18,6),(2,.8),35,pcbnew.F_Cu),
        ('oval',pcbnew.PAD_SHAPE_OVAL,(23,6),(2,1),45,pcbnew.F_Cu),
        ('rounded',pcbnew.PAD_SHAPE_ROUNDRECT,(6,14),(2,1),20,pcbnew.F_Cu),
        ('custom',pcbnew.PAD_SHAPE_CUSTOM,(17,13),(.4,.4),0,pcbnew.F_Cu),
        ('inner layer',pcbnew.PAD_SHAPE_RECT,(12,18),(1.6,1.6),0,pcbnew.In1_Cu),
        ('through hole',pcbnew.PAD_SHAPE_CIRCLE,(20,18),(1.6,1.6),0,pcbnew.F_Cu)]
 for name,shape,pos,size,angle,layer in cases:
  f=pcbnew.FOOTPRINT(b);p=pcbnew.PAD(f);p.SetNumber('1');p.SetNetCode(z.GetNetCode());p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(layers(layer));p.SetShape(shape,layer);p.SetSize(layer,point(*size));p.SetPosition(point(*pos));p.SetOrientationDegrees(angle)
  if shape==pcbnew.PAD_SHAPE_ROUNDRECT:p.SetRoundRectRadiusRatio(.25)
  if name=='custom':
   outline=engine.Polygon(tuple((mm(x),mm(y)) for x,y in ((-1,-.6),(1,-.6),(1,-.1),(.2,-.1),(.2,.7),(-1,.7))))
   p.AddPrimitivePoly(layer,geo.make(outline),0,True)
  if name=='through hole':p.SetAttribute(pcbnew.PAD_ATTRIB_PTH);p.SetLayerSet(layers(pcbnew.F_Cu,pcbnew.B_Cu));p.SetDrillSize(point(.3,.3))
  f.Add(p);b.Add(f);pads.append(p)
 g=geo.BoardGeometry(b,z,z.GetNetCode(),mm(.6),mm(.3),mm(.1))
 permitted=lambda x,y:g.free.Contains(geo.point(g.local((mm(x),mm(y)))))
 for name,_,pos,_,_,_ in cases:assert not permitted(*pos),(name,'pad center permitted')
 # Entire drill disk, not just its center. Conversely no unnecessary full-via
 # copper/foreign-net clearance is imposed on the same-net pad perimeter.
 assert not permitted(7.10,6),'Drill intersects rectangle despite center outside'
 assert not permitted(7.15,6),'Drill touching pad edge must be excluded'
 assert permitted(7.20,6),'Clear drill beside same-net pad unnecessarily excluded'
 larger=geo.BoardGeometry(b,z,z.GetNetCode(),mm(.8),mm(.5),mm(.1))
 assert not larger.free.Contains(geo.point(larger.local((mm(7.20),mm(6))))),'Configured drill radius ignored'
 assert larger.free.Contains(geo.point(larger.local((mm(7.30),mm(6))))),'Clear larger drill unnecessarily excluded'
 assert not permitted(20.70,18),'PTH annulus left open beyond its existing drill exclusion'
 # A true rotated shape, not its bounding rectangle, leaves these corners free.
 assert permitted(19,5.3),'Rotated rectangle bbox unnecessarily excluded'
 assert permitted(17.75,13.5),'Custom pad notch unnecessarily excluded'
 assert pcbnew.In1_Cu in g.layers,"Inner-layer regression not exercising enabled Cu"
 density_module=importlib.import_module(pkg.__name__+'.density_field')
 for enabled in (False,True):
  density=density_module.board_density(b,(1500000,1500000),origin=g.origin,boundaries=g.backend.polygons(g.topology)) if enabled else None
  solver=engine.Engine(g.backend,(1500000,1500000),physical_radius=g.pair_radius,anchors=g.anchors,density=density)
  points=[p for shape,anchors in g.regions() for p in solver.run_region(shape,anchors)]
  # Independent raw pad contours and analytic point-to-edge distances; do not
  # re-use the expanded obstacle under test or Engine.find's decision.
  for pad in pads:
   for layer in set(pad.GetLayerSet().Seq())&set(g.layers):
    raw=pcbnew.SHAPE_POLY_SET();pad.TransformShapeToPolygon(raw,layer,0,1000,pcbnew.ERROR_OUTSIDE)
    for poly in geo.rings(raw):
     for p in points:
      assert not poly.contains(p),('drill center in pad',enabled,p)
      distance=min(density_module.segment_distance(p,a,ring[(i+1)%len(ring)]) for ring in (poly.outer,)+poly.holes for i,a in enumerate(ring))
      assert distance>=mm(.15),('drill disk overlaps pad',enabled,p,distance)
  print('Same-net pad shapes, rotation, inner Cu, PTH and full drill exclusion; adaptive=',enabled,'vias=',len(points),'PASS',flush=True)
if __name__=='__main__':app=wx.App(False);checks()
