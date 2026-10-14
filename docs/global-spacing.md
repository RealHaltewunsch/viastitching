# Shared minimum spacing across separate areas — 0.5.3

The geometric engine now checks the user minimum spacing across **all**
permitted regions of the selected net, including opposite sides of a track.
Local placement growth, preferred direction and maximum-neighbor targets remain
independent for each region. The shared index only excludes points that are too
close; it does not force a global grid phase.

## Mathematical rule

Let `sx, sy` be the nominal X/Y spacings, `m` the minimum percentage divided by
100, and `f(p)` the immutable adaptive spacing factor at a point (1 when density
is disabled). A candidate `p` and same-net via `q` must satisfy

```
((px - qx) / sx)^2 + ((py - qy) / sy)^2
    >= (m * max(f(p), f(q)))^2
```

At 1.5 × 1.5 mm, 80% minimum and factor 1, that means at least **1.2 mm
center-to-center** even across a track. The 20% configured tolerance remains
intentional. Unequal X/Y spacings define an ellipse. Farther vias outside the
exclusion neighborhood do not align, attract or otherwise influence the local
placement. With adaptive density, the larger endpoint factor applies symmetrically.

The implementation compares integer squared distances after multiplying out the
rational denominators. No square root, repeated full-board scan or discretized
search of every 0.01-mm point is needed. Spatial buckets retrieve only nearby
vias. Conservative polygonal exclusion shapes accelerate subtraction; exact
pair checks remain authoritative, including at the configured equality boundary.

## Integration

- All existing same-net vias are registered before the first region is placed,
  even when they belong to a region processed later or lie outside the selected
  region. Both manual and previous plugin vias count.
- Every new via immediately enters the shared spacing index. Existing vias are
  never moved or deleted; pre-existing pairs that violate a newly configured
  density minimum remain unchanged.
- Each region still maintains its own growth history. A via across another
  region's boundary cannot become a maximum-distance growth parent there.
- Dense edge/pad bands, frozen adaptive density, physical/drill constraints,
  foreign-plane protection, grouping and cancellation remain in effect.
- This correction also applies with adaptive density **disabled**. Positions
  previously allowed to be too close across region boundaries can therefore
  change compared with 0.5.2; byte-identical replay of the older behavior is no
  longer the goal.

## Tests

Native regressions cover narrow track-separated flanks, a real KiCad foreign-net
track splitting allowed polygons, a manual via owned by the region processed
last, exact preservation of far independent groups, unequal X/Y spacings,
symmetric adaptive factors, repeatability and translation. Pair distances are
verified independently from the placement index. Previous geometry, density,
GUI/settings, cancellation, Clear and keepout tests also pass.

Fresh copies of the three supplied reference boards use 1.5 × 1.5 mm, 80/150%,
0.6/0.3 mm vias, edge clearance 0.1 mm, inherited project rules, at least two
copper layers, adaptive 100/300% with factor 3 and the interior-only edge rule.
Project-aware DRC and independent global pair/remaining-area verification pass
on all three copies:

| Example | New vias | Geometry + placement | New DRC violations / unconnected |
| --- | ---: | ---: | ---: |
| 1 | 1,048 | 8.67 s | 0 / 0 |
| 2 | 2,563 | 57.71 s | 0 / 0 |
| 3 | 1,905 | 61.48 s | 0 / 0 |

Times exclude load/save, initial copper refill and final full DRC; concurrent
local observations are not a platform benchmark. Original DRC violations remain.
The independent verifier checks all generated vias against the full global set
of new vias and every existing same-net anchor. All global density/physical and
scoped foreign-plane constraints pass, with zero remaining insertable 0.01-mm
positions under the applied rules. Translating the whole third board by
13.37 × 77.23 mm reproduces all 1,905 relative positions exactly.

The shared exclusion changes subsequent seed choices; maximal geometric
coverage does not guarantee optimal packing or monotonically fewer vias after
adding a constraint. Existing KiCad 10/macOS and custom-rule qualification limits
remain as documented in the other validation reports. PCB contents remain local.
