# Configuration

Settings are stored inside the board, per named zone, in the plugin's existing
hidden configuration text. No extra persistent project file is introduced.
Unnamed zones receive a unique name when placement is applied.

Spacing, offsets, style, filled-copper preference, both clearances, minimum
Maximize spacing and segment centering are saved when placing. Via dimensions
are initialized from Board Setup. Preview is session-only and initially off.
Closing or cancelling the main dialog does not save edited settings.

Old boards may contain the legacy ViaStitching configuration marker; it remains
accepted. Missing new fields receive defaults: Object clearance 0.35 mm,
segment centering off, and the ordinary default spacing for Maximize. Existing
style checkbox settings still migrate to the mode selector; Randomize takes
precedence if both legacy style checkboxes were enabled.

Edge clearance retains the old Clearance field. Previously it also influenced
some object checks indirectly; the two new controls now have separate meanings.
Review clearances after upgrading rather than assuming old mixed margins are
identical. Corrupt configuration text is ignored; invalid numeric settings must
be corrected in the dialog before placement.
