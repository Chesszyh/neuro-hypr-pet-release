# macOS native application and capability probe

Build and run the native pet application from the repository root:

```bash
.venv-macos/bin/python packaging/macos/setup.py --pet-app py2app
"dist/Neuro Pet.app/Contents/MacOS/Neuro Pet" --collection /path/to/collection
```

Create the environment and install the locked dependencies below before building.
The application can also run as `python tools/neuro_macos_shimeji.py` with the same
options. `--image-set Neuron` chooses an initial pet; repeat the option for more
materials. Without imported materials, the manager offers ZIP import. Default
materials and preferences use Application Support. `--preferences /tmp/test/preferences.json`
is useful for isolated trials. A repeated invocation with the same preference
path opens the existing manager through a local socket. The menu bar remains
available after removing all pets. The context menu's actions and split controls
apply to the selected pet. New-pet defaults and batch updates are separate.

The manager's **下落速度** control applies to falling, including the flight after
releasing a pet. The setting is saved in preferences and applies to existing pets.
`--fps` controls display refresh independently of the fixed physics clock. Sprite
positions are interpolated between physics updates; increasing display refresh
does not accelerate actions. Visible window bounds are sampled at display refresh
so removing a supporting window does not wait for Accessibility enumeration.

With Stage Manager enabled, **抛出并最小化** uses the system's left shelf;
with it disabled, the system uses the Dock. Completion checks account for both
presentations. **还原搬动的窗口** also brings a shelved window back.

PNG dimensions are logical points regardless of the PNG's DPI metadata; XML
anchors, pointer coordinates and physics use that same scale. Retina backing
resolution is handled by AppKit. Neuron tests therefore preserve each source
frame's canvas dimensions rather than resizing every pose to a common rectangle.

For short, isolated desktop trials with real assets:

```bash
.venv-macos/bin/python tools/neuro_macos_smoke.py \
  --collection /path/to/collection --image-set Neuron --count 5 \
  --duration 10 --report /tmp/neuro-trial.json
```

The capability probe below tests transparent input and Accessibility using a
synthetic PNG and two dedicated blank windows.

From the repository root, using Python 3.13 on macOS:

```bash
python3 -m venv .venv-macos
.venv-macos/bin/python -m pip install -r packaging/macos/requirements.lock
.venv-macos/bin/python tools/run_core_tests.py
.venv-macos/bin/python tools/neuro_macos_diagnose.py
```

The test runner and diagnostic do not create windows. The diagnostic reads
Accessibility authorization without requesting access. Shared engine tests also
run on Linux; macOS framework tests require the native dependencies above.

Build both standalone applications:

```bash
.venv-macos/bin/python packaging/macos/setup.py --target-app py2app
.venv-macos/bin/python packaging/macos/setup.py py2app
```

The two applications must remain beside each other in `dist/`. The probe launches
its own target application and retains the actual AX window elements. It never
chooses another application's windows. `setup.py` includes Conda's `libffi` when
present, alongside py2app's bundled interpreter and dependencies. Dependency
license texts collected from wheel distributions are in `licenses/`; release
licensing and signing remain part of the final application packaging work.

For an interactive desktop test, run the following when the temporary test
windows will not interrupt other work:

```bash
"dist/Neuro macOS Probe.app/Contents/MacOS/Neuro macOS Probe" \
  --duration 60 --exercise-ax --report /tmp/neuro-macos-probe.json
```

The command displays a transparent panel above two same-title windows. It moves
and resizes only those windows, requests minimization, then restores the saved
geometry. Requests, readback geometry, AX errors, click recipients, and frame
intervals are recorded in JSON. Minimization completion is checked separately
from request acceptance. The frame timer uses common run-loop modes. SIGINT and
SIGTERM stop the timer and clean up the target process.

For input testing without window movement, omit `--exercise-ax`. Click the blue
circle, transparent corners, and translucent red strip; drag the circle. Confirm
from both processes' events which window received each click and whether the
sprite became key. Test fast entry, drag release, overlapping pets, and changing
frames separately before accepting the production input design. The prototype
uses native alpha hit handling without a polling-based `ignoresMouseEvents`
switch. A successful draw or an in-window `hitTest` is not evidence of
cross-process click-through.

Physical multi-display, Spaces, sleep/wake, and fresh-system application startup
require desktop testing. The prototype is not the finished pet application.
