# Local validation — 6 October 2026

Environment: KiCad 10 native SWIG/Python/wx runtime on macOS. This is a local
0.4.0 testing build, not an upstream release or completed compatibility matrix.

## Results

- Eight Python test methods pass, including exact legacy coordinates across 27
  combinations of pattern, bounds and offsets; deterministic Randomize uses a
  fixed seed. Spiral/packing separation and broad-phase indexing are covered.
- Native upstream 0.3.4 comparison: identical resulting positions for Standard
  (54), Stagger (55) and Randomize (54) on the regression fixture. The historical
  reference needs a KiCad-10-only width-call adapter, documented in the test.
- Native shared-engine tests: Standard 54, Stagger 55, Randomize 54, Spiral 44,
  Maximize 231 accepted positions. Preview and placement match exactly for each.
- Board serialization before/after preview is byte-identical. Opening and
  cancelling the dialog preserves layer names. Mode switching and the running
  preview are tested with the generated wx dialog.
- Clear preserves an ungrouped manual via. Edge/Object clearance increases
  monotonically remove fixed-grid positions. Segment centering is repeatable
  (56 positions on the fixture). Via-only keepouts and four-layer through-via
  collisions are covered.
- Full native DRC comparisons for five modes and segment centering: no new
  violation identities; zero unconnected items after placement on these fixtures.
- wxFormBuilder regeneration is byte-identical to committed generated Python.
- PCM metadata validates against the official schema; ZIP integrity, Python
  syntax and every packaged source file are checked.
- The native functional tests also pass when implementation modules are loaded
  from the extracted PCM ZIP instead of the checkout.

## Representative performance

Synthetic 100 × 80 mm board, 3 mm Grid/Spiral pitch; Maximize center spacing
1.5 mm. These measure generation plus validation, not PCB Editor rendering.

| Mode | Candidates | Accepted | Seconds |
| --- | ---: | ---: | ---: |
| Standard | 832 | 828 | 0.31 |
| Spiral | 845 | 806 | 0.31 |
| Maximize | 15,726 | 3,825 | 5.64 |

Maximize uses a smaller configured separation in this comparison. The figures
are a runtime/density illustration, not proof of optimal packing or a like-for-
like spacing comparison. Re-run `tests/kicad_performance.py` for local timings.

## Not yet verified / not published

- KiCad 6–9 and Windows/Linux runtime/GUI compatibility.
- PCM-manager installation and menu registration inside PCB Editor. Direct
  action-plugin registration in standalone KiCad Python fails because that
  process does not provide PCB Editor's application context. The isolated
  package tests exercise the dialog/engine, not that application integration.
- Upstream Wiki publication, issue/milestone disposition and official release
  workflow. Current GitHub permissions are read-only for the upstream repository.

The manual documents finite segment-probing resolution and custom-DRC-rule
limitations. These checks do not establish arbitrary-board safety. Run DRC on
actual boards and complete the release gates in `roadmap-040.md` before releasing.

## Keepout fix integration — 14 October 2026

Ported `RealHaltewunsch/viastitching` commit `0686fc3` from
`fix/respect-via-keepouts` onto the roadmap engine. Board and footprint rule
areas are collected independently of net/name, and native polygon collision
checks use the via's actual copper-layer span and radius. Ordinary zones with
stale restriction flags are ignored.

- Eight pure test methods and the existing native roadmap suite pass.
- `tests/kicad_keepouts.py` passes same-name/same-net, inner-layer, blind-via,
  allowed-via, ordinary-zone, circular-corner, polygon-hole and footprint cases.
- Preview/placement equivalence and keepout exclusion pass for all five modes
  plus centered Standard.
- `tests/check_drc.py` on those six before/after pairs reports no new violations
  and zero unconnected items in KiCad 10 on macOS.

The previously built PCM archive predates this fix; these results describe the
updated source branch. The compatibility and installation gates above remain open.
