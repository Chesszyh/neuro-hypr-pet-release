from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import AppKit as AK
import CoreFoundation as CF
import objc
import Quartz as Q

from src.desktop import WindowInfo, clamp_window_rect
from src.macos.accessibility import AccessibilityError, WindowTarget, geometry, is_trusted, read, AX


class WindowBackend:
    def __init__(self):
        # Resolve PyObjC's lazy trust symbols before the main and AX threads can request them together.
        is_trusted()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='pet-ax')
        self.registry = {}
        self.snapshot = []
        self.window_ids = {}
        self.owners = {}
        self.pending = {}
        self.results = {}
        self.modified = set()
        self.errors = {}
        self.mutex = threading.Lock()
        self.sequence = 0
        self.refreshing = False
        self.closing = False
        self.completed_minimizations = set()

    def refresh(self, cg_windows):
        with self.mutex:
            if self.refreshing or self.closing:
                return
            self.refreshing = True
        self.executor.submit(self._refresh, cg_windows)

    def _refresh(self, cg_windows):
        try:
            with objc.autorelease_pool():
                windows, live, window_ids = [], {}, {}
                if not is_trusted():
                    with self.mutex:
                        self.snapshot = []
                    return
                for pid in {item[Q.kCGWindowOwnerPID] for item in cg_windows}:
                    app = AK.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
                    if app is None:
                        continue
                    try:
                        targets = WindowTarget.for_process(pid)
                    except AccessibilityError:
                        continue
                    for target in targets:
                        try:
                            if target.minimized:
                                continue
                            try:
                                fullscreen = bool(read(target.element, 'AXFullScreen'))
                            except AccessibilityError:
                                fullscreen = False
                            if fullscreen:
                                continue
                            rect = geometry(target.element)
                            address = next((key for key, previous in self.registry.items()
                                            if previous.pid == pid and CF.CFEqual(previous.element, target.element)), None)
                            known_id = self.window_ids.get(address)
                            # CG and AX samples are taken at different times while a window is moving.
                            candidates = [item for item in cg_windows if item[Q.kCGWindowOwnerPID] == pid
                                          and ((known_id is not None and item.get(Q.kCGWindowNumber) == known_id)
                                               or (known_id is None and all(abs(item[Q.kCGWindowBounds][key] - value) <= 3
                                                   for key, value in [('X', rect.x), ('Y', rect.y),
                                                                      ('Width', rect.width), ('Height', rect.height)])))]
                            if not candidates:
                                continue
                            if address is None:
                                self.sequence += 1
                                address = f'ax:{self.sequence}'
                            existing = self.registry.get(address)
                            live[address] = existing or target
                            window_ids[address] = candidates[0].get(Q.kCGWindowNumber)
                            live[address].window_id = window_ids[address]
                            try:
                                title = str(read(target.element, AX.kAXTitleAttribute))
                            except AccessibilityError:
                                title = str(app.localizedName())
                            windows.append(WindowInfo(address, str(app.bundleIdentifier() or app.localizedName()), title,
                                                      rect.x, rect.y, rect.width, rect.height, 0, 0, floating=True))
                        except AccessibilityError:
                            continue
                # Retain modified targets while minimized so explicit restore keeps their AX identity.
                with self.mutex:
                    for key, target in self.registry.items():
                        if key not in live and key in self.modified:
                            live[key] = target
                    self.registry = live
                    self.snapshot = windows
                    self.window_ids.update(window_ids)
                    self.window_ids = {key: value for key, value in self.window_ids.items() if key in live}
        except Exception as error:
            with self.mutex:
                self.errors['environment'] = str(error)
        finally:
            with self.mutex:
                self.refreshing = False

    def begin(self, owner, window):
        with self.mutex:
            target = self.registry.get(window.address)
            if target is None:
                raise AccessibilityError('目标窗口已不可用，请刷新窗口列表')
            previous = self.owners.get(window.address)
            if previous is not None and previous is not owner:
                raise AccessibilityError('另一只桌宠正在搬运此窗口')
            self.owners[window.address] = owner
            self.errors.pop(window.address, None)
        return target

    def move(self, owner, address, rect):
        with self.mutex:
            if self.owners.get(address) is not owner:
                return
            already_pending = address in self.pending
            self.pending[address] = (owner, rect)
        if not already_pending:
            self.executor.submit(self._drain, address)

    def _drain(self, address):
        while True:
            with self.mutex:
                request = self.pending.get(address)
                target = self.registry.get(address)
                if request is None or target is None:
                    self.pending.pop(address, None)
                    return
                owner, rect = request
                if self.owners.get(address) is not owner:
                    self.pending.pop(address, None)
                    return
            try:
                with objc.autorelease_pool():
                    if address not in self.modified:
                        target.original = geometry(target.element)
                        target.original_minimized = target.minimized
                        self.modified.add(address)
                    result = target.move(rect)
                with self.mutex:
                    self.results[address] = result
            except AccessibilityError as error:
                with self.mutex:
                    self.errors[address] = str(error)
                    self.pending.pop(address, None)
                return
            with self.mutex:
                if self.pending.get(address) == request:
                    self.pending.pop(address, None)
                    return

    def release(self, owner, address):
        with self.mutex:
            if self.owners.get(address) is owner:
                self.owners.pop(address, None)
                self.pending.pop(address, None)

    def restore(self, originals):
        for address, target in list(originals.items()):
            self.executor.submit(self._restore, address, target)
        originals.clear()

    def _restore(self, address, target):
        try:
            with objc.autorelease_pool():
                result = target.restore()
            with self.mutex:
                self.results[address] = result
                self.modified.discard(address)
        except AccessibilityError as error:
            with self.mutex:
                self.errors[address] = str(error)

    def minimize(self, address):
        cancelled = threading.Event()
        self.executor.submit(self._minimize, address, cancelled)
        return cancelled.set

    def _minimize(self, address, cancelled):
        try:
            with objc.autorelease_pool():
                if cancelled.is_set():
                    return
                target = self.registry[address]
                target.minimize(True)
                import time
                deadline = time.monotonic() + 1
                while time.monotonic() < deadline:
                    if cancelled.is_set():
                        target.minimize(False)
                        return
                    if target.stashed:
                        with self.mutex:
                            self.completed_minimizations.add(address)
                        return
                    time.sleep(.04)
                raise AccessibilityError('应用未完成最小化')
        except (AccessibilityError, KeyError) as error:
            with self.mutex:
                self.errors[address] = str(error)
                self.completed_minimizations.add(address)

    def close(self):
        with self.mutex:
            self.closing = True
            self.pending.clear()
        self.executor.shutdown(wait=True)


class WindowMotion:
    def __init__(self, backend, originals):
        self.backend, self.originals = backend, originals
        self.target = None
        self.last_rect = None

    def begin(self, window):
        if self.target is not None and self.target.address != window.address:
            self.release()
        target = self.backend.begin(self, window)
        if self.target is None:
            with self.backend.mutex:
                self.backend.results.pop(window.address, None)
        self.originals.setdefault(window.address, target)
        self.target = window

    def release(self):
        if self.target is not None:
            self.backend.release(self, self.target.address)
        self.target = None
        self.last_rect = None

    def finish(self):
        if self.target is not None:
            self.backend.executor.submit(self.backend.release, self, self.target.address)
        self.target = None
        self.last_rect = None

    def move(self, window, rect, monitors):
        self.begin(window)
        bounded = clamp_window_rect(rect, monitors)
        self.backend.move(self, window.address, bounded)
        with self.backend.mutex:
            error = self.backend.errors.pop(window.address, None)
            result = self.backend.results.get(window.address)
        if error:
            raise AccessibilityError(error)
        if result:
            from src.runtime import Rect
            actual = Rect(**result['actual'])
            requested = Rect(**result.get('requested', result['actual']))
            # Readback belongs to an older request; apply its constraint offset, not its old position.
            self.last_rect = Rect(bounded.x + actual.x - requested.x, bounded.y + actual.y - requested.y,
                                  actual.width, actual.height)
        else:
            self.last_rect = bounded
        return self.last_rect

    def restore(self, windows, monitors):
        self.backend.restore(self.originals)
        self.release()
        return '已提交窗口还原请求'
