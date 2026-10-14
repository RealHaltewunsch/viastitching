"""Native geometry-driven placement checks; synthetic or disposable board copies."""
import sys,types,importlib,json,time,shutil,os
from dataclasses import asdict
from pathlib import Path
import pcbnew
import wx
ROOT=Path(os.environ.get("GEOMETRIC_TEST_ROOT",str(Path(__file__).resolve().parents[1])))
pkg=types.ModuleType('geometric_test');pkg.__path__=[str(ROOT)];sys.modules[pkg.__name__]=pkg
geo=importlib.import_module(pkg.__name__+'.native_geometry');engine=importlib.import_module(pkg.__name__+'.geometric_engine')

def rect(a,b,c,d):return geo.make(engine.Polygon(tuple((pcbnew.FromMM(x),pcbnew.FromMM(y)) for x,y in ((a,b),(c,b),(c,d),(a,d)))))
def basic():
 backend=geo.Backend();shape=rect(0,0,.1,8)
 solver=engine.Engine(backend,(pcbnew.FromMM(1.5),)*2,physical_radius=pcbnew.FromMM(.554))
 pts=list(solver.run_region(shape))
 assert pts and all(x%10000==y%10000==0 for x,y in pts)
 shift=(pcbnew.FromMM(13.37),pcbnew.FromMM(77.23))
 backend2=geo.Backend(shift);solver2=engine.Engine(backend2,(pcbnew.FromMM(1.5),)*2,physical_radius=pcbnew.FromMM(.554))
 shifted=list(solver2.run_region(shape))
 assert shifted==[(x+shift[0],y+shift[1]) for x,y in pts]
 print('Synthetic narrow gap',len(pts),solver.stats,flush=True)

def run(name,out):
 source=Path(os.environ.get('GEOMETRIC_VALIDATION_ROOT',str(out.parent)))/name/'baseline.kicad_pcb'
 b=pcbnew.LoadBoard(str(source))
 if '--shift' in sys.argv:
  delta=geo.point((13370000,77230000))
  for item in list(b.GetDrawings())+list(b.GetTracks())+list(b.Zones())+list(b.GetFootprints()):item.Move(delta)
 z=next(z for z in b.Zones() if z.GetNetname()=='GND' and z.GetZoneName())
 # Use the saved reference fill; item moves preserve filled polygon geometry.
 # Final CLI DRC explicitly refills with associated project rules.
 start=time.monotonic();last=[start]
 def pulse(stage,n):
  if time.monotonic()-last[0]>5:print(name,stage,n,'elapsed',round(time.monotonic()-start,1),flush=True);last[0]=time.monotonic()
  return True
 g=geo.BoardGeometry(b,z,z.GetNetCode(),pcbnew.FromMM(.6),pcbnew.FromMM(.3),pcbnew.FromMM(.1),all_layers=('--all' in sys.argv),object_clearance=0,pulse=pulse)
 built=time.monotonic()-start
 solver=engine.Engine(g.backend,(pcbnew.FromMM(1.5),)*2,pulse=lambda s:pulse('Place',s.placed),physical_radius=g.pair_radius)
 pts=[];stats=[]
 for shape,anchors in g.regions():
  added=list(solver.run_region(shape,anchors));pts.extend(added);stats.append({'new':len(added),'anchors':anchors,'positions':added,'polygons':[asdict(p) for p in g.backend.polygons(shape)]})
 duration=time.monotonic()-start
 group=next((g for g in b.Groups() if g.GetName()=='VIA_STITCHING_GROUP'+z.GetZoneName()),None)
 if group is None:
  group=pcbnew.PCB_GROUP(b);group.SetName('VIA_STITCHING_GROUP'+z.GetZoneName());b.Add(group)
 ids=[]
 for p in pts:
  v=pcbnew.PCB_VIA(b);v.SetPosition(geo.point(p));v.SetWidth(pcbnew.FromMM(.6));v.SetDrill(pcbnew.FromMM(.3));v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNetCode(z.GetNetCode());v.SetIsFree(True);b.Add(v);group.AddItem(v);ids.append(v.m_Uuid.AsString())
 assert all(x%10000==0 and y%10000==0 for x,y in pts)
 out.mkdir(parents=True,exist_ok=True)
 pcbnew.SaveBoard(str(out/'geometry.kicad_pcb'),b)
 for ext in ('.kicad_pro','.kicad_dru'):
  f=source.with_suffix(ext)
  if f.exists():shutil.copy2(f,out/('geometry'+ext))
 result={'origin':g.origin,'name':name,'count':len(pts),'build_seconds':built,'seconds':duration,'stats':vars(solver.stats),'regions':stats,'positions':pts,'ids':ids}
 (out/'result.json').write_text(json.dumps(result))
 print(name,'COMPLETE',len(pts),round(duration,3),vars(solver.stats),flush=True)
if __name__=='__main__':
 app=wx.App(False)
 if len(sys.argv)==1:basic()
 else:run(sys.argv[1],Path(sys.argv[2]))
