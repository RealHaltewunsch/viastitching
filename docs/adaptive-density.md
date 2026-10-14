# New geometric placement engine with adaptive fill density

Feature branch: [`feature/geometric-adaptive-density`](https://github.com/RealHaltewunsch/viastitching/tree/feature/geometric-adaptive-density).
Experimental PCM version: **0.5.1**, based on upstream master `d7eb10f` and the
new geometric-engine commit `05710ed`. The branch includes the complete placement
rewrite: permitted via-center polygons, direct gap centers, local growth,
0.01-mm positions, geometric remaining-area checks, and no separate refill pass.

## Controls and distance model

Enable **Adaptive fill density** to increase spacing in copper-poor areas.
Defaults are start **100%**, full **300%**, maximum factor **3**. Start is at
least 100%, full must exceed start, and factor is an integer at least 1. All
values must be finite and derived dimensions must fit KiCad's coordinate range.
Invalid active settings stop before any board changes. Settings are saved per
zone. The default for old configurations without density settings is disabled;
previous `SparseGrid` settings are recognized.

Actual track, arc and pad copper contours of all nets on all enabled copper
layers form an immutable proximity field. Track widths, pad shapes and rotation
are included. Zones, vias, component outlines and text have no influence.

For nominal spacings `sx, sy`, distances use the normalized metric
`sqrt((dx/sx)^2 + (dy/sy)^2)`. If copper-edge distance is `r`, the factor is

```
f(r) = 1 + (M - 1) * clamp((r - start) / (full - start), 0, 1)
```

At 1.5 × 1.5 mm and default settings: unchanged local target up to 1.5 mm,
linear increase from 1.5 to 4.5 mm, then a 4.5 × 4.5 mm local target. Factors
are stored to six decimal places for deterministic pair decisions; generated
via positions remain quantized to 0.01 mm.

Both spacing tolerances apply to the local target. For a candidate and a via,
the larger endpoint factor sets their symmetric pair spacing. Existing same-net
vias are included in their free region's spacing index. Independent free regions
keep their separate density distributions; physical drilled-hole and scoped
foreign-plane constraints still apply across the relevant regions.

The new engine scales its preferred local spacing. It does not require a global
raster phase, and its remaining-area search cannot restore the original dense
pitch in an adaptively sparse area. Minimum coverage is geometric, not globally
optimal. Maximum spacing remains a growth target that blocked geometry may make
unachievable. A mixed near/transition area need not have identical individual
positions or near-area counts after enabling the option: symmetric spacing to
larger-factor neighbors and candidate ordering also affect the distribution.

The field is a geometric heuristic, not a calculation of current flow or return
paths. The pulsing progress dialog remains active through geometry, density-field
construction and placement. Cancel preserves already placed vias and marks the
operation incomplete. Grouping and Clear remain shared with ordinary placement.

## Recorded validation — 14 October 2026

Native KiCad 10 Python/wx on macOS; three disposable PCB copies. Nominal spacing
1.5 × 1.5 mm, 80/150% tolerance, 0.6/0.3 mm vias, edge margin 0.1 mm,
inherited board/project clearances, at-least-two copper-layer mode. Non-plugin
vias and all other original objects are retained.

| Example | Density off | Density on | Reduction | Geometry + adaptive placement | New DRC violations / unconnected |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 1,026 | 838 | 18.3% | 7.89 s | 0 / 0 |
| 2 | 2,893 | 2,167 | 25.1% | 32.64 s | 0 / 0 |
| 3 | 2,098 | 1,413 | 32.7% | 33.22 s | 0 / 0 |

Times exclude load/save, initial refill and final full DRC. Runs were concurrent
and are local observations, not an isolated platform benchmark. Source replay
reproduces the DRC-tested positions.

Via counts classified by distance to the same immutable copper field:

| Example | Off: near / transition / far | On: near / transition / far |
| --- | ---: | ---: |
| 1 | 646 / 334 / 46 | 687 / 123 / 28 |
| 2 | 1,761 / 1,016 / 116 | 2,028 / 139 / 0 |
| 3 | 1,168 / 724 / 206 | 1,157 / 226 / 30 |

- Disabled-option replay exactly preserves all 1,026 / 2,893 / 2,098 positions
  from the preceding geometric engine.
- Translating the whole third board by 13.37 × 77.23 mm exactly preserves all
  1,413 relative adaptive positions.
- An independent Shapely/SciPy verifier checks every new via against its local
  density index and existing same-net anchors, permitted polygons, physical
  hole distances and scoped foreign-plane hole envelopes. It finds zero
  remaining insertable 0.01-mm positions under those constraints for all three
  copies. The plugin has no dependency on these verifier libraries.
- 15 pure tests cover contour distance, holes, anisotropic normalization,
  near/transition/far boundaries, symmetry, exact distance thresholds, bounded
  indexing of oversized contours and validation, plus earlier engine/rule tests.
- Native tests cover actual widths/arcs, round/oval/rect/roundrect and rotated
  pads; zones/vias leaving the field unchanged; factor-one and uniform-near
  parity; far reduction; existing anchors; deterministic repeated/translated
  placement; exhaustive small transition-area completion; checkbox/default-off,
  invalid input, per-zone persistence and common Clear.
- Native earlier engine/GUI regressions still pass, including cancellation,
  manual-via preservation, layer mode and keepouts. Density extraction is also
  cancellable before board edits. The generated dialog was inspected visually.

## Limits

The full arbitrary KiCad DRC evaluator remains unavailable in SWIG. Supported
literal net/netclass clearance matrices are handled; unsupported via-relevant
custom rules fail before changes. Foreign-plane boundary/neck protection is
conservative. Tests qualify KiCad 10 on macOS; other platforms/versions and
installation/action registration of this exact PCM in the running PCB Editor
remain unqualified. This branch is experimental and does not change upstream
master or create an upstream PR.
