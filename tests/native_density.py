"""Native copper contours, variable density, disabled parity and GUI persistence."""
from native_geometric import *
from native_fixtures import point,mm,layers,board_fixture
from unittest.mock import patch
Density=importlib.import_module(pkg.__name__+'.density_field')
Dialog=importlib.import_module(pkg.__name__+'.viastitcher_dialog').ViaStitcherDialog

def contour_checks():
 b=pcbnew.BOARD();b.SetCopperLayerCount(4)
 track=pcbnew.PCB_TRACK(b);track.SetStart(point(0,0));track.SetEnd(point(5,0));track.SetWidth(mm(.4));track.SetLayer(pcbnew.F_Cu);b.Add(track)
 arc=pcbnew.PCB_ARC(b);arc.SetStart(point(10,10));arc.SetMid(point(11,11));arc.SetEnd(point(10,12));arc.SetWidth(mm(.4));arc.SetLayer(pcbnew.In1_Cu);b.Add(arc)
 f=Density.board_density(b,(1000000,1000000))
 assert abs(f.distance((mm(2),mm(.7)))-.5)<.002
 assert abs(f.distance((mm(11.7),mm(11)))-.5)<.002
 assert f.distance((mm(2),0))==0
 before=[f.factor((mm(x),mm(y))) for x,y in ((2,.7),(11.7,11),(30,30))]
 via=pcbnew.PCB_VIA(b);via.SetPosition(point(30,30));via.SetWidth(mm(.6));via.SetDrill(mm(.3));via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(via)
 zone=pcbnew.ZONE(b);zone.SetLayer(pcbnew.F_Cu);zone.SetFilledPolysList(pcbnew.F_Cu,rect(25,25,35,35));zone.SetIsFilled(True);b.Add(zone)
 again=Density.board_density(b,(1000000,1000000))
 assert before==[again.factor((mm(x),mm(y))) for x,y in ((2,.7),(11.7,11),(30,30))]
 for shape,size,test,expected in [
  (pcbnew.PAD_SHAPE_CIRCLE,(2,2),(6.5,5),.5),
  (pcbnew.PAD_SHAPE_OVAL,(4,2),(7.5,5),.5),
  (pcbnew.PAD_SHAPE_RECT,(4,2),(7.5,6),.5),
  (pcbnew.PAD_SHAPE_ROUNDRECT,(4,2),(7.5,5),.5)]:
  board=pcbnew.BOARD();fp=pcbnew.FOOTPRINT(board);pad=pcbnew.PAD(fp);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.B_Cu,shape);pad.SetSize(pcbnew.B_Cu,point(*size));pad.SetLayerSet(layers(pcbnew.B_Cu));pad.SetPosition(point(5,5));fp.Add(pad);board.Add(fp)
  f=Density.board_density(board,(1000000,1000000))
  assert abs(f.distance((mm(test[0]),mm(test[1])))-expected)<.002,(shape,f.distance((mm(test[0]),mm(test[1]))))
  assert f.distance((mm(5),mm(5)))==0
  pad.SetOrientation(pcbnew.EDA_ANGLE(45,pcbnew.DEGREES_T))
  rotated=Density.board_density(board,(1000000,1000000));assert rotated.distance((mm(5),mm(5)))==0
 print('Actual track widths, arcs on inner copper, round/oval/rect/roundrect and rotated pads PASS',flush=True)
 try:Density.board_density(b,(1000000,1000000),pulse=lambda n:False);raise AssertionError('Density cancellation ignored')
 except engine.Cancelled:pass
 print('Zone fills and existing/generated vias leave density unchanged; density cancellation PASS',flush=True)


def engine_checks():
 shape=rect(0,0,8,8);pitch=(1500000,1500000)
 dense=engine.Engine(geo.Backend(),pitch);a=list(dense.run_region(shape))
 f=Density.DensityField([],pitch);sparse=engine.Engine(geo.Backend(),pitch,density=f);b=list(sparse.run_region(shape))
 assert 0<len(b)<len(a)/3,(len(a),len(b))
 for p in b:
  for q in b:
   if p!=q:assert ((p[0]-q[0])/pitch[0])**2+((p[1]-q[1])/pitch[1])**2 >= (.8*3)**2-1e-12
 unity=Density.DensityField([],pitch,multiple=1)
 assert list(engine.Engine(geo.Backend(),pitch,density=unity).run_region(shape))==a
 near=Density.DensityField([engine.Polygon(((-10000000,-10000000),(20000000,-10000000),(20000000,20000000),(-10000000,20000000)))],pitch)
 assert list(engine.Engine(geo.Backend(),pitch,density=near).run_region(shape))==a
 repeat=list(engine.Engine(geo.Backend(),pitch,density=f).run_region(shape));assert b==repeat
 shift=(13370000,77230000)
 moved=list(engine.Engine(geo.Backend(shift),pitch,density=Density.DensityField([],pitch)).run_region(shape))
 assert moved==[(x+shift[0],y+shift[1]) for x,y in b]
 anchored=engine.Engine(geo.Backend(),pitch,density=f)
 additions=list(anchored.run_region(shape,[(4000000,4000000)]));check=f.spacing(.8);check.add((4000000,4000000))
 for p in additions:assert check.allows(p);check.add(p)
 # Small transition strip: independent exhaustive regression only, not production.
 pitch=(1000000,1000000);f=Density.DensityField([engine.Polygon(((-10000,-10000),(0,-10000),(0,1000000),(-10000,1000000)))],pitch)
 transition=rect(.5,0,4.2,.2);solver=engine.Engine(geo.Backend(),pitch,density=f);points=list(solver.run_region(transition))
 check=f.spacing(.8)
 for p in points:assert check.allows(p);check.add(p)
 for x in range(500000,4200001,10000):
  for y in range(0,200001,10000):assert not check.allows((x,y)),('Unfilled transition center',(x,y))
 print('Near parity, factor-one parity, far reduction, unequal factor pairs, anchors, transition completion and translation PASS',flush=True)


def boundary_checks():
 pitch=(1500000,1500000);shape=rect(0,0,20,20)
 field=Density.DensityField([],pitch,boundaries=geo.rings(shape))
 field.protected=Density.protected_geometry(field)
 solver=engine.Engine(geo.Backend(),pitch,density=field)
 pts=list(solver.run_region(shape))
 assert any(field.factor(p)==3 for p in pts),'No sparse interior placed'
 assert any(field.factor(p)==1 for p in pts),'No dense edge band placed'
 interior=False
 for p in pts:
  distance=min(p[0],p[1],20000000-p[0],20000000-p[1])/1500000
  assert abs(field.distance(p)-min(3,distance))<1e-12
  if distance<=1:assert field.factor(p)==1
  if distance>1.01:interior=True
  elif interior:raise AssertionError('Interior placement preceded the protected edge band')
  if field.factor(p)>1:assert distance>1
 check=field.spacing(.8)
 for p in pts:assert check.allows(p);check.add(p)
 # Ensure interior vias cannot consume a still-insertable dense edge position.
 for x in range(0,20000001,50000):
  for y in (0,500000,1000000,1500000,18500000,19000000,19500000,20000000):
   assert not check.allows((x,y)),('Edge band unfilled',(x,y))
 hole=rect(6,6,10,10);with_hole=geo.copy(shape);with_hole.BooleanSubtract(hole)
 f=Density.DensityField([],pitch,boundaries=geo.rings(with_hole));f.protected=Density.protected_geometry(f)
 assert f.factor((5000000,8000000))==1
 assert f.protected.Contains(geo.point((5000000,8000000)))
 strip=rect(0,0,2,10);f=Density.DensityField([],pitch,boundaries=geo.rings(strip));f.protected=Density.protected_geometry(f)
 baseline=list(engine.Engine(geo.Backend(),pitch).run_region(strip))
 guarded=list(engine.Engine(geo.Backend(),pitch,density=f).run_region(strip))
 assert guarded==baseline,'Narrow island was thinned'
 print('Dense edge band placed before sparse interior; holes, thin islands, local factors and edge coverage PASS',flush=True)


def gui_checks():
 b,z=board_fixture();z.SetSelected()
 class Progress:
  def __init__(self,*a,**k):pass
  def Pulse(self,*a):return True,False
  def Destroy(self):pass
 with patch.object(pcbnew,'GetBoard',lambda:b),patch.object(pcbnew,'GetUserUnits',lambda:1),patch.object(wx,'MessageBox',lambda *a,**k:None),patch.object(pcbnew,'Refresh',lambda:None),patch.object(wx,'ProgressDialog',Progress):
  d=Dialog(b);assert not d.m_chkSparse.GetValue();assert not d.m_txtDensityMultiple.IsEnabled()
  d.m_chkSparse.SetValue(True);d.onDensityChanged();assert d.m_txtDensityMultiple.IsEnabled()
  d.m_txtViaSize.SetValue('.6');d.m_txtViaDrillSize.SetValue('.3')
  for name,value in [('DensityStart','99'),('DensityEnd','100'),('DensityMultiple','2.5'),('DensityMultiple','0'),('DensityStart','nan'),('DensityEnd','inf')]:
   control=getattr(d,'m_txt'+name);old=control.GetValue();control.SetValue(value)
   try:d._read_fill_settings();raise AssertionError('Invalid density accepted')
   except ValueError:pass
   control.SetValue(old)
  d.m_txtDensityStart.SetValue('125');d.m_txtDensityEnd.SetValue('400');d.m_txtDensityMultiple.SetValue('4')
  d.onProcessAction(None)
  again=Dialog(b);assert again.m_chkSparse.GetValue();assert again.m_txtDensityStart.GetValue()=='125';assert again.m_txtDensityEnd.GetValue()=='400';assert again.m_txtDensityMultiple.GetValue()=='4'
  config=json.loads(again.config_textbox.GetText())[z.GetZoneName()]
  assert config['AdaptiveDensity'] and config['PlacementEngine']=='Geometric'
  again.ClearArea();assert not any(isinstance(v,pcbnew.PCB_VIA) for v in b.GetTracks());again.Destroy()
 print('Checkbox, default-off, lower bound, invalid limits, per-zone persistence and Clear PASS',flush=True)

if __name__=='__main__':
 app=wx.App(False);contour_checks();engine_checks();boundary_checks();gui_checks()
