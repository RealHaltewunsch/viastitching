# Troubleshooting and Compatibility

The project targets the existing SWIG Action Plugin architecture and KiCad 6+.
This local development build has been exercised with KiCad 10 on macOS. A full
KiCad 6–9 and cross-platform release matrix has not yet been executed; those
versions must not be described as independently verified for this build.

If the plugin is missing, check that its complete directory is installed under
the user scripting plugins path for the KiCad version you are running, then
restart KiCad. Remove duplicate manual/PCM installations.

If the dialog cannot obtain valid via dimensions, configure a diameter and drill
in Board Setup. Select a copper zone and fill zones before launching the plugin.
A zone with no suitable filled copper can legitimately produce zero vias.

If preview shows no accepted points, inspect the rejection counts. Check the
selected net, filled-copper layer requirement, via diameter, spacing and the two
clearances. A large diameter or margin can remove an entire narrow region.

Keep KiCad DRC as the final authority. Report the KiCad/plugin versions, operating
system, selected style, dimensions, settings and a minimal shareable example
when reporting a problem. Do not attach confidential board files to a public
issue unless you intend to disclose them.
