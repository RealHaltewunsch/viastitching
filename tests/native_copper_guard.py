"""Native foreign-plane connectivity: reject real cuts, allow alternate paths.

No private PCB files are needed. The guard's decision is distinct from ordinary
clearance checks: the latter remain the placement backend's responsibility.
"""
from native_geometric import *
from types import SimpleNamespace
from native_fixtures import layers
Guard=importlib.import_module(pkg.__name__+'.copper_guard').CopperGuard

def fixture(terminal=True,bypass=False,height=.5):
 b=pcbnew.BOARD();net=pcbnew.NETINFO_ITEM(b,'POWER');b.Add(net)
 if terminal:
  for x in (1,7):
   fp=pcbnew.FOOTPRINT(b);pad=pcbnew.PAD(fp);pad.SetNet(net);pad.SetPosition(geo.point((pcbnew.FromMM(x),pcbnew.FromMM(height/2))))
   pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT,pcbnew.F_Cu);pad.SetSize(geo.point((200000,200000)));pad.SetLayerSet(layers(pcbnew.F_Cu));fp.Add(pad);b.Add(fp)
 if bypass:
  for p,q in [((1,height/2),(1,4)),((1,4),(7,4)),((7,4),(7,height/2))]:
   t=pcbnew.PCB_TRACK(b);t.SetNet(net);t.SetLayer(pcbnew.F_Cu);t.SetWidth(200000);t.SetStart(geo.point(tuple(pcbnew.FromMM(v) for v in p)));t.SetEnd(geo.point(tuple(pcbnew.FromMM(v) for v in q)));b.Add(t)
 g=SimpleNamespace(board=b,layers=[pcbnew.F_Cu],diameter=600000,local_shape=geo.copy,pulse_at=lambda *args:None)
 guard=Guard(g);guard.add(net.GetNetCode(),pcbnew.F_Cu,rect(0,0,8,height),200000,100000);guard.prepare();return guard

def checks():
 cut=(4000000,250000)
 guard=fixture();assert not guard.allows(cut),'Sole connection between pads severed'
 assert guard.certificates,'No geometric rejection certificate created'
 center,radius=guard.certificates[0]
 assert radius>10000
 count=guard.graph_checks
 assert not guard.allows((cut[0]+radius//2,cut[1]))
 assert guard.graph_checks==count,'Certified position repeated graph search'
 assert guard.forbidden_box((cut[0]-10000,cut[1]-10000,cut[0]+10000,cut[1]+10000))
 # Independent fresh guards without certificate reuse confirm actual rejection
 # at samples around the certified disk, not merely cached decisions.
 for dx,dy in ((radius,0),(-radius,0),(0,radius),(0,-radius)):
  raw=fixture();raw.certify=lambda *args:None
  assert not raw.allows((cut[0]+dx,cut[1]+dy))
 assert fixture().allows((4000000,1500000)), 'Valid off-neck placement rejected'
 assert fixture(terminal=False).allows(cut),'Unanchored copper fragment excluded'
 assert fixture(bypass=True).allows(cut),'Alternate fixed-copper connection ignored'
 guard=fixture(height=3)
 for p in ((4000000,450000),(4000000,1500000)):
  assert guard.allows(p);guard.commit(p)
 assert not guard.allows((4000000,2550000)),'Accumulated holes disconnected pads'
 print('Foreign terminal cuts, harmless fragments, alternate paths, accumulated holes PASS',flush=True)
if __name__=='__main__':app=wx.App(False);checks()
