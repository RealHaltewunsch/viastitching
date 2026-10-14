"""Actual SWIG geometry, determinism, completion and GUI/config regressions."""
from native_geometric import *
from native_fixtures import board_fixture,layers,point,mm
from unittest.mock import patch
import itertools,math,wx,tempfile
Dialog=importlib.import_module(pkg.__name__+'.viastitcher_dialog').ViaStitcherDialog

def places(shape,pitch=(1500000,1500000),anchors=(),origin=(0,0)):
 solver=engine.Engine(geo.Backend(origin),pitch,physical_radius=554000)
 return list(solver.run_region(shape,anchors)),solver

def exhaustive_small(shape,pts,pitch=(1500000,1500000),anchors=()):
 # Only a small regression domain; the plugin never runs this point enumeration.
 index=engine.Spacing(pitch,.8)
 for p in pts+list(anchors):index.add(p)
 for poly in geo.rings(shape):
  a,b,c,d=poly.bounds
  for y in range(engine.ceil_div(b,10000)*10000,d+1,10000):
   for x in range(engine.ceil_div(a,10000)*10000,c+1,10000):
    assert not (poly.contains((x,y)) and index.allows((x,y))),('unfilled permitted center',(x,y))

def geometry_checks():
 cases={'gap':rect(0,0,.07,3.7),'triangle':geo.make(engine.Polygon(((2000,2000),(18500,2000),(2000,18500)))), 'tiny':rect(.001,.001,.004,.004)}
 hole=rect(0,0,2,2);hole.BooleanSubtract(rect(.5,.5,1.5,1.5));cases['hole']=hole
 for name,shape in cases.items():
  pts,solver=places(shape);again,_=places(shape)
  assert pts==again
  exhaustive_small(shape,pts)
  assert solver.stats.geometry_probes<5000
  moved=geo.shift(shape,13370000,77230000);shifted,_=places(moved)
  assert sorted(shifted)==sorted((x+13370000,y+77230000) for x,y in pts),(name,'translation mismatch')
  print(name,len(pts),'geometry/translation/completion PASS',flush=True)
 a=rect(0,0,.1,5);b=geo.shift(a,8370000,0)
 pa,_=places(a);pb,_=places(b)
 solver=engine.Engine(geo.Backend(),(1500000,1500000),physical_radius=554000)
 combined=list(solver.run_region(a))+list(solver.run_region(b))
 assert combined==pa+pb,'Separated gap groups changed each other'
 print('Independent duplicate groups PASS',flush=True)
 backend=geo.Backend();solver=engine.Engine(backend,(1500000,1500000),physical_radius=554000)
 backend.active_envelopes=[('plane-a',2000000)];a_points=list(solver.run_region(a))
 backend.active_envelopes=[('plane-b',2000000)];b_points=list(solver.run_region(geo.shift(a,1600000,0)))
 assert sorted(b_points)==sorted((x+1600000,y) for x,y in a_points),'Unrelated foreign planes coupled their via groups'
 print('Foreign-plane protection scoped to its own copper region PASS',flush=True)

 p=(50000,1700000);shape=rect(0,0,.1,3.7)
 pts,_=places(shape,anchors=[p]);exhaustive_small(shape,pts,anchors=[p])
 assert all(math.dist(p,q)>=1200000 for q in pts)
 uneven,_=places(rect(0,0,3,2),pitch=(2000000,1000000));exhaustive_small(rect(0,0,3,2),uneven,pitch=(2000000,1000000))
 cancelled=engine.Engine(geo.Backend(),(1500000,1500000),pulse=lambda s:False)
 try:list(cancelled.run_region(shape));raise AssertionError('Cancel ignored')
 except engine.Cancelled:pass
 tight=engine.Engine(geo.Backend(),(1500000,1500000),minimum=1,maximum=1)
 exact=list(tight.run_region(rect(0,0,.1,8)))
 assert len(exact)==5 and all(x==50000 for x,y in exact)
 print('Existing vias, unequal pitch, 100% tolerance and cancellation PASS',flush=True)

def gui_checks():
 b,z=board_fixture();z.SetSelected();before=[b.GetLayerName(i) for i in range(pcbnew.PCB_LAYER_ID_COUNT)]
 with patch.object(pcbnew,'GetBoard',lambda:b),patch.object(pcbnew,'GetUserUnits',lambda:1),patch.object(wx,'MessageBox',lambda *a,**k:None),patch.object(pcbnew,'Refresh',lambda:None):
  d=Dialog(b);assert d.initialized
  assert not hasattr(d,'m_chkAdaptiveFill') and not hasattr(d,'m_txtHOffset')
  assert d.m_chkAllCopperLayers.GetLabel()=='Require copper connection on all layers (off: at least two)'
  d.m_txtViaSize.SetValue('.6');d.m_txtViaDrillSize.SetValue('.3');d.m_txtHSpacing.SetValue('1.5');d.m_txtVSpacing.SetValue('1.5')
  d._read_fill_settings();assert d.fill_settings['minimum']==.8
  for control,value in [(d.m_txtMinSpacing,'0'),(d.m_txtMaxSpacing,'99'),(d.m_txtHSpacing,'nan'),(d.m_txtViaDrillSize,'.7'),(d.m_txtObjectClearance,'-1')]:
   old=control.GetValue();control.SetValue(value)
   try:d._read_fill_settings();raise AssertionError('Invalid setting accepted')
   except ValueError:pass
   control.SetValue(old)
  d.Destroy();assert before==[b.GetLayerName(i) for i in range(pcbnew.PCB_LAYER_ID_COUNT)]
 print('Generated GUI, label, validation and read-only cancel PASS',flush=True)
 b,z=board_fixture();z.SetSelected()
 class Progress:
  def __init__(self,*a,**k):pass
  def Pulse(self,*a):return True,False
  def Destroy(self):pass
 with patch.object(pcbnew,'GetBoard',lambda:b),patch.object(pcbnew,'GetUserUnits',lambda:1),patch.object(wx,'MessageBox',lambda *a,**k:None),patch.object(pcbnew,'Refresh',lambda:None),patch.object(wx,'ProgressDialog',Progress):
  d=Dialog(b)
  d.m_txtViaSize.SetValue('.6');d.m_txtViaDrillSize.SetValue('.3');d.m_txtHSpacing.SetValue('1.5');d.m_txtVSpacing.SetValue('1.5');d.m_txtMinSpacing.SetValue('85');d.m_txtMaxSpacing.SetValue('140')
  d.onProcessAction(None)
  config=json.loads(d.config_textbox.GetText())[z.GetZoneName()]
  assert config['PlacementEngine']=='Geometric' and config['MinSpacingPercent']=='85' and config['MaxSpacingPercent']=='140' and 'AdaptiveFill' not in config
  manual=pcbnew.PCB_VIA(b);manual.SetPosition(point(34,23));manual.SetWidth(mm(.6));manual.SetDrill(mm(.3));manual.SetNetCode(z.GetNetCode());manual.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);manual.SetIsFree(True);b.Add(manual)
  again=Dialog(b);assert again.m_txtMinSpacing.GetValue()=='85' and again.m_txtMaxSpacing.GetValue()=='140'
  assert any(isinstance(v,pcbnew.PCB_VIA) and v.GetParentGroup() for v in b.GetTracks())
  again.ClearArea();assert [v.m_Uuid.AsString() for v in b.GetTracks() if isinstance(v,pcbnew.PCB_VIA)]==[manual.m_Uuid.AsString()]
  again.Destroy()
 print('GUI processing, saved settings and shared Clear/manual-via preservation PASS',flush=True)
 b,z=board_fixture();z.SetSelected()
 class CancelProgress(Progress):
  def Pulse(self,*a):return False,False
 with tempfile.TemporaryDirectory() as directory,patch.object(pcbnew,'GetBoard',lambda:b),patch.object(pcbnew,'GetUserUnits',lambda:1),patch.object(wx,'MessageBox',lambda *a,**k:None),patch.object(pcbnew,'Refresh',lambda:None),patch.object(wx,'ProgressDialog',CancelProgress):
  d=Dialog(b);before_file=Path(directory)/'before.kicad_pcb';after_file=Path(directory)/'after.kicad_pcb'
  pcbnew.SaveBoard(str(before_file),b);d.onProcessAction(None);pcbnew.SaveBoard(str(after_file),b)
  assert before_file.read_bytes()==after_file.read_bytes(),'Cancel during geometry altered the board'
  d.Destroy()
 print('Cancel during preparation is byte-identical/no board edits PASS',flush=True)



def board_geometry_checks():
 b,z=board_fixture();b.SetCopperLayerCount(4)
 keepout=pcbnew.ZONE(b);keepout.SetIsRuleArea(True);keepout.SetDoNotAllowVias(True);keepout.SetDoNotAllowZoneFills(False)
 keepout.SetZoneName(z.GetZoneName());keepout.SetNetCode(z.GetNetCode());keepout.SetLayerSet(layers(pcbnew.In1_Cu))
 idx=keepout.Outline().NewOutline()
 for x,y in ((14,5),(16,5),(16,7),(14,7)):keepout.Outline().Append(mm(x),mm(y),idx)
 b.Add(keepout)
 g=geo.BoardGeometry(b,z,z.GetNetCode(),mm(.6),mm(.3),0)
 assert not g.free.Contains(geo.point(g.local((mm(15),mm(6)))))
 allg=geo.BoardGeometry(b,z,z.GetNetCode(),mm(.6),mm(.3),0,all_layers=True)
 assert allg.backend.empty(allg.free),'All-layers criterion ignored missing inner copper'
 print('Same-net/name inner-layer via keepout and at-least-two/all-layers PASS',flush=True)
 for layer,bounds in [(pcbnew.In1_Cu,(14,14,24,20)),(pcbnew.In2_Cu,(8,16,20,16.3))]:
  power=pcbnew.ZONE(b);power.SetNetCode(b.GetNetcodeFromNetname('SIGNAL'));power.SetLayer(layer);power.SetMinThickness(mm(.1))
  fill=rect(*bounds);power.SetFilledPolysList(layer,fill);power.SetIsFilled(True)
  for pp in geo.rings(fill):power.Outline().Append(geo.make(pp))
  b.Add(power)
 g=geo.BoardGeometry(b,z,z.GetNetCode(),mm(.6),mm(.3),0)
 assert g.free.Contains(geo.point(g.local((mm(20),mm(18.5))))),'Broad foreign plane interior unnecessarily blocked'
 assert not g.free.Contains(geo.point(g.local((mm(12),mm(16.15))))),'Foreign thin copper neck left unprotected'
 print('Broad foreign plane interior allowed; thin connection protected PASS',flush=True)


if __name__=='__main__':
 app=wx.App(False);geometry_checks();board_geometry_checks();gui_checks()
