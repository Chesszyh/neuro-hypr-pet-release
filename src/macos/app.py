from __future__ import annotations

import argparse
import fcntl
import json
import signal
import socket
import sys
import time
import traceback
import resource
from collections import deque
from pathlib import Path

import AppKit as AK
import Foundation as F
import objc

from src.controller import PetController, load_image_set
from src.manager import PetManager
from src.paths import default_collection, preferences_path
from src.runtime import PetWorld
from src.macos import desktop
from src.macos.manager_ui import ManagerUI
from src.macos.sound import SoundPlayer
from src.macos.sprite_window import SpriteWindow

BUNDLE_ID = 'io.github.chesszyh.neuro-hypr-pet'


class MacApplication:
    def __init__(self, args):
        self.args = args
        self.collection = args.collection.expanduser().resolve()
        self.manager = None
        self.message = ''
        self.world = PetWorld()
        self.players = []
        self.stopping = False
        self.started = time.monotonic()
        self.last_tick = self.started
        self.last_environment = 0
        self.intervals = deque(maxlen=1500)
        self.frame_count = 0
        self.cpu_start = resource.getrusage(resource.RUSAGE_SELF)
        self.image_cache = {}
        self.monitors = []
        self.windows = []
        self.desktop = desktop.Desktop()
        self._neuro_hypr_shimeji_windows = []
        self._neuro_hypr_window_originals = {}
        self.ui = ManagerUI.alloc().init().configure(self)

    def get_application_id(self):
        return BUNDLE_ID

    def attach_manager(self):
        self.manager = PetManager(self, self.collection, self.create_pet, monitor=self.args.monitor,
                                  selection_path=self.args.preferences, desktop=self.desktop)
        self.manager.listeners.append(self.ui.refresh)

    def create_pet(self, name, monitor):
        catalog, behaviors = load_image_set(self.collection, name)
        return PetController(self, self.collection, catalog, monitor, behaviors, desktop=self.desktop,
                             view_factory=SpriteWindow, sound_factory=lambda catalog: SoundPlayer(catalog, self.players),
                             world=self.world, fps=self.args.fps)

    def launch(self):
        if (self.collection / 'img').is_dir():
            self.attach_manager()
            if self.args.image_set:
                self.manager.set_selection(self.args.image_set)
            self.manager.spawn_selected()
        else:
            self.ui.show()
        self.ui.refresh()

    def step(self):
        now = time.monotonic()
        elapsed = now - self.last_tick
        self.intervals.append((now - self.last_tick) * 1000)
        self.frame_count += 1
        self.last_tick = now
        if getattr(self, 'listener', None) is not None:
            try:
                connection, _ = self.listener.accept()
            except BlockingIOError:
                pass
            else:
                connection.close()
                self.ui.show()
        if self.stopping or (self.args.duration is not None and now - self.started >= self.args.duration):
            self.quit()
            return
        entries = self.desktop.window_entries()
        if now - self.last_environment >= .2:
            self.monitors = desktop.load_monitors()
            self.desktop.refresh(entries)
            self.last_environment = now
        self.windows = self.desktop.load_windows(entries)
        for pet in list(self._neuro_hypr_shimeji_windows):
            pet.sync_environment(self.monitors, self.windows)
        cursor = desktop.cursor_pos()
        for pet in list(self._neuro_hypr_shimeji_windows):
            try:
                pet.step(cursor, elapsed=elapsed)
            except Exception as error:
                pet.paused = True
                self.report_error(error)
        self.players[:] = [player for player in self.players if player.isPlaying()]
        with self.desktop.backend.mutex:
            errors = dict(self.desktop.backend.errors)
            completed = set(self.desktop.backend.completed_minimizations)
            self.desktop.backend.completed_minimizations.clear()
        if self.manager:
            for address in completed:
                self.manager.minimizations.pop(address, None)
        for address, message in errors.items():
            if message != self.message:
                self.message = message
                print(f'{address}: {message}', file=sys.stderr, flush=True)
                self.ui.refresh()

    def report_error(self, error):
        self.message = str(error)
        traceback.print_exception(error)
        if self.ui:
            self.ui.refresh()

    def quit(self):
        if getattr(self, '_finished', False):
            return
        self._finished = True
        self.delegate.timer.invalidate()
        if self.manager:
            self.manager.shutdown()
        if self.args.report:
            cpu = resource.getrusage(resource.RUSAGE_SELF)
            elapsed = time.monotonic() - self.started
            intervals = sorted(self.intervals)
            report = {'pets': [{'name': pet.catalog.image_set_dir.name, 'action': pet.runtime.action_name,
                                'x': pet.runtime.anchor_x, 'y': pet.runtime.anchor_y, 'ticks': pet.ticks,
                                'paused': pet.paused} for pet in self._neuro_hypr_shimeji_windows],
                      'frames': self.frame_count, 'max_interval_ms': max(self.intervals, default=0),
                      'median_interval_ms': intervals[len(intervals)//2] if intervals else 0,
                      'p95_interval_ms': intervals[min(len(intervals)-1, int(len(intervals)*.95))] if intervals else 0,
                      'cpu_percent': 100 * ((cpu.ru_utime - self.cpu_start.ru_utime) + (cpu.ru_stime - self.cpu_start.ru_stime)) / max(.001, elapsed),
                      'max_rss_bytes': cpu.ru_maxrss, 'message': self.message}
            self.args.report.parent.mkdir(parents=True, exist_ok=True)
            self.args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        for pet in list(self._neuro_hypr_shimeji_windows):
            pet.close()
        for player in self.players:
            player.stop()
        self.desktop.close()
        self.ui.close()
        if getattr(self, 'listener', None) is not None:
            self.listener.close()
            self.args.preferences.with_suffix('.sock').unlink(missing_ok=True)
        AK.NSApp.terminate_(None)


class ApplicationDelegate(F.NSObject):
    def applicationDidFinishLaunching_(self, notification):
        AK.NSApp.setActivationPolicy_(AK.NSApplicationActivationPolicyAccessory)
        self.timer = F.NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            1 / self.owner.args.fps, self, 'tick:', None, True)
        F.NSRunLoop.mainRunLoop().addTimer_forMode_(self.timer, F.NSRunLoopCommonModes)
        try:
            self.owner.launch()
        except Exception as error:
            self.owner.report_error(error)
            self.owner.ui.show()

    def applicationShouldHandleReopen_hasVisibleWindows_(self, application, visible):
        self.owner.ui.show()
        return True

    def tick_(self, timer):
        try:
            self.owner.step()
        except Exception as error:
            self.owner.report_error(error)

    def applicationWillTerminate_(self, notification):
        if not getattr(self.owner, '_finished', False):
            self.owner.quit()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='Neurolings desktop pets for macOS')
    parser.add_argument('--collection', type=Path, default=default_collection())
    parser.add_argument('--preferences', type=Path, default=preferences_path())
    parser.add_argument('--image-set', action='append', help='Summon this material; may be repeated')
    parser.add_argument('--monitor', default='auto', help='Display ID, auto, or all')
    parser.add_argument('--fps', type=int, default=60, help='Display refresh rate; physics runs at 25 ticks per second')
    parser.add_argument('--duration', type=float, help='Exit after this many seconds')
    parser.add_argument('--report', type=Path, help='Write runtime state when exiting')
    args = parser.parse_args(argv)
    if not 1 <= args.fps <= 120:
        parser.error('--fps must be between 1 and 120')
    return args


def main(argv=None):
    args = parse_args(argv)
    args.preferences.parent.mkdir(parents=True, exist_ok=True)
    lock = args.preferences.with_suffix('.lock').open('a+')
    socket_path = args.preferences.with_suffix('.sock')
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(str(socket_path))
        return 0
    socket_path.unlink(missing_ok=True)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    listener.listen(8)
    listener.setblocking(False)
    native = AK.NSApplication.sharedApplication()
    native.setActivationPolicy_(AK.NSApplicationActivationPolicyAccessory)
    application = MacApplication(args)
    application.listener = listener
    delegate = ApplicationDelegate.alloc().init()
    delegate.owner = application
    application.delegate = delegate
    native.setDelegate_(delegate)
    signal.signal(signal.SIGTERM, lambda *_: setattr(application, 'stopping', True))
    signal.signal(signal.SIGINT, lambda *_: setattr(application, 'stopping', True))
    native.run()
    return 0
