# ViaStitcher

Via stitching action plugin for KiCad 6.0 and newer.

Fill a selected copper area with a pattern of vias.

## When to use this tool

ViaStitcher fills a selected copper zone with a configurable grid of vias. It can be used for ground stitching, shielding, thermal conduction, and current sharing between copper layers.

The plugin works from an existing filled copper zone. Create and fill the zone, select it in PCB Editor, and then start ViaStitcher.

## Install

Install ViaStitcher as a user action plugin in the scripting directory for your KiCad version. On Windows, the usual location is:

```text
C:\Users\<user>\Documents\KiCad\<version>\scripting\plugins\viastitcher
```

Copy the complete repository contents into that directory and restart KiCad. The plugin should appear under **Tools → External Plugins → ViaStitcher**.

## Releases

Release packages for KiCad's Plugin and Content Manager are built automatically when a four-part release tag is pushed. Git tags cannot contain spaces, so use the following format:

```text
Release-x.x.x.x
```

For example, `Release-0.2.0.0` packages PCM version `0.2.0` with version epoch `0`. Before pushing the tag, update `metadata.json` so its version and epoch match. The workflow creates a GitHub release containing the installable PCM ZIP and a `repository-metadata.json` file with the download URL, SHA-256 checksum, download size, and install size required for submission to the official KiCad addon repository. The package uses `viastitcher64x64.png` as its PCM icon while retaining `viastitcher.png` as the PCB Editor toolbar icon.

## Localization

ViaStitcher follows KiCad's active interface language and currently includes English and Italian catalogs. English source strings are the fallback when no matching catalog is available. Set `VIASTITCHER_LANGUAGE` (for example, to `it_IT`) to override language detection while testing.

After editing a `.po` file, compile the runtime `.mo` catalogs before committing:

```text
python locale_setup.py
```

`viastitcher.fbp` is the source of truth for the dialog layout. It has wxFormBuilder internationalization enabled; therefore regenerated `viastitcher_gui.py` files deliberately use `gettext.gettext`. Do not edit the generated file to change its translation import: `localization.py` installs the selected ViaStitcher catalog as gettext's default domain when the plugin loads.

## How it works

Select a filled copper zone and start **Tools → External Plugins → ViaStitcher**, or use the ![ViaStitcher icon](viastitcher.png?raw=true) toolbar button. The following dialog opens:

![ViaStitcher dialog](pictures/viastitcher_dialog.png?raw=true "ViaStitcher dialog")

The zone net is selected automatically, but another net can be chosen when needed. The dialog provides:

- via diameter and drill diameter, initialized from the board settings;
- vertical and horizontal spacing;
- vertical and horizontal grid offsets;
- clearance from the zone boundary and board edges (`0` disables the additional clearance check);
- optional randomized placement;
- **Require copper connection on all layers (off: at least two)**.

The copper-connection checkbox is **off by default**: a via must have its full annular area over the selected net on at least two copper layers. Enable it to require this on every copper layer traversed by the through via. The setting is saved per zone as `RequireAllCopperLayers`. Legacy `OnlyFilledCopper=true` settings migrate to the stricter all-layer mode; unchecked legacy settings now require at least two connected layers instead of allowing single-layer placement. The checkbox never disables collision checks.

Generated vias are marked as free vias when supported by the KiCad API. This prevents KiCad's automatic via-net update from changing their assigned net when several filled zones overlap.

Press **Ok** to generate the vias. Always run KiCad's Design Rules Checker after stitching.
If everything goes fine you'll get something like this:

![ViaStitcher result](pictures/viastitcher_result.png?raw=true "ViaStitcher result")

ViaStitcher checks pads, tracks, vias, footprint zones, board edges, and items belonging to other nets before placing each via. Complex boards may still expose cases not covered by the plugin, so DRC verification remains essential.

Use **Clear** to remove matching vias from the selected zone. With **Clear only plugin placed vias** enabled, only vias belonging to that zone's ViaStitcher group are removed. Disable it to remove any via matching the selected net, size, and drill values inside the zone.

## Optional island and gap refill

Enable **Refill islands and gaps** to run a second pass after the selected grid
style (Standard, Stagger, or Randomize). It uses the selected zone's actual
filled copper polygons, including holes and disconnected islands on each layer.
Small islands can receive a via even when no grid point falls inside them.
Existing vias of the selected net count when they satisfy the chosen
two-layer or all-layer copper-connection requirement.
Vias on a different island do not count as that island's connection.

**Refill spacing (min/max %)** defaults to **80 / 150**. These percentages apply
to center-to-center distances normalized by the horizontal and vertical grid
spacing: `hypot(dx / HSpacing, dy / VSpacing)`. Thus a horizontal 4 mm grid aims
for 4 mm neighbors, allowing 3.2–6 mm in that direction. Limits must satisfy
`0 < minimum <= 100 <= maximum`. They affect only additional vias; existing and
first-pass vias are not moved. The option and both limits are saved per zone;
older configurations default to refill disabled.

Refill tries nominal grid sites first, then points between copper boundaries
and foreign tracks to find narrow corridors. Every suggested point passes the
same copper, collision, and boundary checks as a regular via. Nearby positions
inside each grid cell are then searched from coarse to fine, across the whole
board at each refinement level so early blocked cells cannot consume all work.
The final search step is the smaller of 1% of the relevant
pitch and one quarter of the via diameter (at least one internal board unit).
Each cell search is limited to 512 mesh candidates and 64 geometry suggestions.
The whole refill pass
has a 50,000-candidate / 10-second budget (checked between candidates); reaching
a budget keeps partial results and reports that the search was incomplete.
Refinement may stop before the finest step when a budget is reached. The nearest grid
position is preferred. Minimum spacing is mandatory for all additional vias.
The maximum is the preferred reach when extending an existing pattern:
deferred cells are revisited when accepted vias make them reachable. If that
cannot reach an empty pocket, the search may seed that pocket without a nearby
neighbor, just as it can seed an unserved island. This is necessary because
obstacles can separate valid via positions even on one connected copper plane.
Such seeds still obey minimum spacing and every physical placement check.

This is a bounded placement heuristic, not an exhaustive search or a guarantee
of uniform density. Narrow or obstructed copper may remain unserved. A progress
dialog allows stopping the refill; vias already placed remain in the plugin's
usual group and can be removed with **Clear only plugin placed vias**. The final
message separates grid and additional vias and counts unserved islands per
layer (the same XY island on two layers counts twice).

Both passes check newly added vias as well as pre-existing board objects.
These are the plugin's existing geometric checks, not KiCad's complete custom
rule engine. Run KiCad DRC after stitching, including a zone refill. On older
KiCad versions without access to filled polygon geometry, disable refill to
continue using the regular grid.

## Tests

Run the geometry tests without KiCad:

```sh
python3 -m unittest discover -s tests -v
```

With KiCad 10's Python (including `pcbnew` and `wx`) and a desktop session:

```sh
export KICAD_CLI=/path/to/kicad-cli
/path/to/kicad-python tests/kicad_integration.py /tmp/viastitcher-check
python3 tests/check_drc.py /tmp/viastitcher-check
/path/to/kicad-python tests/kicad_gui.py
```

The integration script builds synthetic two-layer boards with a blocked grid
site, disconnected copper, and a backing plane. It checks all three styles,
repeat runs, saved settings, validation, and removal of both passes. The DRC
comparison rejects new violations and additional unconnected items. Native wx
tests check control bounds, overlap, toggling, and loading old/new settings.
The integration fixtures target KiCad 10; the existing plugin compatibility
fallbacks for earlier versions are retained.

## TODO

Some features still to code:
- [x] Match user units (mm/inches).
- [x] Add clear area function.
- [ ] Draw a better UI (if anyone is willing to contribute please read the following section).
- [x] Collision between new vias and underlying objects: 
   - [x] tracks, 
   - [x] zones,
   - [x] pads,
   - [x] footprint zones,
   - [x] modules,
   - [x] vias.
- [ ] Different fillup patterns/modes (bounding box, centered spiral).
- [x] Avoid placing vias near area edges (define clearance).
- [ ] History management (board commit).
- [x] Localization (English and Italian).
- [x] Support for multiple zones
- [x] Storage of stitching configuration for each individual zone as JSON string in a user layer.
- [ ] Any request?

## Coding notes

The dialog is maintained in `viastitcher.fbp` using wxFormBuilder 4.2.1. Do not edit `viastitcher_gui.py` independently: update the `.fbp` project and regenerate the Python file so both representations remain synchronized.

After regenerating the GUI, verify that all controls referenced by `viastitcher_dialog.py` are still present. In particular, preserve the V/H offset controls and their 120-pixel minimum field width.

## Relationship to similarly named plugins

This project was originally published as **ViaStitching**. It was renamed to
**ViaStitcher** to avoid confusion with another KiCad plugin using the similar
name **Via-Stitching**. The projects remain independent and differ in user
interface, features, implementation and development direction.

## References

Some useful references that helped me coding this plugin:
1. https://sourceforge.net/projects/wxformbuilder/
2. https://wxpython.org/
3. http://docs.kicad-pcb.org/doxygen-python/namespacepcbnew.html
4. https://forum.kicad.info/c/external-plugins
5. https://github.com/KiCad/kicad-source-mirror/blob/master/Documentation/development/pcbnew-plugins.md
6. https://kicad.mmccoo.com/
7. http://docs.kicad-pcb.org/5.1.4/en/pcbnew/pcbnew.html#kicad_scripting_reference


Tool I got inspired by:
- Altium Via Stitching feature!
- https://github.com/jsreynaud/kicad-action-scripts

## Greetings

Hope someone find my work useful or at least *inspiring* to create something else/better.
Special thanks to everyone that contributed to this project:
- [Giulio Borsoi](https://github.com/giulio-borsoi)
- [danwood76](https://github.com/danwood76)
- [NilujePerchut](https://github.com/NilujePerchut)
- [canislupus11](https://github.com/canislupus11) — staggered/brick-pattern via placement ([#40](https://github.com/weirdgyn/viastitcher/issues/40))

Last but not least, I would like to thank everyone who shared their knowledge of Python and KiCAD with me: Thanks!
#

Live long and prosper!

That's all folks.

By[t]e{s}
 Weirdgyn
