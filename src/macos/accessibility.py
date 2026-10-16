from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import ApplicationServices as AX
import CoreFoundation as CF
import Quartz as Q

from src.runtime import Rect


class AccessibilityError(RuntimeError):
    pass


def is_trusted(*, prompt: bool = False) -> bool:
    return bool(AX.AXIsProcessTrustedWithOptions({AX.kAXTrustedCheckOptionPrompt: prompt}))


def read(element, attribute):
    error, value = AX.AXUIElementCopyAttributeValue(element, attribute, None)
    if error:
        raise AccessibilityError(f"Reading {attribute} failed (AX error {error})")
    return value


def write(element, attribute, value) -> None:
    error = AX.AXUIElementSetAttributeValue(element, attribute, value)
    if error:
        raise AccessibilityError(f"Setting {attribute} failed (AX error {error})")


def settable(element, attribute) -> bool:
    error, allowed = AX.AXUIElementIsAttributeSettable(element, attribute, None)
    return not error and bool(allowed)


def geometry(element) -> Rect:
    position = read(element, AX.kAXPositionAttribute)
    size = read(element, AX.kAXSizeAttribute)
    ok_position, point = AX.AXValueGetValue(position, AX.kAXValueCGPointType, None)
    ok_size, dimensions = AX.AXValueGetValue(size, AX.kAXValueCGSizeType, None)
    if not ok_position or not ok_size:
        raise AccessibilityError("Window position or size is not an AX point/size")
    return Rect(round(point.x), round(point.y), round(dimensions.width), round(dimensions.height))


@dataclass
class WindowTarget:
    pid: int
    element: object
    original: Rect
    original_minimized: bool
    window_id: int | None = None

    @classmethod
    def for_process(cls, pid: int) -> list[WindowTarget]:
        if not is_trusted():
            raise AccessibilityError("Accessibility access is required for window movement")
        application = AX.AXUIElementCreateApplication(pid)
        AX.AXUIElementSetMessagingTimeout(application, 0.2)
        result = []
        for element in read(application, AX.kAXWindowsAttribute):
            AX.AXUIElementSetMessagingTimeout(element, 0.2)
            if read(element, AX.kAXRoleAttribute) != AX.kAXWindowRole:
                continue
            if read(element, AX.kAXSubroleAttribute) != AX.kAXStandardWindowSubrole:
                continue
            result.append(cls(pid, element, geometry(element), bool(read(element, AX.kAXMinimizedAttribute))))
        return result

    def move(self, rect: Rect, *, resize: bool = False) -> dict:
        started = perf_counter()
        if not settable(self.element, AX.kAXPositionAttribute):
            raise AccessibilityError("Window position is not writable")
        if resize and not settable(self.element, AX.kAXSizeAttribute):
            raise AccessibilityError("Window size is not writable")
        write(self.element, AX.kAXPositionAttribute, AX.AXValueCreate(AX.kAXValueCGPointType, (rect.x, rect.y)))
        if resize:
            write(self.element, AX.kAXSizeAttribute, AX.AXValueCreate(AX.kAXValueCGSizeType, (rect.width, rect.height)))
        actual = geometry(self.element)
        return {"requested": vars(rect), "actual": vars(actual), "milliseconds": (perf_counter() - started) * 1000}

    def minimize(self, value: bool) -> None:
        if not settable(self.element, AX.kAXMinimizedAttribute):
            raise AccessibilityError("Window minimization is not writable")
        write(self.element, AX.kAXMinimizedAttribute, value)

    @property
    def minimized(self) -> bool:
        return bool(read(self.element, AX.kAXMinimizedAttribute))

    @property
    def stashed(self) -> bool:
        if self.minimized:
            return True
        if self.window_id is None or not CF.CFPreferencesCopyAppValue('GloballyEnabled', 'com.apple.WindowManager'):
            return False
        entries = Q.CGWindowListCopyWindowInfo(Q.kCGWindowListOptionIncludingWindow, self.window_id) or []
        entry = next((entry for entry in entries if entry.get(Q.kCGWindowNumber) == self.window_id), None)
        if entry is None:
            return False
        bounds = entry[Q.kCGWindowBounds]
        rect = geometry(self.element)
        return (not entry.get(Q.kCGWindowIsOnscreen, False) or
                (bounds['Width'] < rect.width * .6 and bounds['Height'] < rect.height * .6))

    def restore(self) -> dict:
        was_stashed = self.stashed
        self.minimize(False)
        result = self.move(self.original, resize=settable(self.element, AX.kAXSizeAttribute))
        self.minimize(self.original_minimized)
        if was_stashed and not self.original_minimized:
            error = AX.AXUIElementPerformAction(self.element, AX.kAXRaiseAction)
            if error:
                raise AccessibilityError(f'还原窗口失败（AX error {error}）')
        return result
