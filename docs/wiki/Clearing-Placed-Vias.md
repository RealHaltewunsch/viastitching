# Clearing Placed Vias

Vias created for a zone are put into its ViaStitcher group. With **Clear only
plugin placed vias** enabled, Clear removes vias belonging to that zone's group.
Manually placed, ungrouped vias remain unchanged.

If you disable that option, Clear removes vias inside the selected filled zone
matching the chosen net, via diameter and drill. This broader operation may
remove hand-placed vias too.

Group membership is the ownership record. Moving vias between groups or
renaming the zone/group can prevent the plugin from recognizing them. There is
no UUID ownership database, orphan cleanup or new Undo/Redo integration in this
release cycle. Save the board before large changes and verify what will be
cleared. Preview itself never creates a group.
