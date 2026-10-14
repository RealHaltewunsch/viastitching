"""Read-only center-domain snapshot for independent verification."""
from native_geometric import *
from dataclasses import asdict
out=Path(sys.argv[1]);name=out.name
app=wx.App(False)
b=pcbnew.LoadBoard(str(out/'baseline.kicad_pcb'));z=next(z for z in b.Zones() if z.GetNetname()=='GND' and z.GetZoneName())
g=geo.BoardGeometry(b,z,z.GetNetCode(),600000,300000,100000,object_clearance=0)
r=json.loads((out/'result.json').read_text());records=[];offset=0
for (shape,anchors),stats in zip(g.regions(),r['regions']):
 ps=r['positions'][offset:offset+stats['new']];offset+=len(ps)
 assert len(anchors)==(stats['anchors'] if isinstance(stats['anchors'],int) else len(stats['anchors']))
 records.append({'envelopes':g.backend.active_envelopes,'polygons':[asdict(p) for p in g.backend.polygons(shape)],'anchors':anchors,'positions':[[x-g.origin[0],y-g.origin[1]] for x,y in ps]})
assert offset==len(r['positions'])
data={'origin':g.origin,'pitch':[1500000,1500000],'minimum':[4,5],'physical_radius':g.pair_radius,'regions':records,'all_positions':r['positions']}
if r.get('adaptive_density'):
 density_module=importlib.import_module(pkg.__name__+'.density_field')
 field=density_module.board_density(b,(1500000,1500000),origin=g.origin,boundaries=g.backend.polygons(g.topology))
 # Normalized contours are exported to the independent Shapely verifier.
 data['density']={'start':field.start,'end':field.end,'multiple':field.multiple,'polygons':[asdict(p) for p in field.polygons],'boundaries':[asdict(p) for p in field.boundaries]}
(out/'audit-data.json').write_text(json.dumps(data))
print(name,'center-domain snapshot ready',flush=True)
