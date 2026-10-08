# neuro-hypr-pet

面向 Hyprland / Wayland 的 **The Neuroling Collection** 原生桌宠运行时。
使用 Python、GTK4 和 gtk4-layer-shell（Wayland 桌面层窗口库），直接读取素材的
Shimeji `actions.xml` / `behaviors.xml`。每只桌宠使用一个与图片大小匹配的窗口，
鼠标输入区域跟随图片的不透明像素。

[English](README.md) · [贡献指南](CONTRIBUTING.md)

## 依赖

- Hyprland Wayland 会话，能够调用 `hyprctl`。
- Python 3、PyGObject（`gi`）、Pycairo（`cairo`）、GTK4，以及
  `Gtk4LayerShell` 的 GObject introspection（对象类型信息）库。
- 声音播放需要 `paplay`、`pw-play`、`aplay` 中任意一个。
- 旧素材导出工具和完整测试还需要 Pillow。
- 托盘入口需要 Waybar 的 `tray` 模块或其他支持 StatusNotifierItem（桌面托盘协议）的托盘。

Fedora 上可安装：

```bash
sudo dnf install git python3-gobject python3-cairo gtk4 gtk4-layer-shell \
  python3-pillow pulseaudio-utils
```

使用系统 Python，以便找到发行版提供的 GTK 绑定。原生运行时不需要 Java 或
Windows 可执行文件。显示器使用缩放和旋转后的逻辑尺寸；混合 1 / 1.2 倍缩放的
双屏已实机验证，旋转坐标转换有自动测试。

## 启动

克隆运行代码：

```bash
git clone https://github.com/Chesszyh/neuro-hypr-pet-release.git
cd neuro-hypr-pet-release
```

从[原发布页面](https://neurofumo.itch.io/neurolings)下载 **Neurolings v1.zip**，然后导入：

```bash
python3 tools/import_neurolings.py "$HOME/Downloads/Neurolings v1.zip"
```

导入器将 `Neuroling` 和 `Evil Neuroling` 安装到
`${XDG_DATA_HOME:-$HOME/.local/share}/neuro-hypr-pet/collection`，为两个角色适配
共用 XML，并保留包内许可与说明。仓库不提供图片，导入时不复制 Java 程序和日志。
可用 `--destination /path/to/new/collection` 指定新目录，启动时通过 `--collection`
使用该路径；已有目录不会被覆盖。

查看显示器名称：

```bash
hyprctl monitors
```

默认在当前聚焦屏幕启动保存的待召唤素材，首次使用优先选择 Neuroling。选择为空时只启动托盘。
指定 `--monitor all`
可在每个已连接屏幕启动所选素材；重复 `--image-set` 可选择多种素材：

```bash
python3 tools/neuro_hypr_shimeji.py --image-set Neuroling
python3 tools/neuro_hypr_shimeji.py --image-set Neuroling --monitor all
python3 tools/neuro_hypr_shimeji.py --image-set Neuroling --image-set "Evil Neuroling"
```

也可用 `--monitor eDP-1` 或其他输出名称指定初始屏幕。

默认使用已导入的素材。使用其他素材目录时传入
`--collection /absolute/path/to/collection`；通过 `--image-set` 选择其
`img/<name>` 目录，名称含空格时加引号。

具体动作取决于导入的素材。Tutel、Vedal 和扩展版 Neuron / Eviling 动作需要另外的素材包。

轻点热点可触发抚摸动作；按住并移动可拖拽，松手可抛出。右键菜单可以选择动作、
召唤 Evil 或 Tutel、换屏、开启窗口搬运、还原搬动的窗口或移除当前桌宠。
Tutel 变身为 Vedal 后仍视为同一位伙伴。

点击托盘图标展开鼠标附近的小浮窗；它使用 Wayland 桌面层，不占用平铺窗口。
浮窗支持全选、全不选、多选素材并召唤、再召唤同款、全部跟随鼠标、只留一只、暂停/继续和移除全部。
“全部跟随鼠标”让普通桌宠沿屏幕底部或窗口顶边追随鼠标的横向位置，靠近后停下；再次点击恢复自主活动。
拖拽和手动窗口互动优先执行，完成后继续跟随。
“召唤所选”会恢复运行并取消成功项的勾选，避免下一次重复召唤；未成功的素材保留勾选。
素材勾选自动保存到 `~/.config/neuro-hypr-pet/preferences.json`，也遵循
`XDG_CONFIG_HOME`。关闭按钮或 Esc 收起浮窗。

“允许分裂成两只”控制所有桌宠自动和手动分裂（`SplitIntoTwo` / `Glitch`），默认开启并自动保存。
关闭后停止产生分裂桌宠，也会拦截尚未处理的分裂事件；现有桌宠和其他召唤操作不受影响。

移除最后一只后程序和托盘仍然保留，可随时重新召唤。“退出程序”才会结束程序。
桌宠右键菜单的“管理桌宠”和下面的命令也可打开浮窗；再次运行入口会唤出已运行实例：

```bash
python3 tools/neuro_hypr_shimeji.py --manage
```

“窗口互动”页可选择执行桌宠和当前可见的目标窗口，主动搬运、抛出或随机抛出。
平铺窗口会临时转为悬浮；过大的窗口会缩小，为搬运留出空间。
“还原搬动的窗口”恢复悬浮窗口的位置和尺寸，并让原本平铺的窗口重新参与平铺布局。
Tutel 通过临时 Cursor 执行这类动作，完成后 Cursor 自动消失。
搬运和抛出速度可在此页调整并自动保存，默认 1.5 倍，范围为 0.5～3 倍。
同屏桌宠从当前位置跳向目标；携窗时窗口位置与桌宠绘制同步，结束后恢复窗口原有动画设置。

“抛出并最小化”在抛出后让窗口缩小并滑向屏幕底部，再收进 `special:minimized`。
可用“还原搬动的窗口”取回。恢复信息保存在 `~/.cache/hypr/minimized/`，包含原来的
位置、尺寸、工作区、平铺和置顶状态。Alt+M 或 Waybar 恢复入口需要另行配置兼容该缓存
格式的 `minimized.py` 脚本；本项目不安装该脚本、快捷键或 Waybar 模块。

查看启动设置或短时间试运行：

```bash
python3 tools/neuro_hypr_shimeji.py --dry-run
python3 tools/neuro_hypr_shimeji.py --image-set Neuroling --monitor auto --duration 5
```

`--dry-run` 只打印模式设置，不检查素材、显示器或 Wayland 连接。
[原生入口](tools/neuro_hypr_shimeji.py) 的 `--help` 列出全部选项。
启动参数和试运行时长在没有已有实例时生效。程序已运行时，再次执行只打开管理浮窗；
可在浮窗召唤桌宠，或先退出已有实例再试运行。

## 功能与兼容范围

- 走路、跑步、跳跃、下落、边缘攀爬和落地动画。
- 热点点击、拖拽、平滑抛出和半透明右键菜单。
- 在当前工作区可见的浮动窗口上降落或攀爬，无需窗口保持聚焦；也考虑当前聚焦窗口。
- 嵌套 `Sequence` / `Select`、条件动画、左右朝向图片、鼠标表达式和按权重选择行为。
- 同一应用中的伙伴互动、繁殖、变身、自毁和动画声音。
- 多屏启动、菜单换屏和相邻屏幕间抛出；显示器拔除后回到剩余屏幕。
- 托盘小浮窗、记住素材选择、多素材启动、同款召唤、全体跟随、暂停和批量管理。
- 主动搬运、抛出指定窗口或随机抛出，支持未聚焦及平铺目标、速度调整和抛出后最小化。
- 自动动作搬动悬浮窗口的能力由菜单或 `--move-active-window` 开启，默认关闭。
- 搬动时绑定同一个窗口，可还原该应用搬动的窗口位置、尺寸及平铺状态。
- 静止图片不重复提交绘制。

本项目是 Shimeji 兼容运行时，仍有行为差异。原版的全局及单素材设置、大小、透明度、
滤镜和主题设置尚未实现。

跨屏拖拽在松手时切换显示输出，按住期间图片仍裁剪在原屏幕内；相邻屏幕之间的
抛出会在飞行中切屏。窗口搬运使用 Hyprland 的 Lua 窗口调度接口，已在 0.56.2
验证；全屏窗口不参与搬运，抛出的窗口保留在可见工作区域内。

## 用户级服务

指定素材和显示器后安装并启动：

```bash
python3 tools/neuro_hypr_shimeji.py \
  --image-set Neuroling --monitor auto --install-user --start
```

安装器写入 `~/.config/systemd/user/neuro-hypr-pet-shimeji.service`，以及应用菜单中的
“Neuroling”入口，后者打开同一个托盘浮窗。服务启动时读取保存的待召唤选择；
安装时传入 `--image-set` 会更新该选择。召唤成功后选择清空，因此后续服务启动通常
只显示托盘，需要再次召唤。重新运行安装器可更新显示器、帧率等启动参数。
服务生成规则由
[service.py](src/service.py) 的 `render_shimeji_user_service()` 定义。

```bash
systemctl --user status neuro-hypr-pet-shimeji.service
systemctl --user stop neuro-hypr-pet-shimeji.service
journalctl --user -u neuro-hypr-pet-shimeji.service -n 50
```

服务随图形会话启动，需要用户服务管理器的环境中存在 `WAYLAND_DISPLAY`。
若因缺少环境变量而跳过启动，可导入当前 Hyprland 会话变量后重启：

```bash
systemctl --user import-environment WAYLAND_DISPLAY HYPRLAND_INSTANCE_SIGNATURE
systemctl --user restart neuro-hypr-pet-shimeji.service
```

卸载用户服务和应用菜单入口：

```bash
systemctl --user disable --now neuro-hypr-pet-shimeji.service
rm -f ~/.config/systemd/user/neuro-hypr-pet-shimeji.service
rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/applications/neuro-hypr-pet.desktop"
systemctl --user daemon-reload
```

仓库目录及 `${XDG_CONFIG_HOME:-$HOME/.config}/neuro-hypr-pet/preferences.json`
中的选择可保留供以后安装使用。

## 诊断和测试

```bash
python3 tools/neuro_hypr_diagnose.py --image-set Neuroling
python3 -m unittest discover -s tests -v
```

诊断输出包含显示器与工作区几何、鼠标位置、活动窗口目标和 XML 目录概要。
原生运行时的 `--debug-state` 可输出运动日志。测试覆盖模型、运行时、服务、入口、
Hyprland、声音和导出工具；真实桌面交互需要另外试运行。
依赖 `refs/The-Neuroling-Collection` 扩展素材的测试在素材缺失时明确跳过；
导入和分裂开关测试使用独立构造的数据，无需图片。

## 旧工具

[neuroling_wpets.py](tools/neuroling_wpets.py) 可为 `wayland-vpets` 导出图片表，
需要 Pillow 和另外安装的 `wayland-vpets`。该模式的透明覆盖层不接收鼠标输入，
不支持点击或拖拽，与原生服务分开。导出及安装参数见该工具的 `--help`。
需显式指定另行编译的运行程序：

```bash
python3 tools/neuroling_wpets.py \
  --binary /absolute/path/to/wayland-vpets/build/bongocat-all --image-set Neuroling
```

原生入口还保留了实验性全屏模式，通过 `--screen-cover --allow-screen-cover`
显式启用；它不是常规启动路径，也不会写入生成的服务。

## 署名与许可证

Wayland 适配代码采用 [MIT 许可证](LICENSE)。Shimeji-ee 和原始 Shimeji 的适用声明
原样保留在 [LICENSES](LICENSES) 中。素材单独导入，来源和作者见
[第三方声明](THIRD_PARTY_NOTICES.md)。
