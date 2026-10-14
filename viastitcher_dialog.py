#!/usr/bin/env python

# ViaStitcher for pcbnew
# This is the plugin WX dialog
# (c) Michele Santucci 2019
#
from json import JSONDecodeError

import wx
import pcbnew
import math

from .viastitcher_gui import viastitcher_gui
from .localization import _
from .geometric_engine import Engine, Cancelled
from .native_geometry import BoardGeometry, point as geometry_point

import json

__version__ = "0.5.0"
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


def _via_width(via, layer=None):
    """KiCad 10 requires a layer when querying padstack-based via diameters."""
    try:
        return via.GetWidth(via.GetLayer() if layer is None else layer)
    except TypeError:
        return via.GetWidth()


class ViaStitcherDialog(viastitcher_gui):
    """Class that gathers all the GUI controls."""

    def __init__(self, board):
        """Initialize the brand new instance."""

        super(ViaStitcherDialog, self).__init__(None)
        self.initialized = False
        self.viagroupname = None
        self.SetTitle(_("{0} v{1} – geometric test build").format(__plugin_name__, __version__))
        self.Bind(wx.EVT_CLOSE, self.onCloseWindow)
        self.m_btnCancel.Bind(wx.EVT_BUTTON, self.onCloseWindow)
        self.m_btnOk.Bind(wx.EVT_BUTTON, self.onProcessAction)
        self.m_btnClear.Bind(wx.EVT_BUTTON, self.onClearAction)
        self.board = board
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
            if (d.GetLayerName() == __plugin_config_layer_name__
                    or d.GetLayer() == self.config_layer):
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
        self.m_lblUnit4.SetLabel(_(GUI_defaults["unit_labels"][units_mode]))
        self.m_lblUnitObject.SetLabel(_(GUI_defaults["unit_labels"][units_mode]))

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
        self.m_txtClearance.SetValue(defaults.get("Clearance", "0"))
        self.m_txtObjectClearance.SetValue(defaults.get("ObjectClearance", "0"))
        self.m_chkAllCopperLayers.SetValue(
            defaults.get("RequireAllCopperLayers", defaults.get("OnlyFilledCopper", False))
        )

        self.m_txtMinSpacing.SetValue(str(defaults.get("MinSpacingPercent", "80")))
        self.m_txtMaxSpacing.SetValue(str(defaults.get("MaxSpacingPercent", "150")))

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
        self.initialized = True

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

        for item in list(self.board.GetTracks()):
            if type(item) is pcbnew.PCB_VIA:
                # If the user selected the Undo action only signed/grouped vias are removed,
                # otherwise are removed vias matching values set in the dialog.

                # if undo and (item.GetTimeStamp() == __timecode__):
                if undo and (self.pcb_group is not None):
                    group = item.GetParentGroup()
                    if group is not None and group.GetName() == self.viagroupname:
                        group.RemoveItem(item)
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
                    parent=item.GetParentGroup()
                    if parent is not None:parent.RemoveItem(item)
                    self.board.Remove(item)
                    viacount += 1
                    # commit.Remove(item)

        if viacount > 0:
            wx.MessageBox(_("Removed: %d vias!") % viacount)
            # commit.Push()
            pcbnew.Refresh()

    def _read_fill_settings(self):
        def number(control):
            value=float(control.GetValue())
            if not math.isfinite(value):raise ValueError("Non-finite value")
            return value
        self.fill_settings={
            "drill":int(self.FromUserUnit(number(self.m_txtViaDrillSize))),
            "diameter":int(self.FromUserUnit(number(self.m_txtViaSize))),
            "pitch":(int(self.FromUserUnit(number(self.m_txtHSpacing))),int(self.FromUserUnit(number(self.m_txtVSpacing)))),
            "clearance":int(self.FromUserUnit(number(self.m_txtClearance))),
            "object_clearance":int(self.FromUserUnit(number(self.m_txtObjectClearance))),
            "minimum":number(self.m_txtMinSpacing)/100,
            "maximum":number(self.m_txtMaxSpacing)/100,
        }
        s=self.fill_settings
        if not 0<s["drill"]<s["diameter"] or min(s["pitch"])<=0 or min(s["clearance"],s["object_clearance"])<0:raise ValueError("Invalid dimensions")
        if not 0<s["minimum"]<=1<=s["maximum"]:raise ValueError("Invalid tolerance")
        if max(s["pitch"])*s["maximum"]>=2**31-1 or max(s["diameter"],s["clearance"],s["object_clearance"])>=2**30:raise ValueError("Dimensions exceed KiCad coordinate range")
        design=self.board.GetDesignSettings()
        if s["diameter"]<getattr(design,"m_ViasMinSize",0) or s["drill"]<getattr(design,"m_MinThroughDrill",0) or s["diameter"]-s["drill"]<2*getattr(design,"m_ViasMinAnnularWidth",0):raise ValueError("Via dimensions are below the board minimums")
        if not self.m_cbNet.GetStringSelection():raise ValueError("No net selected")

    def _open_progress(self):
        self._last_pulse=0
        self._progress=wx.ProgressDialog(_("Geometric via placement"),_("Finding free copper regions..."),parent=self,style=wx.PD_APP_MODAL|wx.PD_CAN_ABORT|wx.PD_ELAPSED_TIME)

    def _pulse(self,message):
        import time
        now=time.monotonic()
        if now-self._last_pulse<.04:return True
        self._last_pulse=now
        result=self._progress.Pulse(message)
        return result[0] if isinstance(result,tuple) else result

    def _prepare_geometry(self):
        s=self.fill_settings
        self._geometry=BoardGeometry(self.board,self.area,self.board.GetNetcodeFromNetname(self.m_cbNet.GetStringSelection()),s["diameter"],s["drill"],s["clearance"],self.m_chkAllCopperLayers.GetValue(),s["object_clearance"],pulse=lambda stage,n:self._pulse(_("Finding free copper regions...")))

    def _place_geometric_via(self,position):
        s=self.fill_settings;via=pcbnew.PCB_VIA(self.board)
        via.SetPosition(geometry_point(position));via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        via.SetNetCode(self.board.GetNetcodeFromNetname(self.m_cbNet.GetStringSelection()))
        if hasattr(via,"SetIsFree"):via.SetIsFree(True)
        via.SetWidth(s["diameter"]);via.SetDrill(s["drill"])
        self.board.Add(via);self.pcb_group.AddItem(via)

    def FillupArea(self):
        own_progress=not hasattr(self,"_progress")
        if own_progress:self._open_progress()
        solver=None
        try:
            if not hasattr(self,"_geometry"):self._prepare_geometry()
            s=self.fill_settings;g=self._geometry
            solver=Engine(g.backend,s["pitch"],s["minimum"],s["maximum"],pulse=lambda stats:self._pulse(_("Placing vias: {count} · Regions: {regions}").format(count=stats.placed,regions=stats.regions)),physical_radius=g.pair_radius)
            for shape,anchors in g.regions():
                for position in solver.run_region(shape,anchors):self._place_geometric_via(position)
            wx.MessageBox(_("Placed vias: {count}\nProcessed free regions: {regions}\nPlacement completed.").format(count=solver.stats.placed,regions=solver.stats.regions))
        except Cancelled:
            wx.MessageBox(_("Placement stopped. {count} vias already placed have been kept.").format(count=solver.stats.placed if solver else 0))
        finally:
            if own_progress:self._progress.Destroy();del self._progress
        pcbnew.Refresh()

    def onProcessAction(self, event):
        """Manage main button (Ok) click event."""
        try:
            self._read_fill_settings()
        except (ValueError, OverflowError) as error:
            wx.MessageBox(_("Invalid placement settings: {error}").format(error=str(error)))
            return
        self._open_progress()
        try:self._prepare_geometry()
        except Cancelled:
            self._progress.Destroy();del self._progress
            return
        except (ValueError,RuntimeError,AttributeError) as error:
            self._progress.Destroy();del self._progress
            wx.MessageBox(_("Cannot determine free via regions: {error}").format(error=str(error)))
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
            "Clearance": self.m_txtClearance.GetValue(),
            "FillStyle": "Geometric",
            "PlacementEngine": "Geometric",
            "ObjectClearance": self.m_txtObjectClearance.GetValue(),
            "RequireAllCopperLayers": self.m_chkAllCopperLayers.GetValue(),
            "MinSpacingPercent": self.m_txtMinSpacing.GetValue(),
            "MaxSpacingPercent": self.m_txtMaxSpacing.GetValue(),
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

        self.board.SetLayerName(self.config_layer, __plugin_config_layer_name__)
        self.config_textbox.SetText(json.dumps(self.config, indent=2))

        # Get overlapping items


        # Search trough groups
        for group in self.board.Groups():
            if group.GetName() == self.viagroupname:
                self.pcb_group = group

        if self.pcb_group is None:
            self.pcb_group = pcbnew.PCB_GROUP(None)
            self.pcb_group.SetName(self.viagroupname)
            self.board.Add(self.pcb_group)

        try:self.FillupArea()
        finally:
            self._progress.Destroy();del self._progress
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



def InitViaStitcherDialog(board):
    """Initalize dialog."""

    dlg = ViaStitcherDialog(board)
    if dlg.initialized:
        dlg.Show(True)
    return dlg
