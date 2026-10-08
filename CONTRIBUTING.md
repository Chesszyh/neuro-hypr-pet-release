# Contributing

Setup and usage are in [README.md](README.md) and [README.zh-CN.md](README.zh-CN.md).

## Bug reports

Open an issue with the reproduction steps, expected result, and actual result.
Include the pet's image-set name, the launch command, `hyprctl version`, and
relevant service errors from `journalctl --user -u neuro-hypr-pet-shimeji.service`.
For movement or multi-monitor problems, include output names, logical positions,
scale factors, and a screenshot or short recording of the affected pet/window.

## Changes and validation

Use the system Python and install the dependencies listed in the README.
From the repository root, run:

```bash
python3 -m unittest discover -s tests -v
```

The automatic suite can run without a Wayland session once the GTK bindings,
gtk4-layer-shell typelib, and Pillow are installed. Tests use temporary
preferences rather than the user's saved pet selection. Extended-collection tests
are explicitly skipped without the optional assets; importer and split-setting
tests run using synthetic fixtures.

For animation, pointer input, output switching, or window movement changes,
also run a desktop trial in Hyprland. Use dedicated test windows for carrying,
throwing, and minimization. XML behavior changes should exercise the real image
set as well as any small synthetic fixture. Record which desktop interactions
were checked in the pull request.

For a separate test desktop, run nested Hyprland with a small configuration and
its own D-Bus session, for example:

```bash
dbus-run-session -- Hyprland --config /absolute/path/to/test/hyprland.lua
```

Launch the pets and dedicated test windows from a terminal inside that desktop,
so they inherit its Wayland display and Hyprland instance. The separate D-Bus
session also gives the test its own GTK application instance. Set
`XDG_CONFIG_HOME` to a temporary test directory when launching the pets to keep
test choices separate. Tray tests need a StatusNotifier host, such as Waybar
with its `tray` module, inside the test desktop.

In a nested Wayland session, `hyprctl output create wayland test` adds another
output window, and `hyprctl output remove test` removes it. This exercises
output layout and switching; physical monitor hotplug still needs a real
desktop trial. See Hyprland's [output commands](https://github.com/hyprwm/hyprland-wiki/blob/main/content/configuring/core/advanced-configuration/using-hyprctl.md).
Containers are useful for dependencies and automatic tests. A virtual machine
is useful for checking installation and user-service startup on a fresh system.

Keep each change focused and explain its resulting behavior and validation.
Comments should explain non-obvious constraints. Keep the English and Chinese
README aligned when changing setup or user-visible behavior, and update the
relevant tests.

## Continuous integration

[Tests](.github/workflows/tests.yml) runs on pushes to `main`, pull requests,
and manual dispatch. It installs the system GTK and Python dependencies in
Fedora and runs the test suite without artwork. Optional extended-collection
tests are skipped; desktop interaction still needs a Hyprland trial.

## Licenses and third-party material

Contributions to the project's Python code, tests, and documentation use the
[MIT License](LICENSE). Imported collections retain their original terms;
their sources and license scope are recorded in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Include the source, author,
and applicable permission when contributing third-party material.
