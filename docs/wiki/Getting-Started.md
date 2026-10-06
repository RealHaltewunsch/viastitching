# Getting Started

1. Open a PCB with a defined outline, assigned nets and a copper zone.
2. Fill the zones in PCB Editor, then select the intended copper zone.
3. Open ViaStitcher. Check the selected net, via diameter and drill diameter.
4. Start with **Standard** (the regular grid), for example 3 mm horizontal and
   vertical spacing. Spacing is measured between via centers.
5. Set additional Edge and Object clearances as required.
6. Enable **Live placement preview** to inspect the result before changing the
   board. Changing values updates the preview after a short pause.
7. Press **OK** to generate vias. A pulsing progress dialog shows activity and
   the number placed. Cancel stops placement and keeps vias already created.
8. Refill zones and run KiCad DRC. Inspect the electrical connections as well as
   geometrical clearances.

To remove the generated result, select the same zone, open ViaStitcher, leave
**Clear only plugin placed vias** enabled and press **Clear**. Existing ungrouped
vias are preserved by this option.

Closing the main dialog without placing or clearing leaves the board unchanged.
The preview never creates PCB objects or saves settings.
