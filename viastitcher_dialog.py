#!/usr/bin/env python

# ViaStitcher for pcbnew
# This is the plugin WX dialog
# (c) Michele Santucci 2019
#
import random
import time
from collections import Counter
from json import JSONDecodeError

import wx
import pcbnew
import math

from .viastitcher_gui import viastitcher_gui
from .localization import _
from .placement_engine import Grid, grid_candidates, evaluate_candidates, Decision, spiral_candidates, packing_candidates, SeparationIndex, centered_segment, BoundsIndex

numpy_available = False
try:
    import numpy as np

    numpy_available = True
except Exception:
    from math import sqrt, pow
import json

__version__ = "0.4.0"
__plugin_name__ = "ViaStitcher"
__plugin_config_key__ = "ViaStitcher"
# Continue accepting the marker written before the public plugin rename.
__legacy_plugin_config_key__ = "ViaStitching"
# __timecode__ = 1972
# This persistent prefix is intentionally unchanged so existing via groups are
# still found and cleared after upgrading to ViaStitcher.
__viagroupname_base__ = "VIA_STITCHING_GROUP"
__plugin_config_layer_name__ = "plugins.config"

GUI_defaults = {
    "to_units": {5: pcbnew.ToMils, 1: pcbnew.ToMM},
    "from_units": {5: pcbnew.FromMils, 1: pcbnew.FromMM},
    "unit_labels": {5: "mils", 1: "mm"},
    "spacing": {5: "40", 1: "1"},
    "offset": {5: "0", 1: "0"},
}

FILL_STYLES = ("Standard", "Stagger", "Randomize", "Spiral", "Maximize")


def _via_width(via):
    # KiCad 10 uses per-layer padstack widths; earlier SWIG bindings do not.
    try:
        return via.GetWidth(pcbnew.F_Cu)
    except TypeError:
        return via.GetWidth()


class ViaStitcherDialog(viastitcher_gui):
    """Class that gathers all the GUI controls."""

    def __init__(self, board):
        """Initialize the brand new instance."""

        super(ViaStitcherDialog, self).__init__(None)
        self.initialized = False
        self.viagroupname = None
        self.SetTitle(_("{0} v{1} (development)").format(__plugin_name__, __version__))
        self.Bind(wx.EVT_CLOSE, self.onCloseWindow)
        self.m_btnCancel.Bind(wx.EVT_BUTTON, self.onCloseWindow)
        self.m_btnOk.Bind(wx.EVT_BUTTON, self.onProcessAction)
        self.m_btnClear.Bind(wx.EVT_BUTTON, self.onClearAction)
        self.board = board
        self.randomize = False
        self.pcb_group = None
        self.clearance = 0
        self.board_edges = []
        self.config_layer = 0
        self.config_textbox = None
        self.area = None
        self.net = None
        self.config = {}

        self.getConfigLayer()

        for d in pcbnew.GetBoard().GetDrawings():
            if d.GetLayerName() == "Edge.Cuts":
                self.board_edges.append(d)
            if d.GetLayerName() == __plugin_config_layer_name__:
                try:
                    new_config = json.loads(d.GetText())
                    if (
                        __plugin_config_key__ in new_config.keys()
                        or __legacy_plugin_config_key__ in new_config.keys()
                    ):
                        self.config_textbox = d
                        self.config = new_config
                except (JSONDecodeError, AttributeError):
                    pass

        # Use the same unit set int PCBNEW
        self.ToUserUnit = None
        self.FromUserUnit = None
        units_mode = pcbnew.GetUserUnits()
        if units_mode == -1:
            wx.MessageBox(_("Not a valid frame"))
            self.Destroy()
            return

        # Check user unit is valid (Mils or MM)
        if units_mode not in GUI_defaults["to_units"]:
            wx.MessageBox(_("Unsupported unit selected"))
            self.Destroy()
            return

        # Check for selected area
        if not self.GetAreaConfig():
            wx.MessageBox(_("Please select a valid area"))
            self.Destroy()
            return

        # Populate nets checkbox
        self.PopulateNets()

        self.ToUserUnit = GUI_defaults["to_units"][units_mode]
        self.FromUserUnit = GUI_defaults["from_units"][units_mode]
        self.m_lblUnit1.SetLabel(_(GUI_defaults["unit_labels"][units_mode]))
        self.m_lblUnit2.SetLabel(_(GUI_defaults["unit_labels"][units_mode]))
        self.m_lblUnit3.SetLabel(_(GUI_defaults["unit_labels"][units_mode]))

        defaults = self.config.get(self.area.GetZoneName(), {})
        self.viagroupname = __viagroupname_base__ + self.area.GetZoneName()

        # Search trough groups
        for group in self.board.Groups():
            if group.GetName() == self.viagroupname:
                self.pcb_group = group

        self.m_txtVSpacing.SetValue(
            defaults.get("VSpacing", GUI_defaults["spacing"][units_mode])
        )
        self.m_txtHSpacing.SetValue(
            defaults.get("HSpacing", GUI_defaults["spacing"][units_mode])
        )
        self.m_txtVOffset.SetValue(
            defaults.get("VOffset", GUI_defaults["offset"][units_mode])
        )
        self.m_txtHOffset.SetValue(
            defaults.get("HOffset", GUI_defaults["offset"][units_mode])
        )
        self.m_txtClearance.SetValue(defaults.get("Clearance", "0"))
        self.m_cbFillStyle.SetSelection(self._get_fill_style_index(defaults))
        self.m_chkOnlyFilledCopper.SetValue(
            defaults.get("OnlyFilledCopper", True)
        )

        # Get default Vias dimensions
        via_size = None
        via_drill = None
        for via_dims in self.board.GetViasDimensionsList():
            via_size = via_dims.m_Diameter
            via_drill = via_dims.m_Drill

        # A new board may not have any custom via presets yet. In that case,
        # use the dimensions currently selected in Board Setup.
        if not via_size or not via_drill:
            design_settings = self.board.GetDesignSettings()
            if hasattr(design_settings, "GetCurrentViaSize"):
                via_size = design_settings.GetCurrentViaSize()
            if hasattr(design_settings, "GetCurrentViaDrill"):
                via_drill = design_settings.GetCurrentViaDrill()

        if not via_size or not via_drill:
            wx.MessageBox(
                _("Please set a valid via diameter and drill size in Board Setup")
            )
            self.Destroy()
            return

        self.m_txtViaSize.SetValue("%.6f" % self.ToUserUnit(via_size))
        self.m_txtViaDrillSize.SetValue("%.6f" % self.ToUserUnit(via_drill))
        self.m_txtObjectClearance.SetValue(defaults.get("ObjectClearance", "%.6f" % self.ToUserUnit(pcbnew.FromMM(.35))))
        self.m_txtMinDistance.SetValue(defaults.get("MinDistance", GUI_defaults["spacing"][units_mode]))
        self.m_chkCenterSegments.SetValue(defaults.get("CenterSegments", False))
        for label in (self.m_lblUnit4, self.m_lblUnit5, self.m_lblUnit6):
            label.SetLabel(_(GUI_defaults["unit_labels"][units_mode]))
        self.overlappings = None
        self.initialized = True
        self._random_seed = random.randrange(2**32)
        self._preview_results = []
        self._preview_timer = wx.Timer(self)
        self._preview_debounce = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._preview_tick, self._preview_timer)
        self.Bind(wx.EVT_TIMER, self._start_preview, self._preview_debounce)
        self.m_preview.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.m_preview.Bind(wx.EVT_PAINT, self._paint_preview)
        for control in (self.m_txtViaSize, self.m_txtViaDrillSize,
                self.m_txtHSpacing, self.m_txtVSpacing, self.m_txtHOffset,
                self.m_txtVOffset, self.m_txtClearance, self.m_txtObjectClearance,
                self.m_txtMinDistance):
            control.Bind(wx.EVT_TEXT, self._settings_changed)
        for control in (self.m_cbFillStyle, self.m_cbNet):
            control.Bind(wx.EVT_COMBOBOX, self._settings_changed)
        for control in (self.m_chkCenterSegments, self.m_chkOnlyFilledCopper, self.m_chkPreview):
            control.Bind(wx.EVT_CHECKBOX, self._settings_changed)
        self._settings_changed()


    @staticmethod
    def _get_fill_style_index(defaults):
        """Read the new style setting or migrate legacy checkbox settings."""
        fill_style = defaults.get("FillStyle")
        if fill_style in FILL_STYLES:
            return FILL_STYLES.index(fill_style)

        # Old configurations could enable both checkboxes. Randomize takes
        # precedence because the new selector intentionally makes styles
        # mutually exclusive.
        if defaults.get("Randomize", False):
            return FILL_STYLES.index("Randomize")
        if defaults.get("Stagger", False):
            return FILL_STYLES.index("Stagger")
        return FILL_STYLES.index("Standard")

    def _get_fill_style(self):
        selection = self.m_cbFillStyle.GetSelection()
        if 0 <= selection < len(FILL_STYLES):
            return FILL_STYLES[selection]
        return "Standard"


    def GetOverlappingItems(self):
        """Collect overlapping items.
        Every bounding box of any item found is a candidate to be inspected for overlapping.
        """

        area_bbox = self.area.GetBoundingBox()
        self._board_outline = None
        self._via_layers = pcbnew.LSET()
        for layer in self.board.GetEnabledLayers().Seq():
            if pcbnew.IsCopperLayer(layer):self._via_layers.AddLayer(layer)
        if self.board_edges and hasattr(self.board, "GetBoardPolygonOutlines"):
            outline = pcbnew.SHAPE_POLY_SET()
            try:
                valid = self.board.GetBoardPolygonOutlines(outline, False)
            except TypeError:
                valid = self.board.GetBoardPolygonOutlines(outline)
            if valid:self._board_outline = outline

        if hasattr(self.board, "GetModules"):
            modules = self.board.GetModules()
        else:
            modules = self.board.GetFootprints()

        tracks = self.board.GetTracks()

        self.overlappings = []

        for zone in self.board.Zones():
            if zone.GetZoneName() != self.area.GetZoneName():
                if zone.GetNetname() != self.net:
                    if zone.GetBoundingBox().Intersects(area_bbox):
                        self.overlappings.append(zone)

        for item in tracks:
            if type(item) is pcbnew.PCB_VIA:
                self.overlappings.append(item)
            if isinstance(item, pcbnew.PCB_TRACK) and not isinstance(item, pcbnew.PCB_VIA):
                self.overlappings.append(item)

        for item in modules:
            for pad in item.Pads():
                self.overlappings.append(pad)
            for zone in item.Zones():
                self.overlappings.append(zone)

        # TODO: change algorithm to 'If one of the candidate area's edges overlaps with target area declare candidate as overlapping'
        for i in range(0, self.board.GetAreaCount()):
            item = self.board.GetArea(i)
            if item.GetBoundingBox().Intersects(area_bbox):
                if item.GetNetname() != self.net:
                    self.overlappings.append(item)

        self._object_index = BoundsIndex(pcbnew.FromMM(5))
        seen=set()
        for item in self.overlappings:
            identity=item.m_Uuid.AsString() if hasattr(item,"m_Uuid") else id(item)
            if identity in seen:continue
            seen.add(identity)
            box=item.GetBoundingBox()
            self._object_index.add((box.GetLeft(),box.GetTop(),box.GetRight(),box.GetBottom()),item)

    def GetAreaConfig(self):
        """Check selected area (if any) and verify if it is a valid container for vias.

        Returns:
            bool: Returns True if an area/zone is selected and matches the implant criteria, False otherwise.
        """

        for i in range(0, self.board.GetAreaCount()):
            area = self.board.GetArea(i)
            if area.IsSelected():
                if not area.IsOnCopperLayer():
                    return False
                elif (
                    hasattr(area, "GetDoNotAllowCopperPour")
                    and area.GetDoNotAllowCopperPour()
                ):
                    return False
                elif (
                    hasattr(area, "GetDoNotAllowZoneFills")
                    and area.GetDoNotAllowZoneFills()
                ):
                    return False
                self.area = area
                self.net = area.GetNetname()
                return True

        return False

    def PopulateNets(self):
        """Populate nets widget."""

        nets = self.board.GetNetsByName()

        # Tricky loop, the iterator should return two values, unluckly I'm not able to use the
        # first value of the couple so I'm recycling it as netname.
        for netname, net in nets.items():
            netname = net.GetNetname()
            if (netname != None) and (netname != ""):
                self.m_cbNet.Append(netname)

        # Select the net used by area (if any)
        if self.net != None:
            index = self.m_cbNet.FindString(self.net)
            self.m_cbNet.Select(index)

    def ClearArea(self):
        """Clear selected area."""

        undo = self.m_chkClearOwn.IsChecked()
        drillsize = self.FromUserUnit(float(self.m_txtViaDrillSize.GetValue()))
        viasize = self.FromUserUnit(float(self.m_txtViaSize.GetValue()))
        netname = self.m_cbNet.GetStringSelection()
        netcode = self.board.GetNetcodeFromNetname(netname)
        # commit = pcbnew.COMMIT()
        viacount = 0

        for item in self.board.GetTracks():
            if type(item) is pcbnew.PCB_VIA:
                # If the user selected the Undo action only signed/grouped vias are removed,
                # otherwise are removed vias matching values set in the dialog.

                # if undo and (item.GetTimeStamp() == __timecode__):
                if undo and (self.pcb_group is not None):
                    group = item.GetParentGroup()
                    if group is not None and group.GetName() == self.viagroupname:
                        self.board.Remove(item)
                        viacount += 1
                        # commit.Remove(item)
                elif (
                    (not undo)
                    and self.area.HitTestFilledArea(
                        self.area.GetLayer(), item.GetPosition(), 0
                    )
                    and (item.GetDrillValue() == drillsize)
                    and (_via_width(item) == viasize)
                    and (item.GetNetname() == netname)
                ):
                    self.board.Remove(item)
                    parent = item.GetParentGroup()
                    if parent is not None:parent.RemoveItem(item)
                    viacount += 1
                    # commit.Remove(item)

        if viacount > 0:
            wx.MessageBox(_("Removed: %d vias!") % viacount)
            # commit.Push()
            pcbnew.Refresh()

    def CheckClearance(self, via, area, clearance):
        """Check if position specified by p1 comply with given clearance in area.

        Parameters:
            p1 (wxPoint): Position to test
            area (pcbnew.ZONE_CONTAINER): Area
            clearance (int): Clearance value

        Returns:
            bool: True if p1 position comply with clearance value False otherwise.

        """
        p1 = via.GetPosition()
        outline = area.Outline()
        if not outline.Contains(p1):
            return False
        for index in range(outline.OutlineCount()):
            rings = [outline.COutline(index)]
            rings.extend(outline.CHole(index,j) for j in range(outline.HoleCount(index)))
            for ring in rings:
                for j in range(ring.PointCount()):
                    a = ring.CPoint(j); b = ring.CPoint((j+1)%ring.PointCount())
                    distance,_ = pnt2line(p1,a,b)
                    if distance < clearance:
                        return False
        board_outline = getattr(self, '_board_outline', None)
        if board_outline is not None and not board_outline.Contains(p1):
            return False
        for edge in self.board_edges:
            if edge.HitTest(p1, int(self.clearance+_via_width(via)/2)):
                return False

        return True

    def CheckOverlap(self, via):
        """Check if via overlaps or interfere with other items on the board."""

        safe_margin = getattr(self, "object_clearance", pcbnew.FromMM(0.35))
        min_hole_dist = getattr(self.board.GetDesignSettings(), "m_HoleToHoleMin", pcbnew.FromMM(0.5))

        # --- 0. Edge ccuts check (Edge.Cuts) ---
        # set edge cuts range clearance (es. 0.5 mm)
        edge_clearance = self.clearance
        check_dist = int(_via_width(via) // 2 + edge_clearance)

        for edge in self.board_edges:
            if edge.HitTest(via.GetPosition(), check_dist):
                return True
        # ---------------------------------------------

        via_bbox = via.GetBoundingBox()
        via_bbox.Inflate(safe_margin)

        candidates = self.overlappings
        if hasattr(self,"_object_index"):
            candidates=self._object_index.query((via_bbox.GetLeft()-min_hole_dist,via_bbox.GetTop()-min_hole_dist,via_bbox.GetRight()+min_hole_dist,via_bbox.GetBottom()+min_hole_dist))
        for item in candidates:
            # Rule areas forbidding vias apply even when they permit zone fills.
            if hasattr(item,"GetDoNotAllowVias") and item.GetDoNotAllowVias():
                if set(item.GetLayerSet().Seq()) & set(via.GetLayerSet().Seq()):
                    outline=item.Outline();position=via.GetPosition()
                    if outline.Contains(position):return True
                    for i in range(outline.OutlineCount()):
                        rings=[outline.COutline(i)]+[outline.CHole(i,j) for j in range(outline.HoleCount(i))]
                        for ring in rings:
                            if any(pnt2line(position,ring.CPoint(j),ring.CPoint((j+1)%ring.PointCount()))[0] < _via_width(via)/2
                                   for j in range(ring.PointCount())):
                                return True
            # 1. ignore copper filled zones
            if type(item).__name__ in ["ZONE", "FP_ZONE", "PCB_ZONE", "ZONE_CONTAINER"]:
                continue

            # 2. handling of the same net points
            if hasattr(item, "GetNetCode") and item.GetNetCode() == via.GetNetCode():
                if isinstance(item, pcbnew.PCB_TRACK) and not isinstance(item, pcbnew.PCB_VIA):
                    continue
                elif type(item) is pcbnew.PCB_VIA:
                    # if same net check clearance
                    dist = math.hypot(
                        via.GetPosition().x - item.GetPosition().x,
                        via.GetPosition().y - item.GetPosition().y,
                    )
                    if dist < (
                        via.GetDrillValue() / 2
                        + item.GetDrillValue() / 2
                        + min_hole_dist
                    ):
                        return True
                    continue

            # 3. check collisions with Pads
            if type(item) is pcbnew.PAD:
                via_layers = set(via.GetLayerSet().Seq())
                pad_layers = set(item.GetLayerSet().Seq())
                common_layers = via_layers & pad_layers
                if common_layers:
                    p = via.GetPosition()
                    accuracy = int(_via_width(via) // 2 + safe_margin)
                    if any(item.HitTest(p, accuracy, layer) for layer in common_layers):
                        return True

            # 4. check collisions with VIAS (other nets)
            elif type(item) is pcbnew.PCB_VIA:
                if item.GetBoundingBox().Intersects(via_bbox):
                    return True

            # 5. check collisions with other tracks (other nets)
            elif hasattr(pcbnew, "PCB_ARC") and isinstance(item, pcbnew.PCB_ARC):
                if item.HitTest(via.GetPosition(), int(_via_width(via)/2+safe_margin)):
                    return True
            elif type(item) is pcbnew.PCB_TRACK:
                if item.GetBoundingBox().Intersects(via_bbox):
                    width = item.GetWidth()
                    dist, _ = pnt2line(
                        via.GetPosition(), item.GetStart(), item.GetEnd()
                    )
                    if (
                        dist
                        <= width // 2
                        + _via_width(via) / 2
                        + safe_margin
                    ):
                        return True

        return False

    def HasFilledCopperAt(self, position, layers, netcode, radius):
        """Return whether the selected net has filled copper around a via."""

        samples = [position]
        for index in range(32):
            angle = 2 * math.pi * index / 32
            sample_x = int(position.x + radius * math.cos(angle))
            sample_y = int(position.y + radius * math.sin(angle))
            if hasattr(pcbnew, "VECTOR2I"):
                samples.append(pcbnew.VECTOR2I(sample_x, sample_y))
            else:
                samples.append(pcbnew.wxPoint(sample_x, sample_y))

        zones = [zone for zone in self.board.Zones() if zone.GetNetCode() == netcode]
        for layer in layers:
            if not all(
                any(
                    zone.HitTestFilledArea(layer, sample, 0)
                    for zone in zones
                    if layer in set(zone.GetLayerSet().Seq())
                )
                for sample in samples
            ):
                return False

        return True

    def _placement_parameters(self):
        """Read and validate inputs before any configuration/board mutation."""
        def number(control):
            value = float(control.GetValue())
            if not math.isfinite(value):
                raise ValueError("Placement parameters must be finite")
            return self.FromUserUnit(value)
        diameter = number(self.m_txtViaSize)
        drill = number(self.m_txtViaDrillSize)
        clearance = number(self.m_txtClearance)
        mode = self._get_fill_style()
        pitch = (number(self.m_txtHSpacing), number(self.m_txtVSpacing)) if mode != "Maximize" else (1,1)
        offset = (number(self.m_txtHOffset), number(self.m_txtVOffset)) if mode in ("Standard","Stagger","Randomize") else (0,0)
        self.object_clearance = number(self.m_txtObjectClearance)
        self.minimum_distance = number(self.m_txtMinDistance) if mode == "Maximize" else 1
        if self.object_clearance < 0 or self.minimum_distance <= 0:
            raise ValueError("Invalid object clearance or minimum spacing")
        if mode == "Maximize":
            pitch = self.minimum_distance, self.minimum_distance
        box = self.area.GetBoundingBox()
        grid = Grid((box.GetLeft(), box.GetTop(), box.GetRight(), box.GetBottom()),
                    diameter, pitch, offset, self._get_fill_style())
        grid.validate()
        if drill <= 0 or drill >= diameter or clearance < 0:
            raise ValueError("Require 0 < drill < diameter and clearance >= 0")
        netcode = self.board.GetNetcodeFromNetname(self.m_cbNet.GetStringSelection())
        if netcode <= 0:
            raise ValueError("Select a valid net")
        return grid, drill, clearance, netcode

    def ValidateCandidate(self, position, parameters):
        """Return a rejection category without creating a PCB object."""
        grid, drill, clearance, netcode = parameters
        geometry = CandidateGeometry(position, grid.diameter,
                                     drill, self._via_layers, netcode)
        layers = list(self.area.GetLayerSet().Seq())
        if not self.CheckClearance(geometry, self.area, clearance + grid.diameter/2):
            return "edge"
        if self.m_chkOnlyFilledCopper.GetValue():
            if not self.HasFilledCopperAt(geometry.GetPosition(), layers,
                                          netcode, grid.diameter/2):
                return "copper"
        elif not any(self.area.HitTestFilledArea(layer, geometry.GetPosition(), 0)
                     for layer in layers):
            return "copper"
        if self.CheckOverlap(geometry):
            return "collision"
        return None

    def PlaceVia(self, position, parameters):
        """Only this stage creates and adds the board's via objects."""
        grid, drill, clearance, netcode = parameters
        via = pcbnew.PCB_VIA(self.board)
        via.SetPosition(CandidateGeometry.point(position))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNetCode(netcode)
        if hasattr(via, "SetIsFree"):
            via.SetIsFree(True)
        via.SetWidth(grid.diameter)
        via.SetDrill(drill)
        self.board.Add(via)
        self.pcb_group.AddItem(via)
        return via

    def FillupArea(self):
        """Generate, validate, then create each accepted via."""
        parameters = self._placement_parameters()
        self._stop_preview()
        self.clearance = parameters[2]
        count = 0
        progress = wx.ProgressDialog(_("Via placement"), _("Computing candidates..."),
            parent=self, style=wx.PD_APP_MODAL|wx.PD_CAN_ABORT|wx.PD_ELAPSED_TIME)
        last = 0
        try:
            for decision in self._decisions(parameters):
                if time.monotonic()-last > .05:
                    if not progress.Pulse(_("Placed: %d vias") % count)[0]:
                        break
                    last = time.monotonic()
                if decision.accepted:
                    self.PlaceVia(decision.position, parameters)
                    count += 1
        finally:
            progress.Destroy()
        wx.MessageBox(_("Implanted: %d vias!") % count if count else _("No vias implanted!"))
        pcbnew.Refresh()

    def _decisions(self, parameters):
        grid, drill, clearance, netcode = parameters
        self.clearance = clearance
        mode = grid.style
        if mode == "Spiral":
            candidates = spiral_candidates(grid.bounds, grid.pitch)
        elif mode == "Maximize":
            candidates = packing_candidates(grid.bounds, self.minimum_distance)
        else:
            candidates = grid_candidates(grid, random.Random(getattr(self, "_random_seed", 0)))
        spacing = grid.pitch if mode == "Spiral" else (self.minimum_distance,)*2
        pattern_index = SeparationIndex(spacing) if mode in ("Spiral","Maximize") else None
        # All prospective vias must also obey drill separation, even though the
        # preview never inserts them into the board's collision collection.
        hole_min = getattr(self.board.GetDesignSettings(), "m_HoleToHoleMin", pcbnew.FromMM(.5))
        holes = SeparationIndex((drill+hole_min,)*2)
        if mode in ("Standard","Stagger") and self.m_chkCenterSegments.GetValue():
            candidates = self._centered_candidates(parameters)
        for position in candidates:
            if position is None:
                yield Decision((0,0), "probe")
                continue
            reason = self.ValidateCandidate(position, parameters)
            if reason is None and (not holes.permits(position) or
                    (pattern_index is not None and not pattern_index.permits(position))):
                reason = "spacing"
            decision = Decision(position, reason or "accepted")
            if decision.accepted:
                holes.add(position)
                if pattern_index is not None:pattern_index.add(position)
            yield decision

    def _centered_candidates(self, parameters):
        grid = parameters[0]
        left, top, right, bottom = grid.bounds
        radius = grid.diameter/2
        left += radius; right -= radius
        y = top+radius
        y += (-(y+grid.offset[1])) % grid.pitch[1]
        step = max(1,min(grid.pitch[0]/20,grid.diameter/4))
        def transition(lo,hi,valid_left):
            while hi-lo>1:
                middle=(lo+hi)/2
                valid=self.ValidateCandidate((int(middle),int(y)),parameters) is None
                if valid == valid_left:lo=middle
                else:hi=middle
            return lo if valid_left else hi
        while y <= bottom-radius:
            x=left; start=None; previous=left
            while x <= right:
                valid = self.ValidateCandidate((int(x),int(y)), parameters) is None
                if valid and start is None:
                    start=x if x==left else transition(previous,x,False)
                if not valid and start is not None:
                    for px in centered_segment(start,transition(previous,x,True),grid.pitch[0]):yield px,int(y)
                    start=None
                previous=x; x+=step
                yield None  # cooperative progress/cancellation during row scans
            if start is not None:
                for px in centered_segment(start,previous,grid.pitch[0]):yield px,int(y)
            y+=grid.pitch[1]

    def _stop_preview(self):
        for name in ("_preview_timer","_preview_debounce"):
            timer=getattr(self,name,None)
            if timer is not None:timer.Stop()

    def _settings_changed(self, event=None):
        self._stop_preview()
        mode=self._get_fill_style()
        for control in (self.m_txtHOffset,self.m_txtVOffset):
            control.Enable(mode in ("Standard","Stagger","Randomize") and not (mode in ("Standard","Stagger") and self.m_chkCenterSegments.GetValue()))
        for control in (self.m_txtHSpacing,self.m_txtVSpacing):control.Enable(mode != "Maximize")
        self.m_txtMinDistance.Enable(mode == "Maximize")
        self.m_chkCenterSegments.Enable(mode in ("Standard","Stagger"))
        enabled=self.m_chkPreview.GetValue()
        self.m_preview.Show(enabled)
        self.m_lblPreviewStatus.Show(enabled)
        self.Layout();self.Fit()
        if enabled:self._preview_debounce.StartOnce(250)
        if event is not None:event.Skip()

    def _start_preview(self, event=None):
        try:
            self._preview_parameters=self._placement_parameters()
            self.GetOverlappingItems()
            self._preview_results=[];self._preview_counts=Counter()
            self._preview_iterator=iter(self._decisions(self._preview_parameters))
            self.m_lblPreviewStatus.SetLabel(_("Computing preview..."))
            self._preview_timer.Start(20)
        except (ValueError,OverflowError):
            self._preview_results=[];self.m_preview.Refresh()
            self.m_lblPreviewStatus.SetLabel(_("Enter valid placement parameters to preview."))
        except Exception:
            self.m_lblPreviewStatus.SetLabel(_("Preview unavailable; placement remains available."))

    def _preview_tick(self, event):
        deadline=time.monotonic()+.02
        try:
            while time.monotonic()<deadline:
                decision=next(self._preview_iterator)
                if decision.reason == "probe":continue
                self._preview_counts[decision.reason]+=1
                if len(self._preview_results)<20000:self._preview_results.append(decision)
        except StopIteration:
            self._preview_timer.Stop()
        except Exception:
            self._preview_timer.Stop()
            self.m_lblPreviewStatus.SetLabel(_("Preview unavailable; placement remains available."))
            return
        counts=self._preview_counts
        self.m_lblPreviewStatus.SetLabel(_("Accepted: {a} | Edge: {e} | Collision: {c}\nCopper: {f} | Spacing: {s}").format(
            a=counts['accepted'],e=counts['edge'],c=counts['collision'],f=counts['copper'],s=counts['spacing'])
            + (_(" (computing)") if self._preview_timer.IsRunning() else "")
            + (_(" (drawing limited to 20,000 candidates)") if sum(counts.values())>20000 else ""))
        self.m_lblPreviewStatus.Wrap(max(200,self.GetClientSize().width-20))
        self.Layout()
        self.m_preview.Refresh()

    def _paint_preview(self, event):
        dc=wx.AutoBufferedPaintDC(self.m_preview);dc.SetBackground(wx.Brush('#101923'));dc.Clear()
        if not hasattr(self,'_preview_parameters'):return
        left,top,right,bottom=self._preview_parameters[0].bounds
        width,height=self.m_preview.GetClientSize()
        scale=min((width-16)/max(1,right-left),(height-16)/max(1,bottom-top))
        dc.SetPen(wx.Pen('#91a2b8'));dc.SetBrush(wx.TRANSPARENT_BRUSH)
        outline=self.area.Outline()
        for i in range(outline.OutlineCount()):
            rings=[outline.COutline(i)]+[outline.CHole(i,j) for j in range(outline.HoleCount(i))]
            for ring in rings:
                points=[wx.Point(int(8+(ring.CPoint(j).x-left)*scale),int(8+(ring.CPoint(j).y-top)*scale)) for j in range(ring.PointCount())]
                if len(points)>2:dc.DrawPolygon(points)
        colors={'accepted':'#3bd9a4','edge':'#ff6b6b','collision':'#ffc66d','copper':'#778899','spacing':'#967bdc'}
        for d in self._preview_results:
            dc.SetPen(wx.Pen(colors[d.reason]));dc.SetBrush(wx.Brush(colors[d.reason]))
            dc.DrawCircle(int(8+(d.position[0]-left)*scale),int(8+(d.position[1]-top)*scale),2)

    def onProcessAction(self, event):
        """Manage main button (Ok) click event."""
        try:
            self._placement_parameters()
        except (ValueError, OverflowError):
            wx.MessageBox(_("Enter finite positive spacing and via sizes, drill smaller than diameter, and non-negative clearance."))
            return
        zone_name = self.area.GetZoneName()
        if zone_name == "":
            for i in range(1000):
                candidate_name = f"stitch_zone_{i}"
                if candidate_name not in self.config.keys():
                    zone_name = candidate_name
                    break
            else:
                wx.LogError(
                    "Tried 1000 different names and all were taken. Please give a name to the zone."
                )
                self.Destroy()
                return
            self.area.SetZoneName(zone_name)

        # Keep the group name synchronized with the final zone name
        self.viagroupname = __viagroupname_base__ + zone_name

        config = {
            "HSpacing": self.m_txtHSpacing.GetValue(),
            "VSpacing": self.m_txtVSpacing.GetValue(),
            "HOffset": self.m_txtHOffset.GetValue(),
            "VOffset": self.m_txtVOffset.GetValue(),
            "Clearance": self.m_txtClearance.GetValue(),
            "FillStyle": self._get_fill_style(),
            "OnlyFilledCopper": self.m_chkOnlyFilledCopper.GetValue(),
            "ObjectClearance": self.m_txtObjectClearance.GetValue(),
            "MinDistance": self.m_txtMinDistance.GetValue(),
            "CenterSegments": self.m_chkCenterSegments.GetValue(),
        }

        if self.config_textbox is None:
            self.config = {__plugin_config_key__: __version__}
            title_block = pcbnew.PCB_TEXT(self.board)
            title_block.SetLayer(self.config_layer)

            if hasattr(pcbnew, "GR_TEXT_HJUSTIFY_LEFT"):
                title_block.SetHorizJustify(pcbnew.GR_TEXT_HJUSTIFY_LEFT)
            else:
                if hasattr(pcbnew, "GR_TEXT_H_ALIGN_LEFT"):
                    title_block.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)

            if hasattr(pcbnew, "GR_TEXT_VJUSTIFY_TOP"):
                title_block.SetVertJustify(pcbnew.GR_TEXT_VJUSTIFY_TOP)
            else:
                if hasattr(pcbnew, "GR_TEXT_V_ALIGN_TOP"):
                    title_block.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_TOP)

            title_block.SetVisible(False)
            self.config_textbox = title_block
            self.board.Add(title_block)
        self.board.SetLayerName(self.config_layer, __plugin_config_layer_name__)
        self.config[zone_name] = config

        self.config_textbox.SetText(json.dumps(self.config, indent=2))

        # Get overlapping items
        self.GetOverlappingItems()

        # Search trough groups
        for group in self.board.Groups():
            if group.GetName() == self.viagroupname:
                self.pcb_group = group

        if self.pcb_group is None:
            self.pcb_group = pcbnew.PCB_GROUP(None)
            self.pcb_group.SetName(self.viagroupname)
            self.board.Add(self.pcb_group)

        self.FillupArea()
        self._stop_preview()
        self.Destroy()

    def onClearAction(self, event):
        """Manage clear vias button (Clear) click event."""

        self._stop_preview()
        self.ClearArea()
        self.Destroy()

    def onCloseWindow(self, event):
        """Manage Close button click event."""

        self._stop_preview()
        self.Destroy()

    def GetStandardLayerName(self, layerid):
        if hasattr(pcbnew, "BOARD_GetStandardLayerName"):
            layer_name = pcbnew.BOARD_GetStandardLayerName(layerid)
        else:
            layer_name = self.board.GetStandardLayerName(layerid)

        return layer_name

    def getConfigLayer(self):
        self.config_layer = 0
        user_layer = 0
        for i in range(
            pcbnew.PCBNEW_LAYER_ID_START,
            pcbnew.PCBNEW_LAYER_ID_START + pcbnew.PCB_LAYER_ID_COUNT,
        ):
            if __plugin_config_layer_name__ == self.GetStandardLayerName(i):
                self.config_layer = i
                break
            if "User.9" == self.GetStandardLayerName(i):
                user_layer = i
        else:
            self.config_layer = user_layer
            # Defer layer naming until Apply; opening/cancelling is read-only.
            pass


def InitViaStitcherDialog(board):
    """Initalize dialog."""

    dlg = ViaStitcherDialog(board)
    if dlg.initialized:
        dlg.Show(True)
    return dlg


class CandidateGeometry:
    """Read-only geometry adapter; unlike PCB_VIA it never belongs to a board."""
    def __init__(self, position, diameter, drill, layers, netcode):
        self.position = self.point(position)
        self.diameter, self.drill = diameter, drill
        self.layers, self.netcode = layers, netcode

    @staticmethod
    def point(position):
        constructor = getattr(pcbnew, "VECTOR2I", None) or pcbnew.wxPoint
        return constructor(int(position[0]), int(position[1]))

    def GetPosition(self): return self.position
    def GetWidth(self, *args): return self.diameter
    def GetDrillValue(self): return self.drill
    def GetLayerSet(self): return self.layers
    def GetNetCode(self): return self.netcode
    def GetBoundingBox(self):
        radius = self.diameter//2
        if hasattr(pcbnew, "BOX2I"):
            return pcbnew.BOX2I(self.point((self.position.x-radius, self.position.y-radius)),
                               self.point((self.diameter, self.diameter)))
        return pcbnew.EDA_RECT(pcbnew.wxPoint(self.position.x-radius, self.position.y-radius),
                               pcbnew.wxSize(self.diameter, self.diameter))


class aVector:
    def __init__(self, point: [pcbnew.wxPoint, list]):
        if isinstance(point, pcbnew.wxPoint):
            self.x = float(point.x)
            self.y = float(point.y)
        elif isinstance(point, list):
            self.x = point[0]
            self.y = point[1]

    def __sub__(self, other: pcbnew.wxPoint):
        return aVector([self.x - float(other.x), self.y - float(other.y)])

    def __mul__(self, other):
        return aVector([self.x * float(other), self.y * float(other)])

    def __add__(self, other):
        return aVector([self.x + float(other.x), self.y + float(other.y)])

    def __truediv__(self, other):
        return aVector([self.x / other, self.y / other])

    @staticmethod
    def norm(vector):
        return sqrt(pow(vector.x, 2) + pow(vector.y, 2))

    @staticmethod
    def dot(vector1, vector2):
        return vector1.x * vector2.x + vector1.y * vector2.y


# Given a line with coordinates 'start' and 'end' and the
# coordinates of a point 'point' the proc returns the shortest
# distance from pnt to the line and the coordinates of the
# nearest point on the line.
#
# 1  Convert the line segment to a vector ('line_vec').
# 2  Create a vector connecting start to pnt ('pnt_vec').
# 3  Find the length of the line vector ('line_len').
# 4  Convert line_vec to a unit vector ('line_unitvec').
# 5  Scale pnt_vec by line_len ('pnt_vec_scaled').
# 6  Get the dot product of line_unitvec and pnt_vec_scaled ('t').
# 7  Ensure t is in the range 0 to 1.
# 8  Use t to get the nearest location on the line to the end
#    of vector pnt_vec_scaled ('nearest').
# 9  Calculate the distance from nearest to pnt_vec_scaled.
# 10 Translate nearest back to the start/end line.
# Malcolm Kesson 16 Dec 2012


def pnt2line(point: pcbnew.wxPoint, start: pcbnew.wxPoint, end: pcbnew.wxPoint):
    pnt = vector([point.x, point.y])
    strt = vector([start.x, start.y])
    nd = vector([end.x, end.y])
    line_vec = nd - strt
    pnt_vec = pnt - strt
    line_len = norm(line_vec)

    # --- ANTI CRASH ---
    if line_len < 0.0001:
        dist = norm(pnt_vec)
        return dist, strt
    # --- END PATCH ---

    line_unitvec = line_vec / line_len
    pnt_vec_scaled = pnt_vec / line_len
    t = dot(line_unitvec, pnt_vec_scaled)
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    nearest = line_vec * t
    dist = norm(pnt_vec - nearest)
    nearest = nearest + strt
    return dist, nearest


norm = aVector.norm
vector = aVector
dot = aVector.dot
if numpy_available:
    norm = np.linalg.norm
    vector = np.array
    dot = np.dot
