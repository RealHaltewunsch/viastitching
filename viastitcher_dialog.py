#!/usr/bin/env python

# ViaStitcher for pcbnew
# This is the plugin WX dialog
# (c) Michele Santucci 2019
#
import random
from json import JSONDecodeError

import wx
import pcbnew
import math

from .viastitcher_gui import viastitcher_gui
from .localization import _
from .placement_engine import Grid, grid_candidates, evaluate_candidates

numpy_available = False
try:
    import numpy as np

    numpy_available = True
except Exception:
    from math import sqrt, pow
import json

__version__ = "0.3.4"
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

FILL_STYLES = ("Standard", "Stagger", "Randomize")


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
        self.SetTitle(_("{0} v{1}").format(__plugin_name__, __version__))
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
        self.overlappings = None
        self.initialized = True

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
            if (type(item) is pcbnew.PCB_VIA) and (
                item.GetBoundingBox().Intersects(area_bbox)
            ):
                self.overlappings.append(item)
            if type(item) is pcbnew.PCB_TRACK:
                self.overlappings.append(item)

        for item in modules:
            if item.GetBoundingBox().Intersects(area_bbox):
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
                    and (item.GetWidth() == viasize)
                    and (item.GetNetname() == netname)
                ):
                    self.board.Remove(item)
                    self.pcb_group.RemoveItem(item)
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
        corners = area.GetNumCorners()
        # Calculate minimum distance from corners
        # TODO: remove?
        for i in range(corners):
            corner = area.GetCornerPosition(i)
            # Handle both VECTOR2I and wxPoint
            if hasattr(corner, "getWxPoint"):
                p2 = corner.getWxPoint()
            else:
                p2 = corner  # VECTOR2I can be used directly
            # Avoid subtracting SWIG geometry objects directly: on KiCad 7
            # GetCornerPosition().getWxPoint() may return wxPoint while
            # via.GetPosition() returns VECTOR2I.
            the_distance = math.hypot(
                p2.x - p1.x,
                p2.y - p1.y,
            )

            if the_distance < clearance:
                return False

        for i in range(corners):
            corner1 = area.GetCornerPosition(i)
            corner2 = area.GetCornerPosition((i + 1) % corners)
            # Handle both VECTOR2I and wxPoint
            if hasattr(corner1, "getWxPoint"):
                pc1 = corner1.getWxPoint()
                pc2 = corner2.getWxPoint()
            else:
                pc1 = corner1  # VECTOR2I can be used directly
                pc2 = corner2
            the_distance, _ = pnt2line(p1, pc1, pc2)

            if the_distance <= clearance:
                return False

        for edge in self.board_edges:
            if edge.ShowShape() == "Line":
                the_distance, _ = pnt2line(p1, edge.GetStart(), edge.GetEnd())
                if the_distance <= clearance + _via_width(via) / 2:
                    return False
            if edge.ShowShape() == "Arc":
                # distance from center of Arc and with angle within Arc angle should be outside Arc radius +- clearance + via Width/2
                center = edge.GetPosition()
                start = edge.GetStart()
                end = edge.GetEnd()
                radius = norm(center - end)
                dist = norm(p1 - center)
                if (
                    radius - (self.clearance + _via_width(via) / 2)
                    < dist
                    < radius + (self.clearance + _via_width(via) / 2)
                ):
                    # via is in range need to check the angle
                    start_angle = math.atan2((start - center).y, (start - center).x)
                    end_angle = math.atan2((end - center).y, (end - center).x)
                    if end_angle < start_angle:
                        end_angle += 2 * math.pi
                    point_angle = math.atan2((p1 - center).y, (p1 - center).x)
                    if start_angle <= point_angle <= end_angle:
                        return False

        return True

    def CheckOverlap(self, via):
        """Check if via overlaps or interfere with other items on the board."""

        safe_margin = pcbnew.FromMM(0.35)
        min_hole_dist = pcbnew.FromMM(0.5)

        # --- 0. Edge ccuts check (Edge.Cuts) ---
        # set edge cuts range clearance (es. 0.5 mm)
        edge_clearance = pcbnew.FromMM(0.5)
        check_dist = int(_via_width(via) // 2 + edge_clearance)

        for edge in self.board_edges:
            if edge.HitTest(via.GetPosition(), check_dist):
                return True
        # ---------------------------------------------

        via_bbox = via.GetBoundingBox()
        via_bbox.Inflate(safe_margin)

        for item in self.overlappings:
            # 1. ignore copper filled zones
            if type(item).__name__ in ["ZONE", "FP_ZONE", "PCB_ZONE", "ZONE_CONTAINER"]:
                continue

            # 2. handling of the same net points
            if hasattr(item, "GetNetCode") and item.GetNetCode() == via.GetNetCode():
                if type(item) is pcbnew.PCB_TRACK:
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
            elif type(item) is pcbnew.PCB_TRACK:
                if item.GetBoundingBox().Intersects(via_bbox):
                    width = item.GetWidth()
                    dist, _ = pnt2line(
                        via.GetPosition(), item.GetStart(), item.GetEnd()
                    )
                    if (
                        dist
                        <= self.clearance
                        + width // 2
                        + _via_width(via) / 2
                        + safe_margin
                    ):
                        return True

        return False
        for item in self.overlappings:
            if type(item) is pcbnew.PAD:
                # Check with HitTest() rather than GetBoundingBox() to handle round+custom pad shapes
                via_layers = set(via.GetLayerSet().Seq())
                pad_layers = set(item.GetLayerSet().Seq())
                common_layers = via_layers & pad_layers
                if common_layers:
                    p = via.GetPosition()
                    accuracy = _via_width(via) // 2
                    if any(item.HitTest(p, accuracy, layer) for layer in common_layers):
                        return True
            elif type(item) is pcbnew.PCB_VIA:
                # Overlapping with vias work best if checking is performed by intersection
                if item.GetBoundingBox().Intersects(via.GetBoundingBox()):
                    return True
            elif type(item).__name__ in [
                "ZONE",
                "FP_ZONE",
                "PCB_ZONE",
                "ZONE_CONTAINER",
            ]:
                via_layers = set(via.GetLayerSet().Seq())
                zone_layers = set(item.GetLayerSet().Seq())
                common_layers = via_layers & zone_layers
                if common_layers:
                    p = via.GetPosition()
                    accuracy = _via_width(via) // 2
                    if any(
                        item.HitTestFilledArea(layer, p, accuracy)
                        for layer in common_layers
                    ):
                        return True
            elif type(item) is pcbnew.PCB_TRACK:
                if item.GetBoundingBox().Intersects(via.GetBoundingBox()):
                    width = item.GetWidth()
                    dist, _ = pnt2line(
                        via.GetPosition(), item.GetStart(), item.GetEnd()
                    )
                    if dist <= self.clearance + width // 2 + _via_width(via) / 2:
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
        pitch = number(self.m_txtHSpacing), number(self.m_txtVSpacing)
        offset = number(self.m_txtHOffset), number(self.m_txtVOffset)
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
        geometry = CandidateGeometry(position, grid.diameter+2*clearance,
                                     drill+2*clearance, self.area.GetLayerSet(), netcode)
        layers = list(geometry.GetLayerSet().Seq())
        if self.m_chkOnlyFilledCopper.GetValue():
            if not self.HasFilledCopperAt(geometry.GetPosition(), layers,
                                          netcode, grid.diameter/2):
                return "copper"
        elif not any(self.area.HitTestFilledArea(layer, geometry.GetPosition(), 0)
                     for layer in layers):
            return "copper"
        if self.CheckOverlap(geometry):
            return "collision"
        if clearance and not self.CheckClearance(geometry, self.area, clearance):
            return "edge"
        return None

    def PlaceVia(self, position, parameters):
        """Only this stage creates and adds the board's via objects."""
        grid, drill, clearance, netcode = parameters
        via = pcbnew.PCB_VIA(self.board)
        via.SetPosition(CandidateGeometry.point(position))
        via.SetLayerSet(self.area.GetLayerSet())
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
        self.clearance = parameters[2]
        count = 0
        for decision in evaluate_candidates(grid_candidates(parameters[0]),
                lambda position: self.ValidateCandidate(position, parameters)):
            if decision.accepted:
                self.PlaceVia(decision.position, parameters)
                count += 1
        wx.MessageBox(_("Implanted: %d vias!") % count if count else _("No vias implanted!"))
        pcbnew.Refresh()

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
        self.Destroy()

    def onClearAction(self, event):
        """Manage clear vias button (Clear) click event."""

        self.ClearArea()
        self.Destroy()

    def onCloseWindow(self, event):
        """Manage Close button click event."""

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
            self.board.SetLayerName(self.config_layer, __plugin_config_layer_name__)


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
