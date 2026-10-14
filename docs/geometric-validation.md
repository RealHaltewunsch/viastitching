# Geometric engine validation — 14 October 2026

Local testing branch from upstream `d7eb10f`. Current environment: native KiCad
10 SWIG/Python/wx on macOS. The package is an experimental testing build.

The engine uses free-space polygons and geometric gap centers. Position
quantization is 0.01 mm. A narrow straight-gap regression needs no rectangle
refinement; all remaining-area checks use geometric exclusion/containment.
No wall-clock timeout or fixed retry budget reports a partial fill as complete.

## Real-board results

Tests use copies, 1.5 × 1.5 mm nominal spacing, 80/150% tolerance, 0.6/0.3 mm
vias, 0.1 mm edge clearance, inherited board/project object clearances and the
at-least-two-layer mode. Existing non-plugin vias are retained. Only the existing
plugin-owned vias were removed from the one supplied board containing that group.

| Local example | New vias | Geometric point probes | Refined rectangles | Geometry + placement |
| --- | ---: | ---: | ---: | ---: |
| Example 1 | 1,026 | 1,237 | 4 | 2.65 s |
| Example 2 | 2,893 | 4,022 | 0 | 13.02 s |
| Example 3 | 2,098 | 2,906 | 3 | 11.97 s |

Timing excludes loading/saving the board, initial zone refill and final full DRC.
Current-source replays were dispatched concurrently; these are recorded local observations,
not an isolated cross-platform benchmark.

- Full KiCad DRC after refilling: **zero new violations and zero new unconnected
  items** for every example. Original violations remain; these boards are not
  claimed to have been DRC-clean initially.
- Full-board translation of Example 3 by 13.37 × 77.23 mm reproduces all 2,098
  relative positions exactly.
- An independent Shapely/SciPy verifier finds **zero remaining insertable
  0.01-mm centers**, checking density spacing, global drilled-hole spacing and
  scoped foreign-plane hole-envelope constraints. The plugin does not depend
  on these verifier libraries.
- Source replay reproduces the DRC-tested positions. This matters because the
  final spatial-index optimization changes how large queries are evaluated,
  without changing the acceptance decisions.

## Regression cases

Eight pure unit tests cover rational rounding, clockwise/counterclockwise ring
order, holes, gap centers, unequal X/Y spacing, exact minimum boundaries, tiny
percentage values on broad spatial queries, rule units and unsupported conditions.

Native regression cases additionally cover:

- narrow and sub-grid gaps; a small triangle with one quantized legal center;
- a region containing no quantized center; holes and independent duplicate gaps;
- foreign-plane protection scoped independently to different copper regions;
- existing same-net vias, anisotropic spacing and the exact 100/100% case;
- inner-layer via keepouts even when net/zone names match;
- at-least-two versus all-enabled-layer copper criteria;
- large foreign-plane interiors remain eligible, while narrow connections are
  protected against being cut by new clearance holes;
- generated GUI, preserved explicit copper-mode label, pre-edit input validation;
- GUI processing, per-zone settings persistence, Clear retaining a manual via;
- cancellation in the geometry stage is byte-identical to the saved board;
- wxFormBuilder-generated UI and native preview screenshot.

## Known limits / remaining release gates

- KiCad 10 on macOS is the exercised environment. Older KiCad versions and
  Windows/Linux have not been qualified.
- The general C++ pairwise DRC evaluator is not exposed to SWIG. Literal
  netclass/netname clearance matrices are handled; unsupported custom distance
  or explicit via/disallow constraints fail before board changes. Rule
  relaxations can be conservatively overruled by stricter inherited minima.
- Foreign-plane neck protection is deliberately conservative: a boundary band
  remains unavailable even when a particular edge notch might be safe. Broad
  plane interiors remain available. This avoids the observed introduction of
  a missing foreign-net connection after refilling.
- Minimum-density coverage does not guarantee an optimal global distribution or
  that every geometric arrangement permits the configured maximum target.
- The generated dialog/controller is tested with native wx/pcbnew; installing
  this exact PCM build and action-menu registration in the running PCB Editor
  remain a manual integration/release gate.
- No public push, PR, tag or release is part of this local validation.
