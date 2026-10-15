# Perimeter placement and foreign-zone gap coverage — 0.5.4

This is an experimental KiCad 10 SWIG release of the new placement engine.

## The reported failure

Version 0.5.3 discarded a band around foreign filled-zone boundaries, plus
nearby hole-envelope positions. On a real four-layer PCB this excluded two
visually empty gaps although vias there connected the selected net on two
layers and KiCad could refill the other net around them without a new DRC
violation. Coverage tests against that restricted domain could pass while the
user-visible result was wrong.

Three individually added regression vias in the reported gaps were checked by
KiCad with project rules and zone refill: no new violations or unconnected
items. The new engine admits all three locations. Private PCB files, project
settings and board-identifying screenshots are not part of the repository or
release assets.

## Placement order

- Build actual permitted **via-center** polygons using native filled copper,
  drill/object clearances, board edges and via keepouts. This already accounts
  for via size: do not erode the resulting regions by the diameter again.
- Process separate areas in ascending polygon area, with stable geometric tie
  breakers. Small/narrow areas start near their area centroid; interior
  cross-section centers handle concavity and holes.
- For larger areas, use inward offset contours in normalized X/Y coordinates.
  Sample each contour at nominal arc spacing, quantize candidates to 0.01 mm,
  and check the same physical and spacing rules for every candidate.
- With adaptive density, process the protected dense band first and **defer**
  inner contour fronts to the interior stage. The fixed density field depends
  on track/arc/pad copper and permitted-area boundaries, not generated vias.
- Existing same-net vias and newly accepted vias share the minimum-distance
  index across all areas. The larger endpoint density factor sets the minimum
  distance. Remote regions impose no raster phase or growth direction.
- Local geometric projection and residual polygon/rectangle checks handle
  blocked contour targets. There is no wall-clock search timeout and no
  whole-board 0.01-mm pixel enumeration.

## Foreign copper

A filled foreign zone may acquire clearance holes during KiCad refill. The new
connectivity guard tracks its minimum-width core and reconstructed copper,
fixed tracks/pads/vias, and pad/via connections across enabled layers. Accepted
holes update this model immediately. A split separating only unanchored copper
is allowed. A split that breaks an existing pad/via connection is rejected.
Native point queries and cached unchanged polygons avoid repeated Python scans
and offsets during graph checks.

A rejected hole can also provide a **geometric exclusion certificate**. If a
smaller hole still breaks the connection, every full-size hole containing that
smaller polygon also breaks it: copper removal is monotone. The maximum safe
center displacement is bounded using actual polygon vertex distances, with
additional numerical margin. Entire candidate rectangles inside a certified disk
are discarded without repeating connectivity searches at 0.01-mm increments.
Certificates are generated only by successful disconnection proofs, not by a
time limit or a generic band around foreign copper. The synthetic regression
checks fresh uncached decisions at their extrema and an allowed off-neck point.

This guard is a geometric model, not KiCad's complete project-rule evaluator.
Run project-aware KiCad DRC with zone refill after placing vias. Supported
custom-clearance matrices and fail-fast handling of unsupported custom rules
remain unchanged; arbitrary KiCad DRC expressions are outside this release.

## Validation

Portable tests cover geometry, exact anisotropic spacing, small-region area /
centroid, density interpolation, boundaries, input limits and rule parsing.
Native regressions cover inward fronts, translations, narrow gaps, holes,
track-separated regions, existing vias, density controls and persistence,
all-versus-two-layer mode, cancellation and shared Clear behavior.

The foreign-copper fixture checks a sole pad connection, an unanchored fragment,
a fixed-copper bypass and an accumulated series of holes that would sever a
connection. Actual PCB comparisons use copies with only old plugin-group vias
removed; manual vias and other objects are retained. DRC and independent
spacing/coverage checks are separate from the engine's completion message.

Recorded release results are below. Timings include geometry, density and
placement and are machine/workload dependent; they are not a performance SLA.


| Private fixture | Nominal X/Y | Adaptive start / full / factor | New vias | Geometry + placement | New DRC violations | New unconnected items |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| Example 1, current saved PCB | 2 / 2 mm | 150% / 300% / 2 | 958 | 78.4 s | 0 | 0 |
| Example 2 | 1.5 / 1.5 mm | 100% / 300% / 3 | 3,440 | 258.5 s | 0 | 0 |
| Example 3 | 1.5 / 1.5 mm | 100% / 300% / 3 | 2,485 | 427.6 s | 0 | 0 |

Via geometry was 0.6 / 0.3 mm, with 80% / 150% spacing tolerance and the
at-least-two-layer mode. Example 1 uses the saved current density settings;
Examples 2 and 3 use the documented defaults. On Example 1 the two reported
empty rectangles now receive 5 and 20 vias respectively (previously zero).
Three known individually DRC-valid positions are admitted by the new geometry.

On Example 3 the uniform reference run places 2,985 vias. Adaptive placement
uses 500 fewer overall (16.8%); deep-interior vias decrease from 197 to 24
(87.8%). The local nominal rule remains dense near boundaries/track/pad copper;
the placement order can change which positions are chosen and their count.
Adaptive density is optional, remains off by default and retains configurable
start/full distances and maximum factor.

The large Example 3 run completes without a search timeout. Its original
foreign-connection tail repeatedly examined thousands of similar invalid
positions; exclusion proofs reduce actual disconnection rejections to five.
The reported minutes are real measured costs on the larger fixtures, not a
claim that every board finishes in seconds. KiCad's separate full refill + DRC
on Example 3 takes about 311 seconds.

Independent Shapely/SciPy checks pass global same-net spacing, physical spacing,
quantization and residual-area coverage. Example 3 has one residual area whose
exclusion additionally depends on the foreign-copper connectivity model: its
holes are reconstructed in bulk separately from the placement engine. The
independently found candidate there was also inserted on a separate PCB copy:
KiCad reports **one new unconnected item**, confirming that it must be rejected,
with no new ordinary clearance violation. Thus spacing/geometry coverage and
foreign-net connectivity are checked separately; a completion flag is not the
coverage evidence.

The installable PCM ZIP itself passes native GUI, settings, cancellation, Clear,
density, spacing and connectivity fixtures; portable CI runs 17 tests and
compiles/packages the committed source. Validation is on KiCad 10 / macOS;
other KiCad versions and operating systems are not established by these runs.
