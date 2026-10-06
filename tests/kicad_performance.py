"""Representative synthetic 100 x 80 mm board benchmark; no user projects."""
from kicad_pipeline import *
import time

app=wx.App(False)
board,zone=board_fixture()
rect=[(0,0),(100,0),(100,80),(0,80)]
for edge,start,end in zip([d for d in board.GetDrawings() if d.GetLayer()==pcbnew.Edge_Cuts],rect,rect[1:]+rect[:1]):
    edge.SetStart(point(*start));edge.SetEnd(point(*end))
for plane in board.Zones():
    if plane.GetNetname()!='GND':continue
    poly=plane.Outline();poly.RemoveAllContours();idx=poly.NewOutline()
    for x,y in ((1,1),(99,1),(99,79),(1,79)):poly.Append(mm(x),mm(y),idx)
with tempfile.TemporaryDirectory() as tmp:
    path=Path(tmp)/'large.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    cli=os.environ.get('KICAD_CLI','/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli')
    subprocess.run([cli,'pcb','drc','--refill-zones','--save-board','--format','json','-o',str(Path(tmp)/'drc.json'),str(path)],check=True,stdout=subprocess.DEVNULL)
    results=[]
    for style in (0,3,4):
        b=pcbnew.LoadBoard(str(path));z=next(z for z in b.Zones() if z.GetZoneName()=='adaptive_fixture')
        start=time.monotonic();h=harness(b,z);h.m_cbFillStyle.SetValue(style)
        parameters=h._placement_parameters();accepted=0;tested=0
        for decision in h._decisions(parameters):
            accepted+=decision.accepted;tested+=1
        result=dict(style=module.FILL_STYLES[style],accepted=accepted,tested=tested,seconds=time.monotonic()-start)
        results.append(result);print(json.dumps(result),flush=True)
    assert results[-1]['accepted']>results[0]['accepted']
