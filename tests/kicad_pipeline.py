"""Run with KiCad's Python. Creates only synthetic boards in the output directory.

Usage: <kicad-python> tests/kicad_integration.py /tmp/viastitcher-check
Then run kicad-cli pcb drc --refill-zones --format json on before/after boards.
"""
import importlib
import json
from pathlib import Path
import random
import sys
import subprocess
import tempfile
import os
import types
from unittest.mock import patch

import pcbnew
import wx

ROOT = Path(os.environ.get('VIASTITCHER_TEST_ROOT', str(Path(__file__).resolve().parents[1])))
pkg = types.ModuleType('viastitcher_test_package')
pkg.__path__ = [str(ROOT)]
sys.modules[pkg.__name__] = pkg
module = importlib.import_module(pkg.__name__ + '.viastitcher_dialog')
Dialog = module.ViaStitcherDialog


def mm(value):
    return pcbnew.FromMM(value)


def point(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def layers(*ids):
    result = pcbnew.LSET()
    for layer in ids:
        result.AddLayer(layer)
    return result


def board_fixture():
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)
    gnd = pcbnew.NETINFO_ITEM(board, 'GND')
    signal = pcbnew.NETINFO_ITEM(board, 'SIGNAL')
    board.Add(gnd)
    board.Add(signal)
    for start, end in [((0,0),(36,0)),((36,0),(36,25)),((36,25),(0,25)),((0,25),(0,0))]:
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(point(*start)); edge.SetEnd(point(*end))
        edge.SetLayer(pcbnew.Edge_Cuts); edge.SetWidth(mm(.05))
        board.Add(edge)
    zone = pcbnew.ZONE(board)
    zone.SetNet(gnd)
    zone.SetZoneName('adaptive_fixture')
    zone.SetAssignedPriority(1)
    zone.SetLayerSet(layers(pcbnew.F_Cu, pcbnew.B_Cu))
    zone.SetLocalClearance(mm(.2))
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
    # One outline with a narrow bridge, severed by a copper keepout below.
    corners = [(2,2),(26,2),(26,10.8),(30.4,10.8),(30.4,10.4),
               (31.6,10.4),(31.6,11.6),(30.4,11.6),(30.4,11.2),
               (26,11.2),(26,22),(2,22)]
    idx = zone.Outline().NewOutline()
    for x,y in corners:
        zone.Outline().Append(mm(x),mm(y),idx)
    board.Add(zone)
    keepout = pcbnew.ZONE(board)
    keepout.SetIsRuleArea(True)
    keepout.SetLayerSet(layers(pcbnew.F_Cu, pcbnew.B_Cu))
    keepout.SetDoNotAllowZoneFills(True)
    idx = keepout.Outline().NewOutline()
    for x,y in [(26,10),(30.4,10),(30.4,12),(26,12)]:
        keepout.Outline().Append(mm(x),mm(y),idx)
    board.Add(keepout)
    # A foreign-net SMD pad blocks a nominal grid point and creates a copper hole.
    footprint = pcbnew.FOOTPRINT(board)
    footprint.SetReference('J1')
    footprint.SetPosition(point(12,12))
    pad = pcbnew.PAD(footprint)
    pad.SetNumber('1'); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT, pcbnew.F_Cu)
    pad.SetSize(point(.6,.6)); pad.SetLayerSet(layers(pcbnew.F_Cu))
    pad.SetPosition(point(12,12)); pad.SetNet(signal)
    footprint.Add(pad); board.Add(footprint)
    # A backing plane connects the islands through another layer, as on a real
    # stitching board. Otherwise adding a via to floating copper necessarily
    # exposes a new unconnected-net item, unrelated to placement clearance.
    plane = pcbnew.ZONE(board)
    plane.SetLayer(pcbnew.B_Cu)
    plane.SetNet(gnd)
    plane.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
    plane.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    plane.SetLocalClearance(mm(.2))
    idx = plane.Outline().NewOutline()
    for x,y in [(1,1),(35,1),(35,24),(1,24)]:
        plane.Outline().Append(mm(x),mm(y),idx)
    board.Add(plane)
    ground_fp = pcbnew.FOOTPRINT(board)
    ground_fp.SetReference('J2'); ground_fp.SetPosition(point(3,3))
    ground_pad = pcbnew.PAD(ground_fp)
    ground_pad.SetNumber('1'); ground_pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    ground_pad.SetShape(pcbnew.PAD_SHAPE_RECT, pcbnew.B_Cu)
    ground_pad.SetSize(point(.6,.6)); ground_pad.SetLayerSet(layers(pcbnew.B_Cu))
    ground_pad.SetPosition(point(3,3)); ground_pad.SetNet(gnd)
    ground_fp.Add(ground_pad); board.Add(ground_fp)
    board.BuildConnectivity()
    # The CLI initializes KiCad's project/rule engine before filling, unlike
    # ZONE_FILLER on a freshly constructed BOARD in standalone Python.
    cli = os.environ.get('KICAD_CLI', '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli')
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'fixture.kicad_pcb'
        pcbnew.SaveBoard(str(path), board)
        subprocess.run([cli, 'pcb', 'drc', '--refill-zones', '--save-board',
                        '--format', 'json', '-o', str(Path(directory)/'drc.json'), str(path)],
                       check=True, stdout=subprocess.DEVNULL)
        board = pcbnew.LoadBoard(str(path))
    return board, next(z for z in board.Zones() if z.GetZoneName() == 'adaptive_fixture')


class Control:
    def __init__(self, value): self.value = value
    def GetValue(self): return self.value
    def GetStringSelection(self): return self.value
    def GetSelection(self): return self.value
    def IsChecked(self): return self.value
    def SetValue(self, value): self.value = value


class Progress:
    def __init__(self,*a,**k):pass
    def Pulse(self,*a,**k):return True,False
    def Destroy(self):pass


class Harness:
    def Destroy(self): pass

for name,value in vars(Dialog).items():
    if callable(value) and name not in ('__init__',):setattr(Harness,name,value)


def harness(board,zone):
    h=Harness();h.board=board;h.area=zone;h.net='GND';h.FromUserUnit=mm
    for name,value in dict(m_txtViaSize='.6',m_txtViaDrillSize='.3',m_txtHSpacing='3',m_txtVSpacing='3',m_txtHOffset='0',m_txtVOffset='0',m_txtClearance='0',m_cbFillStyle=0,m_cbNet='GND',m_chkOnlyFilledCopper=True,m_txtObjectClearance='.35',m_txtMinDistance='1.5',m_chkCenterSegments=False,m_chkClearOwn=True).items():setattr(h,name,Control(value))
    h.board_edges=[x for x in board.GetDrawings() if x.GetLayer()==pcbnew.Edge_Cuts]
    h.pcb_group=pcbnew.PCB_GROUP(board);h.pcb_group.SetName('test');board.Add(h.pcb_group)
    h.viagroupname='test';h._random_seed=17;h.GetOverlappingItems();return h


def positions(board):
    return sorted((v.GetPosition().x,v.GetPosition().y) for v in board.GetTracks() if isinstance(v,pcbnew.PCB_VIA))


def run():
    board,zone=board_fixture()
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'base.kicad_pcb';pcbnew.SaveBoard(str(path),board)
        git=os.environ.get('GIT_BIN','git')
        source=subprocess.check_output([git,'show','5947e23:viastitcher_dialog.py'],cwd=ROOT,text=True)
        reference=types.ModuleType(pkg.__name__+'.reference');reference.__package__=pkg.__name__;exec(source,reference.__dict__)
        old=reference.ViaStitcherDialog
        # API-only adapter for the upstream 0.3.4 source on KiCad 10. Preserve
        # its historical uniform via width; do not alter placement decisions.
        native_width=pcbnew.PCB_VIA.GetWidth
        pcbnew.PCB_VIA.GetWidth=lambda self,*args:native_width(self,*(args or (pcbnew.F_Cu,)))
        for style in range(3):
            results=[]
            for original in (True,False):
                b=pcbnew.LoadBoard(str(path));z=next(z for z in b.Zones() if z.GetZoneName()=='adaptive_fixture');h=harness(b,z)
                h.m_cbFillStyle.SetValue(style)
                if original:
                    import types as bind
                    h.FillupArea=bind.MethodType(old.FillupArea,h)
                    for name in ('CheckOverlap','CheckClearance','HasFilledCopperAt'):
                        setattr(h,name,bind.MethodType(getattr(old,name),h))
                random.seed(17)
                with patch.object(wx,'MessageBox',lambda *a,**k:None),patch.object(pcbnew,'Refresh',lambda:None),patch.object(wx,'ProgressDialog',Progress):h.FillupArea()
                results.append(positions(b))
            assert results[0]==results[1],(style,len(results[0]),len(results[1]),set(results[0])^set(results[1]))
            print('Exact native upstream comparison:',style,len(results[1]),'PASS')

if __name__=='__main__':
    app=wx.App(False);run()
