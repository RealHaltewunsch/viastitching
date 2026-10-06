"""Compare full KiCad DRC identities before/after every placement mode."""
import json
import os
from pathlib import Path
import subprocess
import sys

root=Path(sys.argv[1])
cli=os.environ.get('KICAD_CLI','/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli')
for style in range(6):
    reports=[]
    for stage in ('before','after'):
        path=root/('%s_%s.kicad_pcb'%(stage,style))
        report=path.with_suffix('.json')
        subprocess.run([cli,'pcb','drc','--refill-zones','--all-track-errors','--format','json','-o',str(report),str(path)],check=True,stdout=subprocess.DEVNULL)
        reports.append(json.loads(report.read_text()))
    def key(v):return v['type'],tuple(sorted(i.get('uuid','') for i in v.get('items',[])))
    before,after=reports
    new={key(v) for v in after['violations']}-{key(v) for v in before['violations']}
    print('Mode',style,'new violations',new,'unconnected',len(after['unconnected_items']),flush=True)
    assert not new
    assert len(after['unconnected_items'])<=len(before['unconnected_items'])
