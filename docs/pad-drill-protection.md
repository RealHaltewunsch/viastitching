# No stitching drills in component pads — 0.5.5

Version 0.5.4 allowed stitching vias inside same-net pads because electrically
connected copper is not a normal clearance violation. On the private Example 3
fixture, an independent native-shape audit finds **134 generated drill disks**
overlapping component pads (173 contacts across copper layers), all same-net.
An electrical DRC pass therefore did not establish this manufacturing policy.

Version 0.5.5 excludes the actual pad contour expanded by **half the via drill
diameter**, plus the existing small numerical guard. This excludes a drill even
if its center is just outside the pad but its edge would cut into it. The rule
covers all enabled copper layers traversed by the through via, regardless of the
at-least-two/all-layers connection setting. It is always enabled, and applies to
both uniform and adaptive placement through their shared permitted geometry.
It does not impose an unrelated foreign-net copper-clearance margin on same-net
pads. Existing pad-drill spacing, foreign-net clearances and keepouts are retained.

Native fixtures cover rectangles, circles, rotated rectangles/ovals, rounded
rectangles, a concave custom pad and an inner-layer pad. A plated pad's annulus
is protected beyond the old existing-hole exclusion. Checks include drill-edge
intersection with a center outside the pad, an allowed nearby point, and free
corners/notches that a pad bounding box would incorrectly exclude. Both adaptive
states and the all-layers connection mode are tested.

`tests/native_pad_audit.py` independently checks every generated drill disk using
KiCad's **unexpanded effective pad shapes** and native circle collision, rather
than reusing the expanded exclusion polygons. It checks all nets and copper
layers, distinguishes generated vias by their recorded IDs and preserves existing
manual vias. Run it with `--expect-clean` to fail on any overlap. These are native
KiCad tests, separate from portable GitHub CI and ordinary electrical DRC.

Tests use the same three private baseline copies as the 0.5.4 report, with only
old plugin-group vias removed. Existing manual vias and other objects remain.
Via dimensions are 0.6 / 0.3 mm; minimum/maximum spacing 80% / 150%. Example 1
retains 2-mm pitch, adaptive 150% / 300% / factor 2; the other examples use
1.5-mm pitch and 100% / 300% / factor 3. Current results (KiCad DRC with project rules and zone refill is checked separately):

| Private fixture | Generated vias | Drill/pad overlaps | New DRC violations | New unconnected items |
| --- | ---: | ---: | ---: | ---: |
| Example 1 | 938 | 0 | 0 | 0 |
| Example 2 | 3,397 | 0 | 0 | 0 |
| Example 3 | 2,408 | 0 | 0 | 0 |

The independent spacing/remaining-area audit also passes. Its completeness
probe uses the strict permitted polygon interior: GEOS `covers` includes
exclusion-boundary points which KiCad rejects. Every generated position is
still checked against the closed geometry and every drill against raw pads.

No private PCB/project files are included in the source or installable package.
Existing vias from an earlier run are not silently removed: use **Clear only
plugin placed vias**, refill copper and rerun. Manual vias are preserved.
