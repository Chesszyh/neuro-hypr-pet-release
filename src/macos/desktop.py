from __future__ import annotations

import os
from dataclasses import replace

import AppKit as AK
import Quartz as Q

from src.desktop import CursorPos, MonitorInfo, WindowInfo, monitor_for_point
from src.macos.coordinates import Coordinates


def coordinates() -> Coordinates:
    primary = AK.NSScreen.screens()[0].frame()
    return Coordinates(primary.origin.y + primary.size.height)


def load_monitors() -> list[MonitorInfo]:
    converter = coordinates()
    pointer = AK.NSEvent.mouseLocation()
    result = []
    for screen in AK.NSScreen.screens():
        frame, visible = screen.frame(), screen.visibleFrame()
        rect = converter.rect_from_appkit(frame.origin.x, frame.origin.y, frame.size.width, frame.size.height)
        work = converter.rect_from_appkit(visible.origin.x, visible.origin.y, visible.size.width, visible.size.height)
        cursor_x, cursor_y = converter.point_from_appkit(pointer.x, pointer.y)
        result.append(MonitorInfo(
            str(screen.deviceDescription()['NSScreenNumber']), rect.x, rect.y, rect.width, rect.height,
            screen.backingScaleFactor(),
            (work.left - rect.left, work.top - rect.top, rect.right - work.right, rect.bottom - work.bottom),
            focused=rect.contains(round(cursor_x), round(cursor_y)),
        ))
    return result


def select_monitor(name: str | None = None) -> MonitorInfo:
    monitors = load_monitors()
    if name:
        return next(monitor for monitor in monitors if monitor.name == name)
    return next((monitor for monitor in monitors if monitor.focused), monitors[0])


def cursor_pos() -> CursorPos:
    point = AK.NSEvent.mouseLocation()
    x, y = coordinates().point_from_appkit(point.x, point.y)
    return CursorPos(round(x), round(y))


def load_windows() -> list[WindowInfo]:
    windows = Q.CGWindowListCopyWindowInfo(Q.kCGWindowListOptionOnScreenOnly | Q.kCGWindowListExcludeDesktopElements, Q.kCGNullWindowID) or []
    result = []
    for window in windows:
        bounds = window.get(Q.kCGWindowBounds, {})
        if window.get(Q.kCGWindowLayer) != 0 or window.get(Q.kCGWindowOwnerPID) == os.getpid():
            continue
        if bounds.get('Width', 0) < 100 or bounds.get('Height', 0) < 60:
            continue
        result.append(WindowInfo(
            f"cg:{window[Q.kCGWindowNumber]}", str(window.get(Q.kCGWindowOwnerName, 'Application')),
            str(window.get(Q.kCGWindowName) or window.get(Q.kCGWindowOwnerName, 'Window')),
            round(bounds['X']), round(bounds['Y']), round(bounds['Width']), round(bounds['Height']),
            0, 0, floating=True,
        ))
    return result


def visible_windows(monitors, windows):
    return [window for window in windows if not window.hidden and window.mapped and not window.fullscreen
            and any(monitor.rect.intersects(window.rect) for monitor in monitors)]


class Desktop:
    def __init__(self):
        from src.macos.window_motion import WindowBackend
        self.backend = WindowBackend()

    load_monitors = staticmethod(load_monitors)
    select_monitor = staticmethod(select_monitor)
    cursor_pos = staticmethod(cursor_pos)
    visible_windows = staticmethod(visible_windows)

    def window_entries(self):
        entries = Q.CGWindowListCopyWindowInfo(Q.kCGWindowListOptionOnScreenOnly | Q.kCGWindowListExcludeDesktopElements, Q.kCGNullWindowID) or []
        return [entry for entry in entries if entry.get(Q.kCGWindowLayer) == 0
                and entry.get(Q.kCGWindowOwnerPID) != os.getpid()]

    def refresh(self, entries=None):
        self.backend.refresh(self.window_entries() if entries is None else entries)

    def load_windows(self, entries=None):
        from src.macos.accessibility import is_trusted
        if not is_trusted():
            return load_windows()
        with self.backend.mutex:
            snapshot = list(self.backend.snapshot)
            ids = dict(self.backend.window_ids)
        entries = self.window_entries() if entries is None else entries
        by_id = {entry[Q.kCGWindowNumber]: entry[Q.kCGWindowBounds] for entry in entries}
        result = []
        for window in snapshot:
            bounds = by_id.get(ids.get(window.address))
            if bounds is None or bounds['Width'] < 100 or bounds['Height'] < 60:
                continue
            # Stage Manager thumbnails keep the window ID, but are not physical platforms.
            if bounds['Width'] < window.width * .6 and bounds['Height'] < window.height * .6:
                continue
            result.append(replace(window, x=round(bounds['X']), y=round(bounds['Y']),
                                  width=round(bounds['Width']), height=round(bounds['Height'])))
        return result

    def WindowMotion(self, originals):
        from src.macos.window_motion import WindowMotion
        return WindowMotion(self.backend, originals)

    def close(self):
        self.backend.close()
