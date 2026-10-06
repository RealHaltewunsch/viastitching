# 0.4.0 implementation and release review

Base: upstream `weirdgyn/viastitcher` master, commit
`5947e23a0ced0298581365f50436700348e1df88` (0.3.4). The experimental
adaptive-refill/density branches are not part of this worktree.

## Local implementation status

- #55: separate candidate generation, categorized validation and via creation.
  Validation uses a non-PCB geometry adapter. Pure coordinate tests preserve the
  upstream loop; the native test compares complete resulting coordinates.
- #56: separate Edge/Object margins; zero never skips physical overlap/boundary
  checks. Board minimum hole spacing replaces a hidden fixed hole-distance
  value when the SWIG API exposes the board setting.
- #57: optional, debounced incremental preview, read-only board behavior and
  categorized counts; same decision stream used for placement. Rendering is
  capped at 20,000 points but candidate evaluation is not sampled.
- #58: centered Archimedean spiral; rejected positions do not stop generation.
- #59: deterministic four-phase hexagonal packing heuristic, dedicated center
  separation and shared validation. No global-optimality claim.
- #60: optional per-row segment centering with bounded probing/refinement.
  See the manual for resolution and offset semantics.
- #61: evaluation completed locally; deferral recommended in
  [target-via-count.md](target-via-count.md), subject to maintainer acceptance.
- #62: authoritative wxFormBuilder GUI updated and regenerated; mode-specific
  fields disabled, missing configuration keys defaulted.
- #63: exact grid coordinate oracle and native before/after, preview/placement,
  clear/manual-via preservation, GUI and DRC fixtures included.
- #66: user manual source prepared in [wiki/Home.md](wiki/Home.md). The current
  development screenshot is included. Publishing the upstream Wiki remains release-gate work.
- #64: **not released**. Version 0.4.0 is used only for the local PCM testing
  build, marked development in the dialog and testing in metadata. Do not tag or label this work as a completed stable
  0.4.0 release until the gates below are satisfied.

## Intentional differences and compatibility

The baseline is the user-selected current master (0.3.4), rather than resetting
bug fixes to the older 0.3.0 referenced by the roadmap. Grid generation preserves
its exact order/phase/jitter. The clearance issue intentionally separates formerly
mixed margins. Boundary checks now retain a full via body at Edge=0, handle
outline holes as separate rings, and reject positions outside a valid board
outline. Generated vias are included in virtual hole-separation checks, including
in preview. Foreign-net arcs and via-only rule areas now participate in collisions.
Through-via collision checks include enabled inner copper layers even when the
selected zone covers only the outer layers. A spatial broad-phase index limits
object scans without discarding objects near but outside the zone bounding box. Opening the dialog
no longer renames a board layer before Apply.

KiCad 10 requires a layer argument when reading via diameter; the native baseline
comparison uses an API-only adapter for that historical source. Runtime code
falls back to the older no-argument API for KiCad 6–9.

Issue #64 names `com.github.weirdgyn.viastitching`, but the selected upstream
already renamed the identifier to `com.github.weirdgyn.viastitcher`. Preserve the
actual upstream identity; obtain maintainer confirmation before the release gate.

Reference forks reviewed individually:
- https://github.com/narottamroyal/viastitching — separate clearance/shape checks.
- https://github.com/nilskiefer/viastitching2.0 — preview, packing, segment and
  target-count concepts. No implementation code was copied. IPC/ownership and
  Undo/Redo changes remain excluded, as required by #54/#65.

See [the recorded local results and unverified gates](validation-040.md).

## Validation commands

```
python3 -m unittest discover -s tests -v
python3 -m py_compile placement_engine.py viastitcher_dialog.py viastitcher_gui.py
# Using the Python bundled with KiCad, including wx and pcbnew:
python3 tests/kicad_pipeline.py
python3 tests/kicad_roadmap.py /tmp/roadmap-fixtures
python3 tests/check_drc.py /tmp/roadmap-fixtures
```

`GIT_BIN` can select an independent Git runtime when Apple Git is unavailable.
`KICAD_CLI` can override the DRC executable. Fixture tests use synthetic boards,
not user project files.

## Remaining release gates

- Confirm the final included feature list and Target Via Count disposition with
  the upstream maintainer; do not close upstream issues on the basis of local work.
- Exercise the supported KiCad/OS matrix. Local KiCad 10 checks do not prove
  KiCad 6–9 compatibility or Windows/Linux GUI behavior.
- Complete maintainer acceptance review of the recorded representative performance
  and narrow-region checks, including the finite segment probe resolution.
- Review translated strings, final screenshots and user manual; publish Wiki
  pages and replace the README's local manual link with a verified Wiki link.
- Create the dedicated stable release-preparation commit only after the intended
  feature gates pass; remove the development marker and update PCM status then.
- Validate PCM schema and package/source identity, then install that exact
  archive and verify startup, Grid/Stagger, a new mode, configuration and Clear.
- Only after approval: push the release commit/tag, verify Actions and downloadable
  artifacts, and close the milestone after upstream acceptance.
