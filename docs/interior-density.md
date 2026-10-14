# Adaptive density restricted to area interiors — 0.5.2

The geometric engine now preserves nominal local spacing near **tracks, pads,
and all permitted-area boundaries**. Boundary protection is always part of the
optional Adaptive fill density setting; no extra checkbox is needed.

## Rule

The same start/full distances apply to both copper proximity and area boundaries.
The density factor uses the **smaller** normalized distance to either feature.
With a 1.5 mm nominal spacing and 100/300% defaults, the local factor stays 1
up to 1.5 mm from the nearest feature, increases linearly between 1.5 and
4.5 mm, and reaches 3 only at least 4.5 mm away from **both**.

Boundaries are captured from the permitted via-center topology before any new
vias are placed. This accounts for outer area/board limits, filled-copper holes,
clearance obstacles and disconnected islands. Because these are via-center
boundaries (already inset by via radius/clearances), the band is conservative
relative to the raw copper edge. Same-net via drill holes are not used to alter
the density topology, and generated vias never modify the frozen field.

The engine **fills dense edge/pad bands first**. It then grows into the interior
and completes remaining geometric gaps with the same density/minimum-distance
checks. This prevents a sparse interior seed from consuming a still-insertable
dense edge position. It does not promise a fixed raster phase, an optimal
packing, or impossible spacing around existing manually placed vias.

Narrow regions without a deep interior stay dense. Holes and each disconnected
island have their own edges. X/Y normalization, existing-via spacing, grouping,
Clear, and cancellable pulsing progress remain in effect. Component proximity
uses actual pad copper, as in the original density option; mechanical body and
silkscreen outlines are not simulated.

## Checks

16 pure tests include rectangular edges, holes, anisotropic boundary distances
and narrow islands. Native tests explicitly verify that the dense band is placed
before sparse interior vias, local factor 1 at protected edges, factor 3 in deep
interiors, spacing compliance, no remaining insertable sampled edge positions,
hole protection and an unchanged dense pattern on a narrow strip. Existing
geometry, contour, GUI/config and cancellation regressions remain applicable.

Real-board tests use fresh copies of the same three references as the original
geometric engine: 1.5 × 1.5 mm, 80/150%, 0.6/0.3 mm vias, edge margin 0.1 mm,
inherited rules, at-least-two copper layers.

| Example | New vias | Geometry + placement | New DRC violations / unconnected |
| --- | ---: | ---: | ---: |
| 1 | 1,059 | 8.00 s | 0 / 0 |
| 2 | 2,422 | 56.58 s | 0 / 0 |
| 3 | 1,937 | 57.09 s | 0 / 0 |

Timing excludes loading/saving, initial zone refill and final full DRC. These
concurrent local runs are not a platform benchmark. Existing DRC violations
remain; each final board was refilled and checked with its associated project.

Independent Shapely/SciPy verification passes all generated-via/local-anchor
spacing, allowed geometry, global physical spacing and scoped foreign-plane
constraints, finding zero remaining insertable 0.01-mm positions on each copy.
Disabled-option replay preserves all original geometric-engine positions.
Whole-board translation by 13.37 × 77.23 mm reproduces all 1,937 relative
positions on Example 3 exactly.

Protecting edges intentionally reduces the amount of thinning compared with
0.5.1. Total via counts can even increase on mostly narrow regions because the
new candidate ordering fills the dense bands first. This is not a guarantee
of fewer total vias on every board.

The documented KiCad 10/macOS scope and limits for arbitrary custom DRC rules
remain unchanged. PCB examples and project contents stay local; only anonymized
results are included in the feature branch.
