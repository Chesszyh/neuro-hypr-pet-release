from __future__ import annotations

from dataclasses import dataclass

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


def desktop_rect(monitors: list[MonitorInfo]) -> Rect:
    left = min(monitor.x for monitor in monitors)
    top = min(monitor.y for monitor in monitors)
    right = max(monitor.rect.right for monitor in monitors)
    bottom = max(monitor.rect.bottom for monitor in monitors)
    return Rect(left, top, right - left, bottom - top)


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

