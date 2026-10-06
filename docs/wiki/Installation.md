# Installation

For a published release, use KiCad's Plugin and Content Manager when the plugin
is available in your configured repository. For a downloaded PCM ZIP, use
**Install from File** in that manager. Restart KiCad after installation or upgrade.

For manual installation, put the complete plugin directory in your KiCad
version's per-user `scripting/plugins` directory. Keep all Python files, icons
and the `locale` directory together. Find the user plugin directory from your
KiCad configuration rather than copying into the application installation.
Do not install two copies under different paths: that can leave duplicate menu
entries or make KiCad load an older version.

Open PCB Editor and look under **Tools → External Plugins → ViaStitcher**.
The dialog title displays the loaded plugin version. The local 0.4.0 testing package is marked “development” in the dialog; it is
not a published stable 0.4.0 release.

Uninstall a PCM installation using the manager. To remove a manual installation,
close KiCad and remove that plugin directory. Removing the plugin does not
remove vias or settings already saved in a board.
