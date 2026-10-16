"""Check generated drill disks against native, unexpanded pad shapes.

This checks the manufacturing policy electrical DRC does not enforce. Existing
manual vias are reported neither as generated nor as errors introduced here.
"""
import sys,json
from pathlib import Path
import pcbnew,wx
app=wx.App(False);out=Path(sys.argv[1]);record=json.loads((out/'result.json').read_text());board=pcbnew.LoadBoard(str(out/'geometry.kicad_pcb'));ids=set(record['ids']);vias=[v for v in board.GetTracks() if isinstance(v,pcbnew.PCB_VIA) and v.m_Uuid.AsString() in ids]
cu=set(l for l in board.GetEnabledLayers().Seq() if pcbnew.IsCopperLayer(l));collisions=[];pad_count=0
for fp in board.GetFootprints():
 for pad in fp.Pads():
  common=cu&set(pad.GetLayerSet().Seq())
  if not common:continue
  pad_count+=1;box=pad.GetBoundingBox();shapes={layer:pad.GetEffectiveShape(layer) for layer in sorted(common)}
  for via in vias:
   p=via.GetPosition();r=via.GetDrillValue()//2
   if not (box.GetLeft()-r<=p.x<=box.GetRight()+r and box.GetTop()-r<=p.y<=box.GetBottom()+r):continue
   drill=pcbnew.SHAPE_CIRCLE(p,r)
   for layer,shape in shapes.items():
    if shape.Collide(drill,0):
     collisions.append({'via':via.m_Uuid.AsString(),'pad':pad.m_Uuid.AsString(),'same_net':via.GetNetCode()==pad.GetNetCode(),'layer':int(layer),'position':[p.x,p.y]})
result={'generated_vias':len(vias),'copper_pads':pad_count,'drill_pad_overlaps':len({c['via'] for c in collisions}),'collisions':collisions};(out/'pad-audit.json').write_text(json.dumps(result,indent=2));print(out.name,{k:v for k,v in result.items() if k!='collisions'},flush=True)
if '--expect-clean' in sys.argv:assert not collisions,'Generated drill intersects a pad'
