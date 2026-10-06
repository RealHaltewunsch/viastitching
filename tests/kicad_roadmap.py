"""Native integration checks for the local roadmap implementation."""
from kicad_pipeline import *


def run_roadmap(out):
    out.mkdir(parents=True,exist_ok=True)
    board,zone=board_fixture()
    baseline=out/'reference.kicad_pcb';pcbnew.SaveBoard(str(baseline),board)
    for style in range(5):
        b=pcbnew.LoadBoard(str(baseline));z=next(z for z in b.Zones() if z.GetZoneName()=='adaptive_fixture')
        h=harness(b,z);h.m_cbFillStyle.SetValue(style)
        parameters=h._placement_parameters();before=out/('before_%s.kicad_pcb'%style);pcbnew.SaveBoard(str(before),b)
        decisions=list(h._decisions(parameters));planned=[d.position for d in decisions if d.accepted]
        preview_copy=out/'preview_check.kicad_pcb';pcbnew.SaveBoard(str(preview_copy),b)
        assert before.read_bytes()==preview_copy.read_bytes(),'Preview modified board'
        assert planned==[d.position for d in h._decisions(parameters) if d.accepted]
        with patch.object(wx,'MessageBox',lambda *a,**k:None),patch.object(pcbnew,'Refresh',lambda:None),patch.object(wx,'ProgressDialog',Progress):h.FillupArea()
        assert sorted(planned)==positions(b),(style,'preview/placement mismatch')
        pcbnew.SaveBoard(str(out/('after_%s.kicad_pcb'%style)),b)
        manual=pcbnew.PCB_VIA(b);manual.SetPosition(point(34,23));manual.SetWidth(mm(.6));manual.SetDrill(mm(.3));manual.SetNetCode(b.GetNetcodeFromNetname('GND'));b.Add(manual)
        with patch.object(wx,'MessageBox',lambda *a,**k:None),patch.object(pcbnew,'Refresh',lambda:None):h.ClearArea()
        assert positions(b)==[(mm(34),mm(23))],'Clear removed a manual via or left generated vias'
        print('Mode',style,'accepted',len(planned),'preview/read-only/placement/clear PASS',flush=True)
    # Increasing either clearance can only remove fixed-grid candidates.
    for control in ('m_txtClearance','m_txtObjectClearance'):
        sets=[]
        for value in ('0','.5','1'):
            b=pcbnew.LoadBoard(str(baseline));z=next(z for z in b.Zones() if z.GetZoneName()=='adaptive_fixture')
            h=harness(b,z);getattr(h,control).SetValue(value)
            sets.append({d.position for d in h._decisions(h._placement_parameters()) if d.accepted})
        assert sets[2]<=sets[1]<=sets[0],control
    print('Independent clearance monotonicity PASS',flush=True)
    b=pcbnew.LoadBoard(str(baseline));z=next(z for z in b.Zones() if z.GetZoneName()=='adaptive_fixture')
    h=harness(b,z);h.m_chkCenterSegments.SetValue(True)
    parameters=h._placement_parameters()
    planned=[d.position for d in h._decisions(parameters) if d.accepted]
    assert planned and planned==[d.position for d in h._decisions(parameters) if d.accepted]
    pcbnew.SaveBoard(str(out/'before_5.kicad_pcb'),b)
    for position in planned:h.PlaceVia(position,parameters)
    pcbnew.SaveBoard(str(out/'after_5.kicad_pcb'),b)
    print('Segment centering deterministic, accepted',len(planned),flush=True)
    # A via-only keepout must block placement even though filled copper exists.
    b=pcbnew.LoadBoard(str(baseline));z=next(z for z in b.Zones() if z.GetZoneName()=='adaptive_fixture')
    keepout=pcbnew.ZONE(b);keepout.SetIsRuleArea(True)
    keepout.SetLayerSet(layers(pcbnew.F_Cu,pcbnew.B_Cu));keepout.SetDoNotAllowVias(True);keepout.SetDoNotAllowZoneFills(False)
    idx=keepout.Outline().NewOutline()
    for x,y in ((14,5),(16,5),(16,7),(14,7)):keepout.Outline().Append(mm(x),mm(y),idx)
    b.Add(keepout);h=harness(b,z);parameters=h._placement_parameters();h.clearance=parameters[2]
    assert h.ValidateCandidate((mm(15),mm(6)),parameters)=='collision'
    print('Via-only keepout PASS',flush=True)
    # Through-vias must avoid inner-layer pads even if the selected zone is F/B.
    b=pcbnew.LoadBoard(str(baseline));b.SetCopperLayerCount(4)
    z=next(z for z in b.Zones() if z.GetZoneName()=='adaptive_fixture')
    fp=pcbnew.FOOTPRINT(b);fp.SetPosition(point(6,6))
    pad=pcbnew.PAD(fp);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(layers(pcbnew.In1_Cu))
    pad.SetShape(pcbnew.PAD_SHAPE_RECT,pcbnew.In1_Cu);pad.SetSize(point(1,1));pad.SetPosition(point(6,6))
    pad.SetNetCode(b.GetNetcodeFromNetname('SIGNAL'));fp.Add(pad);b.Add(fp)
    h=harness(b,z);parameters=h._placement_parameters();h.clearance=parameters[2]
    assert h.ValidateCandidate((mm(6),mm(6)),parameters)=='collision'
    print('Four-layer through-via collision PASS',flush=True)
    # Opening and cancelling the real generated dialog must not rename layers.
    b=pcbnew.LoadBoard(str(baseline));z=next(z for z in b.Zones() if z.GetZoneName()=='adaptive_fixture');z.SetSelected()
    before=[b.GetLayerName(i) for i in range(pcbnew.PCB_LAYER_ID_COUNT)]
    with patch.object(pcbnew,'GetBoard',lambda:b),patch.object(pcbnew,'GetUserUnits',lambda:1):
        d=Dialog(b);assert d.initialized
        for style in range(5):
            d.m_cbFillStyle.SetSelection(style);d._settings_changed()
            assert d.m_txtMinDistance.IsEnabled()==(style==4)
            assert d.m_txtHSpacing.IsEnabled()==(style!=4)
            assert d.m_chkCenterSegments.IsEnabled()==(style in (0,1))
        d.m_cbFillStyle.SetSelection(0);d.m_chkPreview.SetValue(True);d._settings_changed();d._preview_debounce.Stop()
        d._start_preview()
        while d._preview_timer.IsRunning():d._preview_tick(None)
        assert d._preview_counts['accepted']>0
        assert d.m_lblPreviewStatus.GetLabel()
        d._stop_preview();d.Destroy()
    assert before==[b.GetLayerName(i) for i in range(pcbnew.PCB_LAYER_ID_COUNT)]
    print('GUI mode switching and read-only cancellation PASS',flush=True)

if __name__=='__main__':
    app=wx.App(False)
    run_roadmap(Path(sys.argv[1]))
