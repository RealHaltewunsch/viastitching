# Target Via Count evaluation — roadmap #61

Decision for this implementation proposal: **defer** the user-facing mode beyond
0.4.0. This is a proposed disposition for maintainer review, not a unilateral
change to the upstream milestone.

Use case: a user has a drilling/thermal via budget N and wants a well-distributed
feasible subset. N cannot imply sufficient electrical/thermal performance. The
objective should be maximum separation over the usable area, not central
concentration or merely taking the first N accepted points.

| Approach | Strength | Limitation / cost |
| --- | --- | --- |
| Automatically choose grid pitch | Familiar appearance and preview | Obstacle-driven valid counts are not monotone in pitch; binary search does not guarantee a target. O(KM) for K trials with M geometric checks. |
| Uniform area allocation | Can account for disconnected areas | Requires defining allocation to tiny islands and usable-area computation. A requested integer count does not map uniquely to area fractions. |
| Farthest-point selection | Deterministic, explicitly maximizes separation greedily | Candidate-pool dependent; not globally optimal. Cached distances give O(MN) time and O(M) memory for M valid candidates. |
| Subset of Maximize proposals | Reuses geometry and preview | Inherits candidate bias; simply taking the first N would concentrate the result. Needs the separate subset objective above. |

Recommended future design: build a finite validated candidate pool, then select
N points with deterministic farthest-point sampling and stable tie-breaking.
Maintain a configured physical minimum separation; diameter, drill, net,
clearances and filled-copper requirements remain applicable. Grid offsets are
inactive; an inferred equivalent pitch may be displayed, not treated as a
competing user input. If only K<N feasible points exist, report Target N /
Placed K. Never relax physical checks to hit the target.

The proposed UI requires separate explanation of target count versus minimum
separation and a strategy for disconnected islands. Those choices add another
optimization objective and acceptance matrix to an already broad engine release.
Deferral keeps the count mode distinct from Maximize and avoids misleadingly
claiming exact-count guarantees.

Reference reviewed: the public `nilskiefer/viastitching2.0` implementation uses
Maximize candidate pools and a center-seeded farthest-subset selection. Its
selection repeatedly scans distances to all selected points; a distance-cache
implementation would avoid that repeated work. No code from that fork was
copied into this implementation. Its behavior is a design reference rather
than the specification for this release.

https://github.com/nilskiefer/viastitching2.0/blob/main/viastitching_dialog.py
