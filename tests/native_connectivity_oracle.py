"""JSON-lines foreign-connectivity constraints for the independent spatial audit.

Reconstruct holes in one native boolean operation per original zone core, not
via Engine.find/placement replay. No private fixtures are part of this module.
"""
from native_geometric import *
app=wx.App(False);out=Path(sys.argv[1]);record=json.loads((out/'result.json').read_text())
b=pcbnew.LoadBoard(str(out/'baseline.kicad_pcb'));z=next(z for z in b.Zones() if z.GetNetname()=='GND' and z.GetZoneName())
g=geo.BoardGeometry(b,z,z.GetNetCode(),600000,300000,100000,object_clearance=0);guard=g.guard
positions=[g.local(tuple(p)) for p in record['positions']]
for r in guard.records:
 holes=pcbnew.SHAPE_POLY_SET();box=r['box'];radius=r['radius']
 for p in positions:
  if box.GetLeft()-radius<=p[0]<=box.GetRight()+radius and box.GetTop()-radius<=p[1]<=box.GetBottom()+radius:holes.Append(geo.ellipse(p,radius,radius,outside=True))
 if holes.OutlineCount():holes.Simplify();r['shape'].BooleanSubtract(holes)
 r['box']=r['shape'].BBox();r['expanded']=None
# Verify that bulk reconstruction preserves the original terminal partition.
for net in guard.baseline:
 assert not guard.disconnected(net,{}),'Final holes changed foreign terminal connectivity'
print(json.dumps({'ready':True}),flush=True)
for line in sys.stdin:
 p=tuple(json.loads(line));allowed=guard.allows(p)
 print(json.dumps({'allowed':allowed,'certificates':guard.certificates}),flush=True)
