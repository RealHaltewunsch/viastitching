"""Confirm current committed-candidate code reproduces the DRC-tested positions."""
from native_geometric import *
name=sys.argv[1];out=Path(sys.argv[2]);app=wx.App(False)
b=pcbnew.LoadBoard(str(out/'baseline.kicad_pcb'));z=next(z for z in b.Zones() if z.GetNetname()=='GND' and z.GetZoneName())
start=time.monotonic()
g=geo.BoardGeometry(b,z,z.GetNetCode(),600000,300000,100000,object_clearance=0)
record=json.loads((out/'result.json').read_text())
density=None
if record.get('adaptive_density'):
 density=importlib.import_module(pkg.__name__+'.density_field').board_density(b,(1500000,1500000),origin=g.origin,boundaries=g.backend.polygons(g.topology))
solver=engine.Engine(g.backend,(1500000,1500000),physical_radius=g.pair_radius,density=density)
positions=[p for shape,anchors in g.regions() for p in solver.run_region(shape,anchors)]
expected=json.loads((out/'result.json').read_text())['positions']
assert positions==[tuple(p) for p in expected],'Current source changed DRC-tested placement'
(out/'replay-result.json').write_text(json.dumps({'identical':True,'count':len(positions),'geometry_probes':solver.stats.geometry_probes,'seconds':time.monotonic()-start},indent=2))
print(name,'Replay identical',len(positions),flush=True)
