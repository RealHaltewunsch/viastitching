"""Compare final native engine output to project-aware baseline DRC."""
import json,subprocess,sys,collections,time
from pathlib import Path
root=Path(sys.argv[1]);name=sys.argv[2];out=root/name
cli='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
t=time.monotonic()
subprocess.run([cli,'pcb','drc','--refill-zones','--all-track-errors','--format','json','-o',str(out/'geometry-drc.json'),str(out/'geometry.kicad_pcb')],check=True,stdout=subprocess.DEVNULL)
before=json.loads((out/'baseline-drc.json').read_text());after=json.loads((out/'geometry-drc.json').read_text())
key=lambda v:(v['type'],tuple(sorted(i.get('uuid','') for i in v.get('items',[]))))
base={key(v) for v in before['violations']};new=[v for v in after['violations'] if key(v) not in base]
result={'board':name,'baseline_violations':len(before['violations']),'after_violations':len(after['violations']),'new':len(new),'new_types':dict(collections.Counter(v['type'] for v in new)),'baseline_unconnected':len(before['unconnected_items']),'after_unconnected':len(after['unconnected_items']),'seconds':time.monotonic()-t,'violations':new}
(out/'drc-result.json').write_text(json.dumps(result,indent=2));print(name,result,flush=True)
assert not new,'New violations introduced'
assert len(after['unconnected_items'])<=len(before['unconnected_items'])
