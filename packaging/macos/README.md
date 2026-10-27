# macOS installation and development

## 安装应用 / Install the app

从 [Releases](https://github.com/Chesszyh/neuro-hypr-pet-release/releases) 下载与 Mac
架构匹配的 Neuro Pet `.dmg`。打开磁盘映像，将 **Neuro Pet.app** 拖入 **Applications**，
再从“应用程序”打开。应用内含 Python 与依赖，不需要安装开发环境。
硬件架构与最低系统版本以对应 Release 说明为准。

Download the Neuro Pet `.dmg` for your Mac from
[Releases](https://github.com/Chesszyh/neuro-hypr-pet-release/releases), open it, and
drag **Neuro Pet.app** into **Applications**. Launch it from Applications; Python
and dependencies are bundled. See the release notes for supported hardware and macOS.

未经过 Apple 公证的版本首次打开可能被系统拦截。尝试打开一次后，在“系统设置 → 隐私与安全性”中
找到 Neuro Pet，选择“仍要打开”。参见 [Apple 的打开应用说明](https://support.apple.com/102445)。
For builds without Apple notarization, attempt to open the app, then use
**System Settings → Privacy & Security → Open Anyway** for Neuro Pet.

从 [Neurolings 素材页](https://neurofumo.itch.io/neurolings)下载 **Neurolings v1.zip**，
在管理面板中导入 ZIP，再选择角色召唤。素材不包含在应用内。关闭管理窗口后仍可通过菜单栏图标打开。
窗口读取和搬运需要在“隐私与安全性 → 辅助功能”中允许 Neuro Pet；基础桌宠使用不需要开启窗口搬运。

Download **Neurolings v1.zip** from the artwork page, import it in the manager, and
summon a character. Artwork is separate from the application. Use the menu-bar
icon to reopen the manager. Window detection and movement require Accessibility
permission for Neuro Pet in Privacy & Security.

更新时退出 Neuro Pet，再用新版替换“应用程序”中的旧版。素材和设置保留在
`~/Library/Application Support/neuro-hypr-pet/`。卸载时退出并移除应用即可；
如已开启“登录时自动启动”，先在管理面板关闭。
To update, quit the app and replace it in Applications. Artwork and preferences
remain in the Application Support directory. To uninstall, disable login startup
if enabled, quit, and remove the app.

## Build from source

```bash
python3.13 -m venv .venv-macos
.venv-macos/bin/python -m pip install -r packaging/macos/requirements.lock
```

Build and run the native pet application from the repository root:

```bash
packaging/macos/build.sh
"dist/Neuro Pet.app/Contents/MacOS/Neuro Pet" --collection /path/to/collection
```

Create the environment and install the locked dependencies above before building.
`build.sh` creates the application and a DMG in `dist/`. It uses `local-codesign`
when installed, or an ad-hoc signature otherwise. This does not perform Apple notarization.
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
python3.13 -m venv .venv-macos
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
