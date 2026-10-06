# Placement Modes

## Standard (Grid)

A global rectangular grid using independent horizontal/vertical spacing and
offsets. Obstacles reject individual positions. Surviving positions keep their
original grid phase unless segment centering is enabled.

## Stagger

The same grid, with every second row shifted by half the horizontal spacing.
The vertical spacing and offset retain their Grid meaning.

## Randomize

Each normal grid position is shifted by up to one fifth of the respective
horizontal and vertical spacing. Every proposed position still needs to pass
all placement checks. A fixed random seed within one dialog session keeps the
preview consistent with placement. Reopening the dialog starts another seed.

## Spiral

An Archimedean spiral starts at the selected zone's bounding-box center and
expands outwards. Horizontal/vertical spacing scales the pattern independently;
equal values produce a circular spiral. The common spacing checks suppress
crowded proposals. A rejected point does not stop the outward search.

The bounding-box center can lie outside a concave zone or inside a cutout.
Such positions are rejected normally. Grid offsets and segment centering are
not used by this mode.

## Maximize

A deterministic packing heuristic proposes a hexagonal distribution followed by
three shifted passes. Valid candidates are accepted when they respect the
configured minimum center separation and all shared physical checks. It is a
finite search, not a proof of the mathematical maximum. Obstacles can leave
unused gaps even after all passes.

Use **Minimum via spacing** instead of the disabled Grid spacing/offset fields.
The board's physical hole spacing also remains in effect.

## Centering separate row segments

For Standard and Stagger, enable **Center each usable row segment** to divide a
row at obstacles and center an equally spaced set within each usable interval.
The largest regularly spaced set fitting the detected interval is used. The
horizontal offset and the alternating stagger phase are replaced by this
centering rule. Vertical row phase remains unchanged.

Usable intervals are found by finite probes at the smaller of one twentieth of
the horizontal pitch and one quarter of the via diameter. Detected transitions
are refined to one internal coordinate unit. Very narrow valid intervals between
probes can remain undiscovered. Every final candidate is validated again.

## Target Via Count

Not implemented in this development build. It remains a separately evaluated
proposal, not a hidden Maximize setting.
