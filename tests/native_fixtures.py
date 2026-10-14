"""Synthetic board fixture shared by native geometry/GUI regressions."""
import os,subprocess,tempfile
from pathlib import Path
import pcbnew
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

