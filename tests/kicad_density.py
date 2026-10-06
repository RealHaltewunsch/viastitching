"""Native shape extraction, sparse patterns, refill and cancellation regressions."""
import math
import random
from pathlib import Path
from unittest.mock import patch
from kicad_integration import *


def run_density(output):
    output.mkdir(parents=True,exist_ok=True)
    results={}
    for style in range(3):
        original,zone=board_fixture()
        pcbnew.SaveBoard(str(output/'source.kicad_pcb'),original)
        runs={}
        for enabled in (False,True):
            board=pcbnew.LoadBoard(str(output/'source.kicad_pcb'))
            zone=next(z for z in board.Zones() if z.GetZoneName()=='adaptive_fixture')
            h=harness(board,zone,style=style)
            h.m_txtHSpacing.SetValue('1.5');h.m_txtVSpacing.SetValue('1.5')
            h.m_chkSparse.SetValue(enabled);h._read_fill_settings()
            field=module.board_density(board,(mm(1.5),mm(1.5)),1,3,3)
            random.seed(42);h.FillupArea()
            grid=spacing_snapshot(board)
            near={p for p in grid.values() if field.factor(p)==1}
            far=sum(field.factor(p)==3 for p in grid.values())
            runs[enabled]=(len(grid),near,far)
            if enabled:
                before=spacing_snapshot(board)
                pcbnew.SaveBoard(str(output/('before_%d.kicad_pcb'%style)),board)
                r=h._refill((0,0),style==1)
                assert not r.cancelled and not r.limited
                checked=list(before.values())
                for uid,p in spacing_snapshot(board).items():
                    if uid in before:continue
                    assert all(math.hypot((p[0]-q[0])/mm(1.5),(p[1]-q[1])/mm(1.5))+1e-12 >=
                               .8*max(field.factor(p),field.factor(q)) for q in checked)
                    checked.append(p)
                pcbnew.SaveBoard(str(output/('after_%d.kicad_pcb'%style)),board)
                h.ClearArea();assert not vias(board)
        assert runs[True][0]<runs[False][0],runs
        assert runs[True][1]==runs[False][1],runs
        assert runs[True][2]<runs[False][2],runs
        results[style]={str(k):dict(total=v[0],near=len(v[1]),far=v[2]) for k,v in runs.items()}
    # Native polygons follow rotated pad contours, track width and arc shape.
    board=pcbnew.BOARD();board.SetCopperLayerCount(2)
    fp=pcbnew.FOOTPRINT(board);board.Add(fp)
    for shape,pos,size in [(pcbnew.PAD_SHAPE_CIRCLE,(10,10),(2,2)),
                           (pcbnew.PAD_SHAPE_OVAL,(20,10),(4,2)),
                           (pcbnew.PAD_SHAPE_RECT,(30,10),(4,2)),
                           (pcbnew.PAD_SHAPE_ROUNDRECT,(40,10),(4,2))]:
        pad=pcbnew.PAD(fp);pad.SetPosition(point(*pos));pad.SetSize(point(*size))
        pad.SetShape(shape,pcbnew.F_Cu);pad.SetLayerSet(layers(pcbnew.F_Cu));fp.Add(pad)
    track=pcbnew.PCB_TRACK(board);track.SetStart(point(0,0));track.SetEnd(point(5,0));track.SetWidth(mm(1));track.SetLayer(pcbnew.B_Cu);board.Add(track)
    arc=pcbnew.PCB_ARC(board);arc.SetStart(point(0,20));arc.SetMid(point(5,25));arc.SetEnd(point(10,20));arc.SetWidth(mm(1));arc.SetLayer(pcbnew.F_Cu);board.Add(arc)
    f=module.board_density(board,(mm(1),mm(1)),1,3,3)
    for p in [(10,10),(20,10),(30,10),(40,10),(2,0),(5,25)]:assert f.distance((mm(p[0]),mm(p[1])))==0,p
    assert abs(f.distance((mm(2),mm(1.5)))-1)<.003
    assert abs(f.distance((mm(5),mm(26.5)))-1)<.003
    assert f.distance((mm(10.9),mm(10.9)))>.2
    # Vias and planes, including foreign-net planes, never become references.
    v=pcbnew.PCB_VIA(board);v.SetPosition(point(60,60));v.SetWidth(mm(2));v.SetDrill(mm(.5));v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(v)
    assert module.board_density(board,(mm(1),mm(1)),1,3,3).factor((mm(60),mm(60)))==3
    board,zone=board_fixture();h=harness(board,zone,adaptive=True)
    h.m_chkSparse.SetValue(True);h.m_txtDensityStart.SetValue('125');h.m_txtDensityEnd.SetValue('400');h.m_txtDensityMultiple.SetValue('4')
    h.onProcessAction(None)
    saved=json.loads(h.config_textbox.GetText())['adaptive_fixture']
    assert saved['SparseGrid'] and saved['DensityStartPercent']=='125' and saved['DensityMultiple']=='4'
    board,zone=board_fixture();h=harness(board,zone);h.m_chkSparse.SetValue(True);h.m_txtDensityMultiple.SetValue('1.5')
    h.onProcessAction(None);assert h.config_textbox is None and not vias(board)
    board,zone=board_fixture();h=harness(board,zone);h.m_chkSparse.SetValue(True);h._read_fill_settings()
    class Cancel(Progress):
        def Pulse(self,*args):return False,False
    with patch.object(wx,'ProgressDialog',Cancel):h.FillupArea()
    assert not vias(board)
    print(json.dumps(results,indent=2));print('Native density shapes, patterns, settings, spacing and cancellation PASS')

if __name__=='__main__':
    app=wx.App(False)
    with patch.object(wx,'MessageBox',lambda *a,**k:None),patch.object(wx,'ProgressDialog',Progress),patch.object(pcbnew,'Refresh',lambda:None):
        run_density(Path(sys.argv[1]))
