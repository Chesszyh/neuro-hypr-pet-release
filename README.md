# neuro-hypr-pet

A native Hyprland/Wayland runtime for the desktop pets in **The Neuroling
Collection**. It reads Shimeji `actions.xml` and `behaviors.xml` directly,
using Python, GTK4, and gtk4-layer-shell. Each pet occupies a sprite-sized
window whose mouse input region follows the visible pixels.

[简体中文](README.zh-CN.md) · [Contributing](CONTRIBUTING.md)

## Requirements

- A Hyprland Wayland session with `hyprctl` available.
- Python 3 with PyGObject (`gi`), Pycairo (`cairo`), GTK4, and the
  `Gtk4LayerShell` GObject introspection typelib.
- For sound effects, one of `paplay`, `pw-play`, or `aplay`.
- Pillow for the legacy sprite exporter and the full test suite.
- Waybar's `tray` module or another StatusNotifierItem host for the tray entry.

On Fedora:

```bash
sudo dnf install git python3-gobject python3-cairo gtk4 gtk4-layer-shell \
  python3-pillow pulseaudio-utils
```

Use the system Python so it can find the distribution's GTK bindings. Java
and the Windows executable are not needed. Display geometry uses logical dimensions
after scale and rotation. Mixed 1 / 1.2 scale outputs have been tested on a real
dual-monitor session; rotation conversion is covered by automated tests.

## Run

Clone the runtime:

```bash
git clone https://github.com/Chesszyh/neuro-hypr-pet-release.git
cd neuro-hypr-pet-release
```

Download **Neurolings v1.zip** from the
[original release page](https://neurofumo.itch.io/neurolings), then import it:

```bash
python3 tools/import_neurolings.py "$HOME/Downloads/Neurolings v1.zip"
```

The importer installs the two image sets, `Neuroling` and `Evil Neuroling`,
into `${XDG_DATA_HOME:-$HOME/.local/share}/neuro-hypr-pet/collection`.
It adapts the archive's shared XML for each image set and preserves its notices.
The repository contains no artwork. Java executables and logs are not imported.
Use `--destination /path/to/new/collection` to import elsewhere, then pass that
path with `--collection` when launching. Existing destinations are kept intact.

Find your monitor name:

```bash
hyprctl monitors
```

The default starts the saved pending image sets on the focused output, initially
Neuroling when available. An empty selection starts the tray without pets. Use `--monitor all` to start the selected sets on each connected output.
Repeat `--image-set` to choose multiple sets:

```bash
python3 tools/neuro_hypr_shimeji.py --image-set Neuroling
python3 tools/neuro_hypr_shimeji.py --image-set Neuroling --monitor all
python3 tools/neuro_hypr_shimeji.py --image-set Neuroling --image-set "Evil Neuroling"
```

Use `--monitor eDP-1` or another output name to choose the initial monitor.

The runtime uses the imported collection by default. For another collection,
pass `--collection /absolute/path/to/collection`. Choose its `img/<name>`
directory with `--image-set`, quoting names that contain spaces.

Available animations and interactions depend on the imported image set. Tutel,
Vedal, and the extended Neuron/Eviling actions require a separate collection.

Tap a hotspot for its petting action. Hold and move to drag, then release to
throw. Right-click to choose a behavior, summon Evil or Tutel, change outputs,
enable window movement, restore moved windows, or remove that pet. Tutel and
Vedal count as the same companion after transformation.

Click the tray icon for a small popup near the cursor. It uses a Wayland desktop
layer and does not occupy the tiling layout. Select and summon multiple image
sets, summon another of the same pet, make all pets follow the cursor, keep one,
pause/resume, or remove all. Select all or clear all with one click. Summoning
selected sets resumes the pets and clears successful choices; unfinished choices
remain checked. Image-set choices are saved automatically to
`~/.config/neuro-hypr-pet/preferences.json`, respecting `XDG_CONFIG_HOME`.
Close the popup with its close button or Esc.

Right-click a pet to change that pet's split permission and automatic split
probability. The tray's **桌宠** (Pets) tab edits the same per-pet settings,
including separate settings for multiple pets of the same image set.
**应用到当前全部** (Apply to all current pets) changes the current pets once;
individual edits afterward remain independent. **新召唤默认值** (New summon
defaults) is saved for future summons and does not change existing pets.
Per-pet overrides last for that pet's lifetime; split children inherit their
parent's settings, while fresh summons use the saved defaults.

**使用素材概率** (Use asset probability) preserves the XML behavior weights.
Turn it off to set a 0–100% chance of splitting at each autonomous action choice,
when the XML conditions permit splitting. At 0%, manual splitting is still
available; disabling **允许分裂** (Allow splitting) blocks both automatic and
manual splits, including pending split births. Manual splitting is unaffected
by the percentage. Other summon actions are unaffected.

Cursor following makes regular pets follow the cursor's horizontal position
along the screen floor or a window's top edge, then stop nearby. Toggle it off
to resume autonomous behavior. Dragging and manual window interactions take
priority; following resumes afterward.

Removing the last pet keeps the process and tray available for another summon.
Use **Quit** to end the process. The pet menu's manager entry and this command
also open the popup; launching again activates the existing instance:

```bash
python3 tools/neuro_hypr_shimeji.py --manage
```

The window interaction page lets you choose a pet and a visible window to carry
or throw, or throw a random window. Tiled targets temporarily become floating;
large targets shrink to leave room for carrying. Restore returns floating
windows to their original position and size and returns originally tiled windows
to the tiling layout. Tutel delegates these actions to a transient Cursor that
disappears when finished.
Adjust carry/throw speed on this page: the default is 1.5×, with a saved range
of 0.5×–3×. Pets on the same output jump from their current position. Carried
windows move with the sprite frame, then regain their original animation setting.

**Throw and minimize** shrinks the thrown window toward the bottom of the screen,
then stores it in `special:minimized`. Restore it through the manager. The restore
cache at `~/.cache/hypr/minimized/` saves its original geometry, workspace, tiling
and pinned state. Alt+M and Waybar restoration require a separately configured
`minimized.py` script that understands this cache format; this project does not
install that script, keyboard bindings, or a Waybar module.

Check startup settings or run a short trial:

```bash
python3 tools/neuro_hypr_shimeji.py --dry-run
python3 tools/neuro_hypr_shimeji.py --image-set Neuroling --monitor auto --duration 5
```

`--dry-run` prints mode settings; it does not check assets, the monitor, or the
Wayland connection. All options are listed by `--help` in
[the native entry point](tools/neuro_hypr_shimeji.py).
Startup options and the trial duration apply when no instance is running.
If the application is already running, another invocation opens its manager;
use that popup to summon pets or quit before starting a trial.

## Features and compatibility

- Walking, running, jumping, falling, edge climbing, and landing animations.
- Hotspot clicks, dragging, smoothed throws, and a translucent pet menu.
- Landing on and climbing visible floating windows in the current workspace,
  including unfocused windows; the focused window is also considered.
- Nested `Sequence` / `Select` actions, conditional animations, directional
  images, cursor expressions, and weighted behavior selection.
- Companion interactions, breeding, transformations, self-destruction, and
  pose sound effects in the same application.
- Multiple outputs, menu transfers, and throws across adjacent outputs, with
  recovery to a remaining output when a display is removed.
- A tray popup, remembered image-set selection, multiple sets at startup,
  same-pet summons, group cursor following, pause, and batch controls.
- Explicit carry/throw actions for selected windows or a random throw, including
  unfocused and tiled targets, adjustable speed, and throw-to-minimize.
- Autonomous movement of floating windows, enabled through the pet menu or
  `--move-active-window` and disabled by default.
- Stable window targets and restoration of position, size, and tiling state.
- Static sprites avoid redundant drawing submissions.

This is a Shimeji-compatible runtime with remaining behavior differences.
Global and per-image-set settings, resizing, opacity, filters, and themes
remain unimplemented.

Cross-output dragging switches outputs on release; while held, the sprite is
clipped to the original output. Throws between adjacent outputs switch during
flight. Window movement uses Hyprland's Lua dispatch interface, verified on
0.56.2. Fullscreen windows do not participate in carrying, and thrown
windows remain within a visible work area.

## User service

Install and start with the monitor and image set you want:

```bash
python3 tools/neuro_hypr_shimeji.py \
  --image-set Neuroling --monitor auto --install-user --start
```

The installer writes `~/.config/systemd/user/neuro-hypr-pet-shimeji.service` and
a **Neuroling** application-menu entry that opens the same tray popup. The service
reads the saved pending image-set selection at startup; passing `--image-set` during
installation updates that selection. Successful summons clear it, so subsequent
service starts show only the tray until you summon pets again. Run the installer
again to update the monitor, frame rate, and other launch arguments. Service generation is defined by
`render_shimeji_user_service()` in [service.py](src/service.py).

```bash
systemctl --user status neuro-hypr-pet-shimeji.service
systemctl --user stop neuro-hypr-pet-shimeji.service
journalctl --user -u neuro-hypr-pet-shimeji.service -n 50
```

The service starts with the graphical session and requires `WAYLAND_DISPLAY`
in the user service manager's environment. If it is skipped for a missing
environment, import the current Hyprland session variables and restart:

```bash
systemctl --user import-environment WAYLAND_DISPLAY HYPRLAND_INSTANCE_SIGNATURE
systemctl --user restart neuro-hypr-pet-shimeji.service
```

To uninstall the service and application-menu entry:

```bash
systemctl --user disable --now neuro-hypr-pet-shimeji.service
rm -f ~/.config/systemd/user/neuro-hypr-pet-shimeji.service
rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/applications/neuro-hypr-pet.desktop"
systemctl --user daemon-reload
```

The checkout and saved choices in
`${XDG_CONFIG_HOME:-$HOME/.config}/neuro-hypr-pet/preferences.json` can be kept
for a later install.

## Diagnostics and tests

```bash
python3 tools/neuro_hypr_diagnose.py --image-set Neuroling
python3 -m unittest discover -s tests -v
```

Diagnostics show monitor/work-area geometry, cursor position, the active
window target, and an XML catalog summary. Use `--debug-state` on the native
runtime for motion logging. Tests cover model, runtime, service, entry-point,
Hyprland, sound, and exporter behavior; desktop interaction needs a separate trial.
Tests requiring the optional extended collection under
`refs/The-Neuroling-Collection` are skipped when it is absent. Import and split
setting tests use synthetic fixtures and run without artwork.

## Legacy tools

[neuroling_wpets.py](tools/neuroling_wpets.py) exports sprite sheets for
`wayland-vpets`. It requires Pillow and a separately installed `wayland-vpets`;
its pass-through overlay does not support clicks or dragging. It is separate
from the native service. See its `--help` for export and installation options.
Pass the separately built runtime explicitly:

```bash
python3 tools/neuroling_wpets.py \
  --binary /absolute/path/to/wayland-vpets/build/bongocat-all --image-set Neuroling
```

The native entry point retains an experimental full-screen mode behind
`--screen-cover --allow-screen-cover`. It is not the normal launch path or
part of service generation.

## Credits and licences

The Wayland adaptation uses the [MIT License](LICENSE). Shimeji-ee and original
Shimeji notices are retained in [LICENSES](LICENSES). Artwork remains separate;
see [third-party notices](THIRD_PARTY_NOTICES.md) for sources and credits.
