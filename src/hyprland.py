from __future__ import annotations

import json
import os
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.runtime import Rect


@dataclass(frozen=True)
class MonitorInfo:
    name: str
    x: int
    y: int
    width: int
    height: int
    scale: float
    reserved: tuple[int, int, int, int]
    active_workspace_id: int = 0
    focused: bool = False

    @property
    def work_area(self) -> Rect:
        left, top, right, bottom = self.reserved
        return Rect(left, top, self.width - left - right, self.height - top - bottom)

    def to_local_rect(self, rect: Rect) -> Rect:
        return Rect(rect.x - self.x, rect.y - self.y, rect.width, rect.height)

    def to_global_rect(self, rect: Rect) -> Rect:
        return Rect(rect.x + self.x, rect.y + self.y, rect.width, rect.height)

    @property
    def rect(self) -> Rect:
        return Rect(self.x, self.y, self.width, self.height)

    @property
    def global_work_area(self) -> Rect:
        return self.to_global_rect(self.work_area)


@dataclass(frozen=True)
class WindowInfo:
    address: str
    class_name: str
    title: str
    x: int
    y: int
    width: int
    height: int
    workspace_id: int
    fullscreen: int
    floating: bool = False
    mapped: bool = True
    hidden: bool = False
    pinned: bool = False

    @property
    def rect(self) -> Rect:
        return Rect(self.x, self.y, self.width, self.height)


@dataclass(frozen=True)
class CursorPos:
    x: int
    y: int


def _hyprctl_json(*args: str) -> Any:
    try:
        return _hyprctl_socket_json(*args)
    except Exception:
        pass
    output = subprocess.check_output(["hyprctl", *args, "-j"], text=True)
    return json.loads(output)


def _hyprctl_socket_json(*args: str) -> Any:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if not runtime_dir or not signature:
        raise RuntimeError("missing Hyprland socket environment")
    socket_path = Path(runtime_dir) / "hypr" / signature / ".socket.sock"
    command = "j/" + " ".join(args)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(0.2)
        client.connect(str(socket_path))
        client.sendall(command.encode())
        client.shutdown(socket.SHUT_WR)
        chunks: list[bytes] = []
        while True:
            chunk = client.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    return json.loads(b"".join(chunks).decode())


def monitor_from_hyprctl(data: dict) -> MonitorInfo:
    reserved = data.get("reserved") or [0, 0, 0, 0]
    width, height = int(data["width"]), int(data["height"])
    if int(data.get("transform", 0)) % 2:
        width, height = height, width
    scale = float(data.get("scale", 1.0))
    return MonitorInfo(
        name=str(data["name"]),
        x=int(data.get("x", 0)),
        y=int(data.get("y", 0)),
        width=round(width / scale),
        height=round(height / scale),
        scale=scale,
        reserved=tuple(int(value) for value in reserved[:4]),  # type: ignore[arg-type]
        active_workspace_id=int((data.get("activeWorkspace") or {}).get("id", 0)),
        focused=bool(data.get("focused", False)),
    )


def window_from_hyprctl(data: dict) -> WindowInfo:
    at = data.get("at") or [0, 0]
    size = data.get("size") or [0, 0]
    workspace = data.get("workspace") or {}
    return WindowInfo(
        address=str(data.get("address", "")),
        class_name=str(data.get("class", "")),
        title=str(data.get("title", "")),
        x=int(at[0]),
        y=int(at[1]),
        width=int(size[0]),
        height=int(size[1]),
        workspace_id=int(workspace.get("id", 0)),
        fullscreen=int(data.get("fullscreen", 0)),
        floating=bool(data.get("floating", False)),
        mapped=bool(data.get("mapped", True)),
        hidden=bool(data.get("hidden", False)),
        pinned=bool(data.get("pinned", False)),
    )


def load_monitors() -> list[MonitorInfo]:
    return [
        monitor_from_hyprctl(item) for item in _hyprctl_json("monitors")
        if not item.get("disabled") and item.get("mirrorOf", "none") == "none"
    ]


def desktop_rect(monitors: list[MonitorInfo]) -> Rect:
    left = min(monitor.x for monitor in monitors)
    top = min(monitor.y for monitor in monitors)
    right = max(monitor.rect.right for monitor in monitors)
    bottom = max(monitor.rect.bottom for monitor in monitors)
    return Rect(left, top, right - left, bottom - top)


def select_monitor(name: str | None = None) -> MonitorInfo:
    monitors = load_monitors()
    if not monitors:
        raise RuntimeError("hyprctl returned no monitors")
    if name:
        for monitor in monitors:
            if monitor.name == name:
                return monitor
        raise RuntimeError(f"monitor not found: {name}")
    return next((monitor for monitor in monitors if monitor.focused), monitors[0])


def monitor_for_point(monitors: list[MonitorInfo], x: int, y: int) -> MonitorInfo:
    for monitor in monitors:
        if monitor.rect.contains(x, y):
            return monitor
    return min(monitors, key=lambda monitor: (
        max(monitor.rect.left - x, 0, x - monitor.rect.right) ** 2
        + max(monitor.rect.top - y, 0, y - monitor.rect.bottom) ** 2
    ))


def clamp_window_rect(rect: Rect, monitors: list[MonitorInfo]) -> Rect:
    monitor = monitor_for_point(monitors, rect.x + rect.width // 2, rect.y + rect.height // 2)
    area = monitor.global_work_area
    return Rect(
        max(area.left, min(rect.x, max(area.left, area.right - rect.width))),
        max(area.top, min(rect.y, max(area.top, area.bottom - rect.height))),
        rect.width, rect.height,
    )


def active_window() -> WindowInfo | None:
    data = _hyprctl_json("activewindow")
    if not data or not data.get("address"):
        return None
    return window_from_hyprctl(data)


def load_windows() -> list[WindowInfo]:
    return [window_from_hyprctl(item) for item in _hyprctl_json("clients")]


def floating_window_rects_for_monitor(monitor: MonitorInfo, windows: list[WindowInfo]) -> list[Rect]:
    monitor_rect = Rect(monitor.x, monitor.y, monitor.width, monitor.height)
    rects: list[Rect] = []
    for window in windows:
        if not window.floating or not window.mapped or window.hidden or window.fullscreen or window.width <= 0 or window.height <= 0:
            continue
        if monitor.active_workspace_id and window.workspace_id != monitor.active_workspace_id and not window.pinned:
            continue
        if monitor_rect.intersects(window.rect):
            rects.append(monitor.to_local_rect(window.rect))
    return rects


def active_window_rect_for_monitor(monitor: MonitorInfo, window: WindowInfo | None) -> Rect | None:
    if window is None or window.fullscreen:
        return None
    monitor_rect = Rect(monitor.x, monitor.y, monitor.width, monitor.height)
    if not monitor_rect.intersects(window.rect):
        return None
    return monitor.to_local_rect(window.rect)


def move_window_to_monitor_rect(monitor: MonitorInfo, window: WindowInfo, rect: Rect) -> None:
    move_window_to_rect(window, monitor.to_global_rect(rect))


def move_window_to_rect(window: WindowInfo, rect: Rect) -> None:
    _window_dispatch(f"hl.dsp.window.move({{ window = {json.dumps('address:' + window.address)}, x = {rect.x}, y = {rect.y} }})")


def set_window_floating(window: WindowInfo, floating: bool) -> None:
    action = "enable" if floating else "disable"
    _window_dispatch(f"hl.dsp.window.float({{ window = {json.dumps('address:' + window.address)}, action = {json.dumps(action)} }})")


def resize_window(window: WindowInfo, width: int, height: int) -> None:
    _window_dispatch(f"hl.dsp.window.resize({{ window = {json.dumps('address:' + window.address)}, x = {width}, y = {height} }})")


def window_animation_disabled(window: WindowInfo) -> str:
    return subprocess.check_output(["hyprctl", "getprop", "address:" + window.address, "no_anim"], text=True).strip()


def set_window_animation_disabled(window: WindowInfo, value: str) -> None:
    _window_dispatch(f"hl.dsp.window.set_prop({{ window = {json.dumps('address:' + window.address)}, prop = \"no_anim\", value = {json.dumps(value)} }})")


def window_move_animation_ms() -> int:
    animations = {item["name"]: item for item in _hyprctl_json("animations")[0]}
    for name in ("windowsMove", "windows", "global"):
        animation = animations[name]
        if animation["overridden"]:
            return round(animation["speed"] * 100) if animation["enabled"] else 0
    return 0


def _window_dispatch(command: str) -> None:
    result = subprocess.run(
        ["hyprctl", "dispatch", command],
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip() != "ok":
        raise RuntimeError(result.stdout.strip() or result.stderr.strip())


@dataclass(frozen=True)
class WindowPlacement:
    rect: Rect
    floating: bool
    workspace_id: int = 0
    pinned: bool = False


def minimized_cache_path(address: str) -> Path:
    return Path.home() / ".cache/hypr/minimized" / (address + ".json")


def minimize_window(window: WindowInfo, placement: WindowPlacement) -> None:
    path = minimized_cache_path(window.address)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Match the Win+M / Alt+M restore cache used by Hyprland's minimized.py.
    path.write_text(json.dumps({"address": window.address, "at": [placement.rect.x, placement.rect.y],
                               "size": [placement.rect.width, placement.rect.height], "floating": placement.floating,
                               "workspace": {"name": str(placement.workspace_id)}, "pinned": placement.pinned}), encoding="utf-8")
    path.chmod(0o600)
    selector = json.dumps("address:" + window.address)
    if window.pinned:
        _window_dispatch(f"hl.dsp.window.pin({{ window = {selector}, action = \"disable\" }})")
    _window_dispatch(f"hl.dsp.window.move({{ window = {selector}, workspace = \"special:minimized\", follow = false }})")
    if not placement.floating:
        set_window_floating(window, False)


def visible_windows(monitors: list[MonitorInfo], windows: list[WindowInfo]) -> list[WindowInfo]:
    return [window for window in windows if window.mapped and not window.hidden and not window.fullscreen
            and window.width > 0 and window.height > 0 and any(
                monitor.rect.intersects(window.rect)
                and (window.pinned or window.workspace_id == monitor.active_workspace_id)
                for monitor in monitors)]


class WindowMotion:
    def __init__(self, originals: dict[str, WindowPlacement] | None = None) -> None:
        self.target: WindowInfo | None = None
        self.last_rect: Rect | None = None
        self.originals = originals if originals is not None else {}
        self.animation_disabled: str | None = None

    def begin(self, window: WindowInfo) -> None:
        if self.target is None or self.target.address != window.address:
            self.release()
            self.target = window
            self.last_rect = None
        if self.animation_disabled is None:
            value = window_animation_disabled(window)
            # Layer-shell sprite movement is immediate; smoothing only the window separates their anchors.
            set_window_animation_disabled(window, "1")
            self.animation_disabled = value

    def release(self) -> None:
        if self.target is not None and self.animation_disabled is not None:
            if any(window.address == self.target.address for window in load_windows()):
                set_window_animation_disabled(self.target, self.animation_disabled)
        self.animation_disabled = None
        self.target = None
        self.last_rect = None

    def move(self, window: WindowInfo, rect: Rect, monitors: list[MonitorInfo]) -> Rect | None:
        if not window.floating or not window.mapped or window.hidden or window.fullscreen:
            return None
        rect = clamp_window_rect(rect, monitors)
        self.begin(window)
        if rect != self.last_rect:
            move_window_to_rect(window, rect)
            self.originals.setdefault(window.address, WindowPlacement(window.rect, window.floating, window.workspace_id, window.pinned))
            self.last_rect = rect
        return rect

    def restore(self, windows: list[WindowInfo], monitors: list[MonitorInfo]) -> None:
        by_address = {window.address: window for window in windows}
        for address, placement in list(self.originals.items()):
            window = by_address.get(address)
            if window is not None and window.mapped and not window.fullscreen:
                if window.workspace_id < 0 and placement.workspace_id:
                    _window_dispatch(f"hl.dsp.window.move({{ window = {json.dumps('address:' + address)}, workspace = {json.dumps(str(placement.workspace_id))}, follow = false }})")
                if window.floating or placement.floating:
                    if not window.floating:
                        set_window_floating(window, True)
                    if placement.floating and (window.width, window.height) != (placement.rect.width, placement.rect.height):
                        resize_window(window, placement.rect.width, placement.rect.height)
                    move_window_to_rect(window, clamp_window_rect(placement.rect, monitors))
                if window.floating and not placement.floating:
                    set_window_floating(window, False)
                if placement.pinned and not window.pinned:
                    _window_dispatch(f"hl.dsp.window.pin({{ window = {json.dumps('address:' + address)}, action = \"enable\" }})")
            minimized_cache_path(address).unlink(missing_ok=True)
            del self.originals[address]
        self.release()


@dataclass
class ActiveWindowMoveGuard:
    window_address: str | None = None
    rect: Rect | None = None

    def reset(self) -> None:
        self.window_address = None
        self.rect = None

    def move_if_changed(self, monitor: MonitorInfo, window: WindowInfo, rect: Rect) -> bool:
        if self.window_address != window.address:
            self.window_address = window.address
            self.rect = None
        if self.rect == rect:
            return False
        move_window_to_monitor_rect(monitor, window, rect)
        self.window_address = window.address
        self.rect = rect
        return True


def cursor_pos_for_monitor(monitor: MonitorInfo, cursor: CursorPos) -> CursorPos:
    return CursorPos(x=cursor.x - monitor.x, y=cursor.y - monitor.y)


def cursor_pos() -> CursorPos:
    data = _hyprctl_json("cursorpos")
    return CursorPos(x=int(data["x"]), y=int(data["y"]))
