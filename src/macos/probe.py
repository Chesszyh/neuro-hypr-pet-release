from __future__ import annotations

import argparse
import json
import io
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import AppKit as AK
import Foundation as F
import objc
from src.macos.accessibility import AccessibilityError, WindowTarget, is_trusted
from src.runtime import Rect


def probe_image():
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (240, 240))
    draw = ImageDraw.Draw(image)
    draw.ellipse((40, 40, 199, 199), fill=(51, 179, 230, 255))
    draw.rectangle((100, 210, 139, 229), fill=(255, 77, 102, 64))
    output = io.BytesIO()
    image.save(output, format="PNG")
    native = AK.NSImage.alloc().initWithData_(F.NSData.dataWithBytes_length_(output.getvalue(), len(output.getvalue())))
    native.setSize_((240, 240))
    return native


class ClickView(AK.NSView):
    def acceptsFirstMouse_(self, event):
        return True

    def mouseDown_(self, event):
        point = self.window().convertPointToScreen_(event.locationInWindow())
        self.owner.record("mouse_down", surface=self.label, x=point.x, y=point.y,
                          active=bool(AK.NSApp.isActive()), key=bool(self.window().isKeyWindow()))
        self.grab = point
        self.origin = self.window().frame().origin

    def mouseDragged_(self, event):
        if self.label != "sprite":
            return
        point = AK.NSEvent.mouseLocation()
        self.window().setFrameOrigin_((self.origin.x + point.x - self.grab.x, self.origin.y + point.y - self.grab.y))
        self.owner.record("mouse_dragged", surface=self.label, x=point.x, y=point.y)

    def mouseUp_(self, event):
        self.owner.record("mouse_up", surface=self.label)

    def drawRect_(self, rect):
        if self.label == "sprite":
            AK.NSColor.clearColor().set()
            AK.NSRectFillUsingOperation(self.bounds(), AK.NSCompositingOperationCopy)
            self.owner.image.drawInRect_fromRect_operation_fraction_(self.bounds(), AK.NSZeroRect, AK.NSCompositingOperationSourceOver, 1.0)
        else:
            AK.NSColor.windowBackgroundColor().set()
            AK.NSRectFill(rect)
            text = "Click the blue circle, transparent corners, and red translucent strip."
            AK.NSString.drawAtPoint_withAttributes_(text, (20, 15), {AK.NSFontAttributeName: AK.NSFont.systemFontOfSize_(14)})


class ProbePanel(AK.NSPanel):
    def canBecomeKeyWindow(self):
        return False

    def canBecomeMainWindow(self):
        return False


class Probe(F.NSObject):
    @objc.python_method
    def configure(self, args):
        self.args = args
        self.events = []
        self.windows = []
        self.started = time.monotonic()
        self.last_tick = self.started
        self.intervals = []
        self.target_process = None
        self.targets = []
        self.ax_step = 0
        self.failure = None
        self.finishing = False
        self.stop_requested = False
        return self

    @objc.python_method
    def record(self, kind, **data):
        event = {"seconds": round(time.monotonic() - self.started, 4), "event": kind, **data}
        self.events.append(event)
        print(json.dumps(event, ensure_ascii=False), flush=True)

    def applicationDidFinishLaunching_(self, notification):
        AK.NSApp.setActivationPolicy_(AK.NSApplicationActivationPolicyRegular if self.args.target else AK.NSApplicationActivationPolicyAccessory)
        screens = list(AK.NSScreen.screens())
        frame = screens[0].visibleFrame()
        x, y = frame.origin.x + 60, frame.origin.y + 80
        if self.args.target:
            for index in range(2):
                window = AK.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                    ((x + 410 * index, y), (380, 310)),
                    AK.NSWindowStyleMaskTitled | AK.NSWindowStyleMaskClosable | AK.NSWindowStyleMaskMiniaturizable | AK.NSWindowStyleMaskResizable,
                    AK.NSBackingStoreBuffered, False)
                window.setTitle_("Neuro macOS probe target")
                window.setReleasedWhenClosed_(False)
                view = ClickView.alloc().initWithFrame_(((0, 0), (380, 310)))
                view.owner, view.label = self, f"target-{index}"
                window.setContentView_(view)
                window.orderFrontRegardless()
                self.windows.append(window)
            self.record("targets_ready", pid=os.getpid())
        else:
            self.image = probe_image()
            if getattr(sys, "frozen", False):
                target = Path(sys.executable).resolve().parents[3] / "Neuro macOS Probe Target.app/Contents/MacOS/Neuro macOS Probe Target"
                command = [str(target)]
            else:
                command = [sys.executable, str(Path(__file__).resolve().parents[2] / "tools/neuro_macos_probe_target.py")]
            command += ["--duration", str(self.args.duration + 5)]
            self.target_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            sprite = ProbePanel.alloc().initWithContentRect_styleMask_backing_defer_(
                ((x + 70, y + 45), (240, 240)),
                AK.NSWindowStyleMaskBorderless | AK.NSWindowStyleMaskNonactivatingPanel,
                AK.NSBackingStoreBuffered, False)
            sprite.setOpaque_(False)
            sprite.setBackgroundColor_(AK.NSColor.clearColor())
            sprite.setHasShadow_(False)
            sprite.setHidesOnDeactivate_(False)
            sprite.setLevel_(AK.NSFloatingWindowLevel)
            sprite.setCollectionBehavior_(AK.NSWindowCollectionBehaviorCanJoinAllSpaces |
                                          AK.NSWindowCollectionBehaviorCanJoinAllApplications)
            sprite.setReleasedWhenClosed_(False)
            view = ClickView.alloc().initWithFrame_(((0, 0), (240, 240)))
            view.owner, view.label = self, "sprite"
            sprite.setContentView_(view)
            sprite.orderFrontRegardless()
            self.windows.append(sprite)
            self.record("sprite_ready", accessibility_trusted=is_trusted(), target_pid=self.target_process.pid,
                        transparent_point=[x + 80, y + 55], opaque_point=[x + 190, y + 165],
                        screens=[{"name": str(s.localizedName()), "scale": s.backingScaleFactor(),
                                  "frame": [[s.frame().origin.x, s.frame().origin.y], [s.frame().size.width, s.frame().size.height]]}
                                 for s in screens])
        self.timer = F.NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(0.04, self, "tick:", None, True)
        F.NSRunLoop.mainRunLoop().addTimer_forMode_(self.timer, F.NSRunLoopCommonModes)

    def tick_(self, timer):
        now = time.monotonic()
        self.intervals.append((now - self.last_tick) * 1000)
        self.last_tick = now
        elapsed = now - self.started
        if self.args.exercise_ax and not self.args.target and elapsed > 1:
            self.exerciseAX()
        if elapsed >= self.args.duration or self.stop_requested:
            self.finish()

    @objc.python_method
    def exerciseAX(self):
        if self.failure or self.ax_step >= 80:
            return
        try:
            if not self.targets:
                self.targets = WindowTarget.for_process(self.target_process.pid)
                if len(self.targets) != 2:
                    raise AccessibilityError(f"Expected two dedicated targets, found {len(self.targets)}")
                self.targets.sort(key=lambda target: target.original.x)
                import Quartz as Q
                entries = Q.CGWindowListCopyWindowInfo(Q.kCGWindowListOptionOnScreenOnly, Q.kCGNullWindowID) or []
                for target in self.targets:
                    rect = target.original
                    match = next((item for item in entries if item.get(Q.kCGWindowOwnerPID) == target.pid
                                  and all(abs(item[Q.kCGWindowBounds][key] - value) <= 3 for key, value in
                                          [('X', rect.x), ('Y', rect.y), ('Width', rect.width), ('Height', rect.height)])), None)
                    target.window_id = match[Q.kCGWindowNumber] if match else None
                self.record("ax_bound", originals=[vars(target.original) for target in self.targets])
            index = self.ax_step // 25
            if index < 2:
                target = self.targets[index]
                original = target.original
                delta = (self.ax_step % 25 + 1) * 2
                result = target.move(Rect(original.x + delta, original.y + delta, original.width + 20, original.height + 10), resize=self.ax_step % 25 == 0)
                self.record("ax_move", target=index, **result)
                if result["actual"] != result["requested"]:
                    raise AccessibilityError("Target did not accept the requested geometry")
            elif self.ax_step == 50:
                if self.targets[0].stashed:
                    raise AccessibilityError('Target was already stashed before minimization')
                self.targets[0].minimize(True)
                self.record("ax_minimize", target=0)
            elif self.ax_step == 65:
                if not self.targets[0].stashed:
                    raise AccessibilityError("Target did not minimize within 600 ms")
                self.record("ax_minimize_confirmed", target=0, dock_minimized=self.targets[0].minimized,
                            window_id=self.targets[0].window_id)
                self.record("ax_restore", target=0, **self.targets[0].restore())
            elif self.ax_step == 79:
                if self.targets[0].stashed:
                    raise AccessibilityError("Target did not restore within 560 ms")
                self.record("ax_restore", target=1, **self.targets[1].restore())
                self.record("ax_sequence_completed")
            self.ax_step += 1
        except AccessibilityError as error:
            self.failure = str(error)
            self.record("ax_failed", error=self.failure)

    @objc.python_method
    def finish(self):
        if self.finishing:
            return
        self.finishing = True
        self.timer.invalidate()
        for target in self.targets:
            try:
                target.restore()
            except AccessibilityError as error:
                self.record("restore_failed", error=str(error))
        target_events = []
        if self.target_process:
            self.target_process.terminate()
            try:
                output, _ = self.target_process.communicate(timeout=3)
                for line in output.splitlines():
                    try:
                        target_events.append(json.loads(line))
                    except ValueError:
                        self.record("target_output", text=line)
            except subprocess.TimeoutExpired:
                self.target_process.kill()
                self.target_process.communicate()
        if self.args.report:
            intervals = sorted(self.intervals)
            report = {"events": self.events, "target_events": target_events,
                      "frame_intervals_ms": {"samples": len(intervals), "median": intervals[len(intervals)//2] if intervals else None,
                                             "max": max(intervals, default=0)},
                      "ax_failure": self.failure,
                      "manual_checks": {"physical_clicks": "pending", "rapid_entry": "pending", "spaces": "pending", "multiple_screens": "pending"}}
            self.args.report.parent.mkdir(parents=True, exist_ok=True)
            self.args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        for window in self.windows:
            window.close()
        AK.NSApp.terminate_(None)

    def applicationWillTerminate_(self, notification):
        if not self.finishing:
            self.finish()


def main():
    parser = argparse.ArgumentParser(description="macOS transparent input and dedicated-window AX prototype")
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--exercise-ax", action="store_true", help="Move only the two windows created by this probe")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--target", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.duration <= 0:
        parser.error("--duration must be positive")
    app = AK.NSApplication.sharedApplication()
    delegate = Probe.alloc().init().configure(args)
    def stop(signum, frame):
        delegate.stop_requested = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()
