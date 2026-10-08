#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes.util
import os
import random
import re
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


os.environ.setdefault("GDK_BACKEND", "wayland")


def ensure_layer_shell_preloaded() -> None:
    ld_preload = os.environ.get("LD_PRELOAD", "")
    if "gtk4-layer-shell" in ld_preload or os.environ.get("NEURO_HYPR_SHIMEJI_PRELOADED") == "1":
        return
    lib = ctypes.util.find_library("gtk4-layer-shell")
    if lib and not lib.startswith("/"):
        for candidate in (Path("/usr/lib64") / lib, Path("/lib64") / lib):
            if candidate.exists():
                lib = str(candidate)
                break
    if not lib:
        fallback = Path("/usr/lib64/libgtk4-layer-shell.so.0")
        if fallback.exists():
            lib = str(fallback)
    if not lib:
        return
    env = os.environ.copy()
    env["LD_PRELOAD"] = f"{lib}:{ld_preload}" if ld_preload else lib
    env["NEURO_HYPR_SHIMEJI_PRELOADED"] = "1"
    os.execvpe(sys.executable, [sys.executable, *sys.argv], env)


ensure_layer_shell_preloaded()

import cairo
import gi

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Gtk4LayerShell  # noqa: E402

from src.assets import default_collection

from src.hyprland import (
    WindowMotion,
    WindowPlacement,
    MonitorInfo,
    WindowInfo,
    active_window,
    active_window_rect_for_monitor,
    cursor_pos,
    desktop_rect,
    load_monitors,
    load_windows,
    select_monitor,
    monitor_for_point,
    floating_window_rects_for_monitor,
    set_window_floating,
    resize_window,
    clamp_window_rect,
)
from src.manager import PetManager, preferences_path, save_selection
from src.manager_ui import ManagerPopup, SplitControls
from src.window_effects import animate_minimize
from src.tray import PetTray
from src.runtime import PetRuntime, PetWorld, Rect, RuntimeConfig
from src.service import write_manager_desktop_entry, write_shimeji_user_service
from src.shimeji_model import ActionCatalog, BehaviorCatalog, PoseFrame, load_action_catalog, load_behavior_catalog
from src.sound import SoundPlayer


DEFAULT_ENV_SYNC_HZ = 5

MANUAL_BEHAVIOR_LABELS = {
    "SitAndFaceMouse": "看向鼠标",
    "SitDown": "坐下",
    "SitWhileDanglingLegs": "晃晃双腿",
    "LieDown": "躺下",
    "HeartHeartHeart": "比心",
    "Wink": "眨眼",
    "SplitIntoTwo": "分裂成两只",
    "Gymbag": "从包里叫来伙伴",
    "CrawlAlongWorkAreaFloor": "沿地面爬行",
    "ClimbAlongWall": "沿墙攀爬",
    "ClimbAlongCeiling": "沿顶端攀爬",
    "NoticeFallingTutel": "留意落下的 Tutel",
    "HugEvil": "拥抱 Evil",
    "HurlEvil": "抛起 Evil",
    "AskForHugs": "讨抱抱",
    "RunAndGrabBottomLeftWall": "跑向左侧墙角",
    "RunAndGrabBottomRightWall": "跑向右侧墙角",
    "JumpFromBottomOfIE": "从窗口底边跳下",
    "ThrowIEFromLeft": "从左侧抛出窗口",
    "ThrowIEFromRight": "从右侧抛出窗口",
    "RunAndThrowIEFromLeft": "跑动后从左侧抛窗",
    "RunAndThrowIEFromRight": "跑动后从右侧抛窗",
}

COMPANION_CHOICES = (
    ("Eviling", "召唤 Evil", ("Eviling",)),
    ("Tuteling", "召唤 Tutel", ("Tuteling", "Vedaling")),
)


def manual_behavior_label(name: str) -> str:
    return MANUAL_BEHAVIOR_LABELS.get(name, re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name))


class SurfaceCache:
    def __init__(self, image_set_dir: Path) -> None:
        self.image_set_dir = image_set_dir
        self.surfaces: dict[str, cairo.ImageSurface] = {}

    def get(self, frame: PoseFrame, *, look_right: bool = False) -> cairo.ImageSurface:
        image = frame.image_for_direction(look_right=look_right)
        surface = self.surfaces.get(image)
        if surface is None:
            if image:
                surface = cairo.ImageSurface.create_from_png(str(self.image_set_dir / image))
            else:
                surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
            self.surfaces[image] = surface
        return surface


def make_runtime(catalog: ActionCatalog, monitor: MonitorInfo, behavior_catalog: BehaviorCatalog | None = None) -> PetRuntime:
    initial_action = catalog.actions.get("Falling") or next(iter(catalog.actions.values()))
    initial_frame = initial_action.frames[0]
    return PetRuntime(
        catalog,
        RuntimeConfig(
            work_area=monitor.global_work_area,
            start_x=monitor.global_work_area.left + (monitor.work_area.width // 2),
            start_y=monitor.global_work_area.top + initial_frame.anchor_y,
        ),
        behavior_catalog=behavior_catalog,
    )


def draw_surface(cr: cairo.Context, surface: cairo.ImageSurface, x: int, y: int, mirror: bool) -> None:
    if mirror:
        cr.save()
        cr.translate(x + surface.get_width(), y)
        cr.scale(-1, 1)
        cr.set_source_surface(surface, 0, 0)
        cr.paint()
        cr.restore()
    else:
        cr.set_source_surface(surface, x, y)
        cr.paint()


def make_sound_player(catalog: ActionCatalog) -> SoundPlayer:
    collection_root = catalog.image_set_dir.parent.parent
    return SoundPlayer(collection_root, catalog.image_set_dir)


def play_pending_sounds(runtime: PetRuntime, player: SoundPlayer) -> None:
    for event in runtime.pop_sound_events():
        player.play(event)


def format_runtime_state(runtime: PetRuntime, rect: Rect, *, ticks: int) -> str:
    look = "right" if runtime.look_right else "left"
    frame = runtime.frame
    try:
        active_edge = runtime.active_window_edge(tolerance=3)
    except Exception:
        active_edge = "unknown"
    try:
        work_edge = runtime.work_area_edge(tolerance=3)
    except Exception:
        work_edge = "unknown"
    active_window = getattr(runtime, "active_window_rect", None)
    active = (
        "None"
        if active_window is None
        else f"{active_window.x},{active_window.y},{active_window.width},{active_window.height}"
    )
    return (
        "state "
        f"tick={ticks} "
        f"action={runtime.action_name} "
        f"anchor={runtime.anchor_x},{runtime.anchor_y} "
        f"target={runtime.target_x},{runtime.target_y} "
        f"velocity={runtime.velocity_x:.2f},{runtime.velocity_y:.2f} "
        f"look={look} "
        f"dragging={runtime.dragging} "
        f"frame={frame.image} "
        f"rect={rect.x},{rect.y},{rect.width},{rect.height} "
        f"active={active} "
        f"active_edge={active_edge} "
        f"work_edge={work_edge}"
    )


def maybe_print_runtime_state(runtime: PetRuntime, rect: Rect, *, ticks: int, fps: int, enabled: bool) -> None:
    if not enabled:
        return
    interval = max(1, fps)
    if ticks % interval != 0:
        return
    print(format_runtime_state(runtime, rect, ticks=ticks), flush=True)


def environment_sync_due(ticks: int, *, fps: int, sync_hz: int = DEFAULT_ENV_SYNC_HZ) -> bool:
    interval = max(1, round(max(1, fps) / max(1, sync_hz)))
    return ticks % interval == 1


@dataclass(frozen=True)
class SpriteLayerGeometry:
    sprite_rect: Rect
    window_rect: Rect
    draw_x: int
    draw_y: int


def clip_sprite_layer_geometry(sprite_rect: Rect, output_rect: Rect) -> SpriteLayerGeometry:
    left = max(sprite_rect.left, output_rect.left)
    top = max(sprite_rect.top, output_rect.top)
    right = min(sprite_rect.right, output_rect.right)
    bottom = min(sprite_rect.bottom, output_rect.bottom)
    if right <= left:
        left = min(max(sprite_rect.left, output_rect.left), max(output_rect.left, output_rect.right - 1))
        right = left + 1
    if bottom <= top:
        top = min(max(sprite_rect.top, output_rect.top), max(output_rect.top, output_rect.bottom - 1))
        bottom = top + 1
    window_rect = Rect(left, top, right - left, bottom - top)
    return SpriteLayerGeometry(
        sprite_rect=sprite_rect,
        window_rect=window_rect,
        draw_x=sprite_rect.x - window_rect.x,
        draw_y=sprite_rect.y - window_rect.y,
    )


def _surface_alpha_at(data: memoryview, stride: int, x: int, y: int) -> int:
    return data[(y * stride) + (x * 4) + 3]


def sprite_input_region(surface: cairo.ImageSurface, geometry: SpriteLayerGeometry, *, mirror: bool = False) -> cairo.Region:
    width = surface.get_width()
    height = surface.get_height()
    if width <= 0 or height <= 0 or surface.get_format() != cairo.FORMAT_ARGB32:
        return cairo.Region(cairo.RectangleInt(0, 0, geometry.window_rect.width, geometry.window_rect.height))

    surface.flush()
    data = surface.get_data()
    stride = surface.get_stride()
    region = cairo.Region()
    for source_y in range(height):
        local_y = geometry.draw_y + source_y
        if local_y < 0 or local_y >= geometry.window_rect.height:
            continue
        run_start: int | None = None
        run_end = 0
        for drawn_x in range(width):
            source_x = width - 1 - drawn_x if mirror else drawn_x
            local_x = geometry.draw_x + drawn_x
            visible = (
                0 <= local_x < geometry.window_rect.width
                and _surface_alpha_at(data, stride, source_x, source_y) > 0
            )
            if visible and run_start is None:
                run_start = local_x
                run_end = local_x + 1
            elif visible and local_x == run_end:
                run_end = local_x + 1
            elif visible:
                region.union(cairo.RectangleInt(run_start, local_y, run_end - run_start, 1))  # type: ignore[arg-type]
                run_start = local_x
                run_end = local_x + 1
            elif run_start is not None:
                region.union(cairo.RectangleInt(run_start, local_y, run_end - run_start, 1))
                run_start = None
        if run_start is not None:
            region.union(cairo.RectangleInt(run_start, local_y, run_end - run_start, 1))
    return region


def layer_output_rect(window: object) -> Rect:
    monitor = getattr(window, "monitor", None)
    width = getattr(monitor, "width", None)
    height = getattr(monitor, "height", None)
    if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
        return Rect(0, 0, width, height)
    return Rect(-100000, -100000, 200000, 200000)


def close_if_self_destructed(runtime: PetRuntime, window: Gtk.Window) -> bool:
    events = runtime.pop_self_destruct_events()
    if not events:
        return False
    window.close()
    return True


def configure_runtime_from_breed(runtime: PetRuntime, event: object) -> None:
    runtime.anchor_x = event.anchor_x  # type: ignore[attr-defined]
    runtime.anchor_y = event.anchor_y  # type: ignore[attr-defined]
    runtime.look_right = event.look_right  # type: ignore[attr-defined]
    behavior = event.behavior  # type: ignore[attr-defined]
    runtime.start_action(behavior if behavior in runtime.catalog.actions else "Stand")


def apply_interaction_event(event: object) -> None:
    target = event.target  # type: ignore[attr-defined]
    if event.target_look and target.look_right == event.source_look_right:  # type: ignore[attr-defined]
        target.look_right = not event.source_look_right  # type: ignore[attr-defined]
    target_behavior = event.target_behavior  # type: ignore[attr-defined]
    target.start_action(target_behavior if target_behavior in target.catalog.actions else "Stand")


def pet_world_for_application(application: Gtk.Application) -> PetWorld:
    world = getattr(application, "_neuro_hypr_shimeji_world", None)
    if world is None:
        world = PetWorld()
        application._neuro_hypr_shimeji_world = world  # type: ignore[attr-defined]
    return world


def remember_window(application: Gtk.Application, window: Gtk.Window, *, parent=None) -> None:
    manager = getattr(application, "_neuro_hypr_manager", None)
    if manager is not None:
        manager.register(window, parent=parent)
        return
    windows = getattr(application, "_neuro_hypr_shimeji_windows", None)
    if windows is None:
        windows = []
        application._neuro_hypr_shimeji_windows = windows  # type: ignore[attr-defined]
    windows.append(window)


def forget_window(application: Gtk.Application, window: Gtk.Window) -> None:
    windows = getattr(application, "_neuro_hypr_shimeji_windows", None)
    if windows is None or window not in windows:
        return
    windows.remove(window)
    if getattr(application, "_neuro_hypr_shimeji_window", None) is window:
        application._neuro_hypr_shimeji_window = None  # type: ignore[attr-defined]
    manager = getattr(application, "_neuro_hypr_manager", None)
    if manager is not None:
        manager.changed()
    elif not windows:
        application.quit()


def load_image_set(collection: Path, image_set: str) -> tuple[ActionCatalog, BehaviorCatalog | None]:
    actions_xml = collection / "img" / image_set / "conf" / "actions.xml"
    behaviors_xml = collection / "img" / image_set / "conf" / "behaviors.xml"
    catalog = load_action_catalog(actions_xml)
    behavior_catalog = load_behavior_catalog(behaviors_xml) if behaviors_xml.is_file() else None
    return catalog, behavior_catalog


def sync_active_window(
    runtime: PetRuntime, monitor: MonitorInfo, motion: WindowMotion | None = None,
) -> WindowInfo | None:
    try:
        window = active_window()
        current_monitor = next((item for item in load_monitors() if item.name == monitor.name), monitor)
        windows = load_windows()
        rects = [current_monitor.to_global_rect(rect) for rect in floating_window_rects_for_monitor(current_monitor, windows)]
        floating_count = len(rects)
        active_rect = active_window_rect_for_monitor(current_monitor, window)
        if active_rect is not None:
            active_rect = current_monitor.to_global_rect(active_rect)
        if active_rect is not None and active_rect not in rects:
            rects.append(active_rect)
        runtime.update_window_rects(rects, floating_count=floating_count)
        if motion is not None and motion.target is not None and runtime.window_action_active:
            target = next((item for item in windows if item.address == motion.target.address), None)
            if target is not None and target.floating and target.mapped and not target.hidden and not target.fullscreen:
                # Compositor animations can lag behind commanded positions during a carry.
                runtime.active_window_rect = motion.last_rect or target.rect
                return target
            motion.release()
            runtime.desired_active_window_rect = None
            runtime.start_action("Fall" if "Fall" in runtime.catalog.actions else "Falling")
            return None
        return next((item for item in windows if item.rect == runtime.active_window_rect), None)
    except Exception:
        runtime.update_active_window_rect(None)
        return None


def sync_cursor(runtime: PetRuntime, monitor: MonitorInfo) -> None:
    try:
        cursor = cursor_pos()
        runtime.update_cursor_pos(cursor.x, cursor.y)
    except Exception:
        pass


def sync_drag_cursor(runtime: PetRuntime, monitor: MonitorInfo) -> bool:
    if not runtime.dragging:
        return False
    try:
        cursor = cursor_pos()
    except Exception:
        return False
    runtime.update_cursor_pos(cursor.x, cursor.y)
    return runtime.pointer_motion(cursor.x, cursor.y)


class ScreenCoverShimejiWindow(Gtk.ApplicationWindow):
    def __init__(
        self,
        app: Gtk.Application,
        collection: Path,
        catalog: ActionCatalog,
        monitor: MonitorInfo,
        fps: int,
        behavior_catalog: BehaviorCatalog | None = None,
        debug_state: bool = False,
    ) -> None:
        super().__init__(application=app)
        self.collection = collection
        self.catalog = catalog
        self.monitor = monitor
        self.cache = SurfaceCache(catalog.image_set_dir)
        self.sound_player = make_sound_player(catalog)
        self.runtime = make_runtime(catalog, monitor, behavior_catalog)
        self.fps = max(1, fps)
        self.ticks = 0
        self.debug_state = debug_state
        self.paused = False
        self.following_cursor = False
        self.transient = False
        self._closed = False
        self.window_motion = WindowMotion(app._neuro_hypr_window_originals)

        self.set_title("neuro-hypr-shimeji-screen-cover")
        self.set_decorated(False)
        self.set_default_size(monitor.width, monitor.height)
        self.set_css_classes(["neuro-hypr-shimeji-window"])

        Gtk4LayerShell.init_for_window(self)
        Gtk4LayerShell.set_namespace(self, "neuro-hypr-shimeji")
        Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.OVERLAY)
        Gtk4LayerShell.set_exclusive_zone(self, -1)
        Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.NONE)
        for edge in (Gtk4LayerShell.Edge.LEFT, Gtk4LayerShell.Edge.RIGHT, Gtk4LayerShell.Edge.TOP, Gtk4LayerShell.Edge.BOTTOM):
            Gtk4LayerShell.set_anchor(self, edge, True)
        self._select_gdk_monitor()

        self.area = Gtk.DrawingArea()
        self.area.set_draw_func(self._draw)
        self.area.set_hexpand(True)
        self.area.set_vexpand(True)
        self.area.set_can_target(False)
        self.set_child(self.area)
        self.connect("realize", self._on_realize)
        self.connect("close-request", self._on_close_request)

    def start(self) -> None:
        self.present()
        GLib.timeout_add(max(1, round(1000 / self.fps)), self._tick)

    def _select_gdk_monitor(self) -> None:
        display = Gdk.Display.get_default()
        if display is None:
            return
        monitors = display.get_monitors()
        for index in range(monitors.get_n_items()):
            monitor = monitors.get_item(index)
            connector = monitor.get_connector() if hasattr(monitor, "get_connector") else None
            if connector == self.monitor.name:
                Gtk4LayerShell.set_monitor(self, monitor)
                return

    def _on_realize(self, _window: Gtk.Window) -> None:
        surface = self.get_surface()
        if surface is not None and hasattr(surface, "set_input_region"):
            surface.set_input_region(cairo.Region())

    def _tick(self) -> bool:
        if self._closed:
            return False
        if self.paused:
            return True
        self.ticks += 1
        if environment_sync_due(self.ticks, fps=self.fps):
            sync_active_window(self.runtime, self.monitor)
            sync_cursor(self.runtime, self.monitor)
        if self.following_cursor:
            self.runtime.follow_cursor()
        self.runtime.tick()
        play_pending_sounds(self.runtime, self.sound_player)
        self._apply_pending_transforms()
        self.runtime.pop_breed_events()
        if close_if_self_destructed(self.runtime, self):
            return False
        if self.runtime.ready_for_idle and not self.following_cursor and self.ticks % (self.fps * 3) == 0:
            self.runtime.start_idle_action(rng=random)
        surface = self.cache.get(self.runtime.frame, look_right=self.runtime.look_right)
        maybe_print_runtime_state(
            self.runtime,
            self.runtime.sprite_rect(surface.get_width(), surface.get_height()),
            ticks=self.ticks,
            fps=self.fps,
            enabled=self.debug_state,
        )
        self.area.queue_draw()
        return True

    def _on_close_request(self, _window) -> bool:
        self._closed = True
        forget_window(self.get_application(), self)
        return False

    def request_window_interaction(self, _window, *, throw: bool) -> bool:
        raise ValueError("全屏实验模式不支持窗口搬运，请使用默认运行模式")

    def _draw(self, _area: Gtk.DrawingArea, cr: cairo.Context, _width: int, _height: int) -> None:
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        frame = self.runtime.frame
        surface = self.cache.get(frame, look_right=self.runtime.look_right)
        rect = self.monitor.to_local_rect(self.runtime.sprite_rect(surface.get_width(), surface.get_height()))
        draw_surface(cr, surface, rect.x, rect.y, frame.needs_horizontal_flip(look_right=self.runtime.look_right))

    def _apply_pending_transforms(self) -> None:
        for event in self.runtime.pop_transform_events():
            image_set = event.image_set if self._image_set_exists(event.image_set) else self.catalog.image_set_dir.name
            catalog, behavior_catalog = load_image_set(self.collection, image_set)
            self.catalog = catalog
            self.cache = SurfaceCache(catalog.image_set_dir)
            self.sound_player = make_sound_player(catalog)
            self.runtime.apply_transform(catalog, behavior_catalog, event.behavior)

    def _image_set_exists(self, image_set: str) -> bool:
        return bool(image_set) and (self.collection / "img" / image_set / "conf" / "actions.xml").is_file()


class SpriteLayerWindow(Gtk.ApplicationWindow):
    def __init__(
        self,
        app: Gtk.Application,
        collection: Path,
        catalog: ActionCatalog,
        monitor: MonitorInfo,
        fps: int,
        behavior_catalog: BehaviorCatalog | None = None,
        move_active_window: bool = False,
        world: PetWorld | None = None,
        debug_state: bool = False,
    ) -> None:
        super().__init__(application=app)
        self.collection = collection
        self.catalog = catalog
        self.monitor = monitor
        self.monitors = [monitor]
        self.cache = SurfaceCache(catalog.image_set_dir)
        self.sound_player = make_sound_player(catalog)
        self.runtime = make_runtime(catalog, monitor, behavior_catalog)
        self.fps = max(1, fps)
        self.ticks = 0
        self.world = world
        if self.world is not None:
            self.world.register(self.runtime)
        self.move_active_window = move_active_window
        self.debug_state = debug_state
        self.paused = False
        self.following_cursor = False
        self.transient = False
        self.active_window_info = sync_active_window(self.runtime, self.monitor)
        self.minimize_after_throw = False
        self._pending_window_move = None
        if not hasattr(app, "_neuro_hypr_window_originals"):
            app._neuro_hypr_window_originals = {}  # type: ignore[attr-defined]
        self.window_motion = WindowMotion(app._neuro_hypr_window_originals)  # type: ignore[attr-defined]
        self._input_region_key: tuple[int, int, int, int, int, bool] | None = None
        self._last_geometry: SpriteLayerGeometry | None = None
        self._last_visual_key = self._visual_key()
        self._closed = False

        self.set_title("neuro-hypr-shimeji")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_css_classes(["neuro-hypr-shimeji-window"])

        Gtk4LayerShell.init_for_window(self)
        Gtk4LayerShell.set_namespace(self, "neuro-hypr-shimeji")
        Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.OVERLAY)
        Gtk4LayerShell.set_exclusive_zone(self, -1)
        Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.NONE)
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.LEFT, True)
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.TOP, True)
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.RIGHT, False)
        Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.BOTTOM, False)
        self._select_gdk_monitor()

        self.area = Gtk.DrawingArea()
        self.area.set_draw_func(self._draw)
        self.area.set_can_target(True)
        self.set_child(self.area)
        self.menu_popover = Gtk.Popover()
        self.menu_popover.add_css_class("neuro-pet-menu")
        self.menu_popover.set_has_arrow(False)
        self.menu_popover.set_position(Gtk.PositionType.RIGHT)
        self.menu_popover.set_parent(self.area)

        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect("pressed", self._on_pressed)
        click.connect("released", self._on_released)
        self.area.add_controller(click)

        context_click = Gtk.GestureClick()
        context_click.set_button(3)
        context_click.connect("pressed", self._on_context_pressed)
        self.area.add_controller(context_click)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        self.area.add_controller(motion)

        self.connect("close-request", self._on_close_request)
        self.connect("realize", self._on_realize)
        self._apply_geometry()

    def _sync_monitors(self) -> None:
        try:
            monitors = load_monitors()
        except Exception:
            return
        if not monitors:
            return
        current = next((item for item in monitors if item.name == self.monitor.name), None)
        if current is not None and (current.rect != self.monitor.rect or current.reserved != self.monitor.reserved):
            self.runtime.anchor_x += current.x - self.monitor.x
            self.runtime.anchor_y += current.y - self.monitor.y
            area = current.global_work_area
            self.runtime.anchor_x = max(area.left, min(self.runtime.anchor_x, area.right - 1))
            self.runtime.anchor_y = max(area.top, min(self.runtime.anchor_y, area.bottom))
        self.monitors = monitors
        self.runtime.update_work_areas(tuple(item.global_work_area for item in monitors), desktop_rect(monitors))
        if not any(item.name == self.monitor.name for item in monitors):
            if self.runtime.pointer_active:
                self.runtime.pointer_up(self.runtime.cursor_x, self.runtime.cursor_y)
            destination = monitor_for_point(monitors, self.runtime.anchor_x, self.runtime.anchor_y)
            area = destination.global_work_area
            self.runtime.anchor_x = max(area.left, min(self.runtime.anchor_x, area.right - 1))
            self.runtime.anchor_y = max(area.top, min(self.runtime.anchor_y, area.bottom))
            self.runtime.start_action("Falling")
        self._sync_output()

    def _sync_output(self) -> None:
        destination = monitor_for_point(self.monitors, self.runtime.anchor_x, self.runtime.anchor_y - 1)
        # Rebinding a layer surface cancels its pointer grab; keep it until release.
        if self.runtime.dragging and destination.name != self.monitor.name:
            return
        changed = destination != self.monitor
        rebound = destination.name != self.monitor.name
        self.monitor = destination
        self.runtime.update_work_areas(tuple(item.global_work_area for item in self.monitors), desktop_rect(self.monitors))
        if changed:
            if rebound:
                self._select_gdk_monitor()
            self._last_geometry = None
            self._last_visual_key = None
            self._input_region_key = None

    def _sprite_local_rect(self, surface: cairo.ImageSurface) -> Rect:
        return self.monitor.to_local_rect(self.runtime.sprite_rect(surface.get_width(), surface.get_height()))

    def start(self) -> None:
        self.present()
        GLib.timeout_add(max(1, round(1000 / self.fps)), self._tick)

    def _select_gdk_monitor(self) -> None:
        display = Gdk.Display.get_default()
        if display is None:
            return
        monitors = display.get_monitors()
        for index in range(monitors.get_n_items()):
            monitor = monitors.get_item(index)
            connector = monitor.get_connector() if hasattr(monitor, "get_connector") else None
            if connector == self.monitor.name:
                Gtk4LayerShell.set_monitor(self, monitor)
                return

    def _current_surface(self) -> cairo.ImageSurface:
        return self.cache.get(self.runtime.frame, look_right=self.runtime.look_right)

    def _current_rect(self) -> "Rect":
        return self._current_geometry().window_rect

    def _current_geometry(self) -> SpriteLayerGeometry:
        surface = self._current_surface()
        sprite_rect = self._sprite_local_rect(surface)
        return clip_sprite_layer_geometry(sprite_rect, layer_output_rect(self))

    def _visual_key(self) -> tuple[Path, str, bool, Rect]:
        frame = self.runtime.frame
        surface = self.cache.get(frame, look_right=self.runtime.look_right)
        return (
            self.catalog.image_set_dir,
            frame.image_for_direction(look_right=self.runtime.look_right),
            frame.needs_horizontal_flip(look_right=self.runtime.look_right),
            self._sprite_local_rect(surface),
        )

    def _refresh_sprite(self, *, force: bool = False) -> None:
        visual_key = self._visual_key()
        if not force and visual_key == self._last_visual_key:
            return
        self._last_visual_key = visual_key
        self._apply_geometry()
        self.area.queue_draw()

    def _apply_geometry(self) -> None:
        surface = self._current_surface()
        sprite_rect = self._sprite_local_rect(surface)
        geometry = clip_sprite_layer_geometry(sprite_rect, layer_output_rect(self))
        previous_geometry = getattr(self, "_last_geometry", None)
        self._last_geometry = geometry
        if previous_geometry != geometry:
            self.set_default_size(geometry.window_rect.width, geometry.window_rect.height)
            self.area.set_content_width(geometry.window_rect.width)
            self.area.set_content_height(geometry.window_rect.height)
            Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.LEFT, geometry.window_rect.x)
            Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.TOP, geometry.window_rect.y)
            Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.RIGHT, 0)
            Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.BOTTOM, 0)
            self.queue_resize()
        self._apply_input_region(surface, geometry)

    def _apply_input_region(self, surface: cairo.ImageSurface, geometry: SpriteLayerGeometry) -> None:
        gdk_surface = self.get_surface()
        if gdk_surface is None or not hasattr(gdk_surface, "set_input_region"):
            return
        frame = self.runtime.frame
        mirror = frame.needs_horizontal_flip(look_right=self.runtime.look_right)
        key = (
            id(surface),
            geometry.draw_x,
            geometry.draw_y,
            geometry.window_rect.width,
            geometry.window_rect.height,
            mirror,
        )
        if getattr(self, "_input_region_key", None) == key:
            return
        self._input_region_key = key
        gdk_surface.set_input_region(
            sprite_input_region(surface, geometry, mirror=mirror)
        )

    def _on_realize(self, _window: Gtk.Window) -> None:
        self._apply_geometry()
        self.get_frame_clock().connect("after-paint", self._after_paint)

    def _after_paint(self, _clock) -> None:
        pending = self._pending_window_move
        self._pending_window_move = None
        if pending is not None and self.runtime.action.params.get("Class", "").rsplit(".", 1)[-1] in {"FallWithIE", "WalkWithIE"}:
            window, rect = pending
            if self.window_motion.target is not None and self.window_motion.target.address == window.address:
                try:
                    self.window_motion.move(window, rect, self.monitors)
                except Exception as error:
                    self.window_motion.release()
                    self.runtime.desired_active_window_rect = None
                    self.runtime.start_action("Fall" if "Fall" in self.runtime.catalog.actions else "Falling")
                    print(f"Window movement failed: {error}", file=sys.stderr)

    def _tick(self) -> bool:
        if self._closed:
            return False
        if self.paused:
            return True
        self.ticks += 1
        if environment_sync_due(self.ticks, fps=self.fps):
            self._sync_monitors()
            if not self.runtime.window_action_active:
                self.window_motion.release()
                self.runtime.desired_active_window_rect = None
            self.active_window_info = sync_active_window(self.runtime, self.monitor, self.window_motion)
            if not self.runtime.dragging:
                sync_cursor(self.runtime, self.monitor)
        sync_drag_cursor(self.runtime, self.monitor)
        if self.following_cursor:
            self.runtime.follow_cursor()
        if self.runtime.window_action_active and self.window_motion.target is None:
            self.window_motion.target = self.active_window_info
        was_throwing = self.runtime.action.params.get("Class", "").endswith(".ThrowIE")
        manager = getattr(self.get_application(), "_neuro_hypr_manager", None)
        self.runtime.advance(manager.window_speed if manager is not None else 1.5)
        self._sync_output()
        play_pending_sounds(self.runtime, self.sound_player)
        self._apply_pending_transforms()
        self._apply_pending_interactions()
        self._apply_pending_breeds()
        self._move_active_window_if_needed()
        if was_throwing and not self.runtime.action.params.get("Class", "").endswith(".ThrowIE") and self.minimize_after_throw:
            target = self.window_motion.target
            animation_disabled = self.window_motion.animation_disabled
            self.window_motion.release()
            self.minimize_after_throw = False
            window = next((item for item in load_windows() if target is not None and item.address == target.address), None)
            if window is not None:
                animate_minimize(window, manager, animation_disabled)
            self.runtime.desired_active_window_rect = None
            self.runtime.update_active_window_rect(None)
        if not self.runtime.window_action_active:
            self.window_motion.release()
            self.minimize_after_throw = False
        if close_if_self_destructed(self.runtime, self):
            return False
        if (
            self.runtime.ready_for_idle
            and not self.following_cursor
            and self.ticks % (self.fps * 3) == 0
        ):
            self.runtime.start_idle_action(rng=random)
        self._refresh_sprite()
        maybe_print_runtime_state(
            self.runtime,
            self._last_geometry.window_rect,
            ticks=self.ticks,
            fps=self.fps,
            enabled=self.debug_state,
        )
        return True

    def _apply_pending_transforms(self) -> None:
        for event in self.runtime.pop_transform_events():
            image_set = event.image_set if self._image_set_exists(event.image_set) else self.catalog.image_set_dir.name
            catalog, behavior_catalog = load_image_set(self.collection, image_set)
            self.catalog = catalog
            self.cache = SurfaceCache(catalog.image_set_dir)
            self.sound_player = make_sound_player(catalog)
            self.runtime.apply_transform(catalog, behavior_catalog, event.behavior)
            manager = getattr(self.get_application(), "_neuro_hypr_manager", None)
            if manager is not None:
                manager.changed()

    def _image_set_exists(self, image_set: str) -> bool:
        return bool(image_set) and (self.collection / "img" / image_set / "conf" / "actions.xml").is_file()

    def _apply_pending_interactions(self) -> None:
        for event in self.runtime.pop_interaction_events():
            apply_interaction_event(event)

    def _apply_pending_breeds(self) -> None:
        application = self.get_application()
        if application is None:
            self.runtime.pop_breed_events()
            return
        for event in self.runtime.pop_breed_events():
            image_set = event.image_set if self._image_set_exists(event.image_set) else self.catalog.image_set_dir.name
            catalog, behavior_catalog = load_image_set(self.collection, image_set)
            child = SpriteLayerWindow(
                application,
                self.collection,
                catalog,
                self.monitor,
                self.fps,
                behavior_catalog,
                move_active_window=self.move_active_window,
                world=self.world,
                debug_state=self.debug_state,
            )
            configure_runtime_from_breed(child.runtime, event)
            if child.runtime.window_action_active:
                child.active_window_info = self.active_window_info
                child.runtime.update_active_window_rect(self.runtime.active_window_rect)
            child._sync_monitors()
            child.transient = event.transient
            child._apply_geometry()
            remember_window(application, child, parent=self)
            child.start()

    def _on_close_request(self, _window: Gtk.Window) -> bool:
        self._closed = True
        self.window_motion.release()
        if self.world is not None:
            self.world.unregister(self.runtime)
        application = self.get_application()
        if application is not None:
            forget_window(application, self)
        return False

    def _on_context_pressed(self, _gesture: Gtk.GestureClick, _n_press: int, x: float, y: float) -> None:
        if self.runtime.dragging:
            return
        self._fill_context_menu()
        pointing_to = Gdk.Rectangle()
        pointing_to.x = int(x)
        pointing_to.y = int(y)
        pointing_to.width = 1
        pointing_to.height = 1
        self.menu_popover.set_pointing_to(pointing_to)
        self.menu_popover.popup()

    def _fill_context_menu(self) -> None:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        card.add_css_class("neuro-menu-card")
        card.set_size_request(232, -1)

        title = Gtk.Label(label=self.catalog.image_set_dir.name.upper(), xalign=0)
        title.add_css_class("neuro-menu-title")
        card.append(title)
        application = self.get_application()
        manager = getattr(application, "_neuro_hypr_manager", None)
        if manager is not None:
            manage = Gtk.Button(label="管理桌宠")
            manage.connect("clicked", lambda _button: application.activate_action("manage", None))
            card.append(manage)
            resummon = Gtk.Button(label="再召唤同款")
            resummon.connect("clicked", lambda _button: manager.resummon(self))
            card.append(resummon)
        section = Gtk.Label(label="动作", xalign=0)
        section.add_css_class("neuro-menu-section")
        card.append(section)

        action_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        names = self.runtime.available_manual_behaviors()
        for name in names:
            button = Gtk.Button()
            button.add_css_class("neuro-menu-action")
            label = Gtk.Label(label=manual_behavior_label(name), xalign=0)
            label.set_hexpand(True)
            button.set_child(label)
            button.set_tooltip_text(name)
            button.connect("clicked", self._on_manual_behavior, name)
            action_list.append(button)
        if not names:
            empty = Gtk.Label(label="当前没有可用动作", xalign=0)
            empty.add_css_class("neuro-menu-empty")
            action_list.append(empty)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_width(208)
        scroll.set_max_content_height(244)
        scroll.set_propagate_natural_height(True)
        scroll.set_child(action_list)
        card.append(scroll)

        card.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        if manager is not None:
            card.append(SplitControls(manager,
                lambda: (self.runtime.allow_split, self.runtime.split_probability),
                lambda enabled, probability: manager.set_pet_split(self, enabled, probability)))
        movement = Gtk.CheckButton(label="允许搬运和抛出悬浮窗口")
        movement.set_active(self.move_active_window)
        movement.connect("toggled", self._on_window_movement_toggled)
        card.append(movement)
        if self.window_motion.originals:
            restore = Gtk.Button(label="还原搬动的窗口")
            restore.add_css_class("neuro-menu-action")
            restore.connect("clicked", self._on_restore_windows)
            card.append(restore)
        if len(self.monitors) > 1:
            for monitor in self.monitors:
                if monitor.name == self.monitor.name:
                    continue
                transfer = Gtk.Button(label=f"移到 {monitor.name}")
                transfer.add_css_class("neuro-menu-action")
                transfer.connect("clicked", self._on_transfer_monitor, monitor.name)
                card.append(transfer)

        if self.world is not None:
            companions = [
                (image_set, label)
                for image_set, label, identities in COMPANION_CHOICES
                if self._image_set_exists(image_set) and not self.world.has_image_set(*identities)
            ]
            if companions:
                card.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
                companion_section = Gtk.Label(label="伙伴", xalign=0)
                companion_section.add_css_class("neuro-menu-section")
                card.append(companion_section)
                for image_set, label in companions:
                    button = Gtk.Button(label=label)
                    button.add_css_class("neuro-menu-action")
                    button.connect("clicked", self._on_summon_companion, image_set)
                    card.append(button)
        card.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        remove = Gtk.Button()
        remove.add_css_class("neuro-menu-remove")
        remove_label = Gtk.Label(label="移除这一只", xalign=0)
        remove_label.set_hexpand(True)
        remove.set_child(remove_label)
        remove.connect("clicked", self._on_remove_requested)
        card.append(remove)
        self.menu_popover.set_child(card)

    def _on_manual_behavior(self, _button: Gtk.Button, name: str) -> None:
        self.menu_popover.popdown()
        if self.runtime.start_manual_behavior(name, rng=random):
            self._refresh_sprite(force=True)

    def _on_remove_requested(self, _button: Gtk.Button) -> None:
        self.menu_popover.popdown()
        self.close()

    def _on_summon_companion(self, _button: Gtk.Button, image_set: str) -> None:
        self.menu_popover.popdown()
        application = self.get_application()
        if application is None or self.world is None or not self._image_set_exists(image_set):
            return
        identities = next(names for name, _label, names in COMPANION_CHOICES if name == image_set)
        if self.world.has_image_set(*identities):
            return
        catalog, behaviors = load_image_set(self.collection, image_set)
        companion = SpriteLayerWindow(
            application,
            self.collection,
            catalog,
            self.monitor,
            self.fps,
            behaviors,
            move_active_window=self.move_active_window,
            world=self.world,
            debug_state=self.debug_state,
        )
        offset = 160 if image_set == "Eviling" else -160
        work_area = self.monitor.global_work_area
        companion.runtime.anchor_x = max(work_area.left + 64, min(work_area.right - 64, self.runtime.anchor_x + offset))
        companion.runtime.anchor_y = work_area.bottom
        companion.runtime.start_action("Stand")
        companion._apply_geometry()
        remember_window(application, companion)
        companion.start()

    def _move_active_window_if_needed(self) -> None:
        rect = self.runtime.desired_active_window_rect
        if not self.move_active_window or self.active_window_info is None or rect is None:
            return
        try:
            action_class = self.runtime.action.params.get("Class", "").rsplit(".", 1)[-1]
            if action_class in {"FallWithIE", "WalkWithIE"}:
                moved = clamp_window_rect(rect, self.monitors)
                if self.active_window_info.floating:
                    self.runtime.anchor_x += moved.x - rect.x
                    self.runtime.anchor_y += moved.y - rect.y
                    # Dispatch after GTK commits the sprite frame, so the window cannot lead the pet by a frame.
                    self._pending_window_move = (self.active_window_info, moved)
            else:
                moved = self.window_motion.move(self.active_window_info, rect, self.monitors)
            if moved is not None:
                self.runtime.active_window_rect = moved
        except Exception as error:
            self.window_motion.release()
            self.runtime.desired_active_window_rect = None
            self.runtime.start_action("Fall" if "Fall" in self.runtime.catalog.actions else "Falling")
            print(f"Window movement failed: {error}", file=sys.stderr)

    def _on_window_movement_toggled(self, button: Gtk.CheckButton) -> None:
        self.move_active_window = button.get_active()
        if not self.move_active_window:
            self.window_motion.release()

    def _on_restore_windows(self, _button: Gtk.Button) -> None:
        self.menu_popover.popdown()
        application = self.get_application()
        manager = getattr(application, "_neuro_hypr_manager", None)
        if manager is not None:
            manager.restore_windows()
            return
        for window in application._neuro_hypr_shimeji_windows:  # type: ignore[attr-defined]
            window.runtime.start_action("Stand")
            window.runtime.desired_active_window_rect = None
            window.window_motion.release()
        self.window_motion.restore(load_windows(), self.monitors)

    def request_window_interaction(self, window: WindowInfo, *, throw: bool, minimize: bool = False) -> bool:
        if self.catalog.image_set_dir.name != "Tuteling" and not self.runtime.supports_window_interaction:
            return False
        actor = self
        if self.catalog.image_set_dir.name == "Tuteling":
            catalog, behaviors = load_image_set(self.collection, "Tuteling Cursor")
            actor = SpriteLayerWindow(self.get_application(), self.collection, catalog, self.monitor, self.fps,
                                      behaviors, move_active_window=True, world=self.world, debug_state=self.debug_state)
            actor.transient = True
            remember_window(self.get_application(), actor)
        monitors = load_monitors()
        monitor = monitor_for_point(monitors, window.x + window.width // 2, window.y + window.height // 2)
        actor.monitors = monitors
        if actor.monitor.name != monitor.name:
            actor.runtime.anchor_x = monitor.global_work_area.left + monitor.work_area.width // 2
            actor.runtime.anchor_y = monitor.global_work_area.bottom
        actor._sync_output()
        actor.window_motion.originals.setdefault(window.address, WindowPlacement(window.rect, window.floating, window.workspace_id, window.pinned))
        actor.window_motion.begin(window)
        if not window.floating:
            set_window_floating(window, True)
            window = next(item for item in load_windows() if item.address == window.address)
        max_width, max_height = monitor.work_area.width * 3 // 5, monitor.work_area.height * 3 // 5
        if window.width > max_width or window.height > max_height:
            resize_window(window, min(window.width, max_width), min(window.height, max_height))
            window = next(item for item in load_windows() if item.address == window.address)
        actor.active_window_info = window
        actor.move_active_window = True
        actor.window_motion.target = window
        actor.window_motion.last_rect = None
        actor.minimize_after_throw = minimize
        started = actor.runtime.start_window_interaction(window.rect, throw=throw, transient=actor.transient)
        actor._refresh_sprite(force=True)
        if actor is not self:
            actor.start()
        return started

    def _on_transfer_monitor(self, _button: Gtk.Button, name: str) -> None:
        self.menu_popover.popdown()
        monitor = next(item for item in self.monitors if item.name == name)
        area = monitor.global_work_area
        self.runtime.anchor_x = area.left + area.width // 2
        self.runtime.anchor_y = area.top + self.runtime.frame.anchor_y
        self.runtime.start_action("Falling")
        self._sync_output()
        self._refresh_sprite(force=True)

    def _screen_pos(self, x: float, y: float) -> tuple[int, int]:
        rect = self._last_geometry.window_rect
        return self.monitor.x + rect.x + int(x), self.monitor.y + rect.y + int(y)

    def _cursor_screen_pos(self, fallback_x: float, fallback_y: float) -> tuple[int, int]:
        try:
            cursor = cursor_pos()
            return cursor.x, cursor.y
        except Exception:
            return self._screen_pos(fallback_x, fallback_y)

    def _on_pressed(self, _gesture: Gtk.GestureClick, _n_press: int, x: float, y: float) -> None:
        if self.paused:
            return
        surface = self._current_surface()
        screen_x, screen_y = self._screen_pos(x, y)
        self.runtime.update_cursor_pos(screen_x, screen_y)
        if self.runtime.pointer_down(
            screen_x,
            screen_y,
            image_width=surface.get_width(),
            image_height=surface.get_height(),
        ):
            self._refresh_sprite(force=True)

    def _on_motion(self, _controller: Gtk.EventControllerMotion, x: float, y: float) -> None:
        if not self.runtime.pointer_active:
            return
        screen_x, screen_y = self._cursor_screen_pos(x, y)
        self.runtime.update_cursor_pos(screen_x, screen_y)
        if self.runtime.pointer_motion(screen_x, screen_y):
            self._refresh_sprite()

    def _on_released(self, _gesture: Gtk.GestureClick, _n_press: int, x: float, y: float) -> None:
        if not self.runtime.pointer_active:
            return
        screen_x, screen_y = self._cursor_screen_pos(x, y)
        self.runtime.update_cursor_pos(screen_x, screen_y)
        self.runtime.pointer_up(screen_x, screen_y)
        self._sync_output()
        self._refresh_sprite(force=True)

    def _draw(self, _area: Gtk.DrawingArea, cr: cairo.Context, _width: int, _height: int) -> None:
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        frame = self.runtime.frame
        surface = self._current_surface()
        geometry = clip_sprite_layer_geometry(
            self._sprite_local_rect(surface),
            layer_output_rect(self),
        )
        draw_surface(
            cr,
            surface,
            geometry.draw_x,
            geometry.draw_y,
            frame.needs_horizontal_flip(look_right=self.runtime.look_right),
        )


def install_css() -> None:
    provider = Gtk.CssProvider()
    provider.load_from_data(
        b"""
        .neuro-hypr-shimeji-window {
          background: transparent;
        }
        popover.neuro-pet-menu contents {
          background: rgba(24, 27, 41, 0.92);
          color: #f7f7fb;
          font-size: 80%;
          border: 1px solid rgba(255, 255, 255, 0.18);
          border-radius: 16px;
          box-shadow: 0 12px 32px rgba(0, 0, 0, 0.3);
        }
        .neuro-menu-card { padding: 10px; }
        .neuro-menu-title {
          color: #f6b8dc;
          font-size: 9.6px;
          font-weight: 800;
          letter-spacing: 2px;
        }
        .neuro-menu-section {
          color: rgba(255, 255, 255, 0.62);
          font-size: 8.8px;
        }
        .neuro-menu-card button {
          min-height: 24px;
          padding: 4px 8px;
          border: 0;
          border-radius: 9px;
          background: transparent;
          color: #f7f7fb;
          box-shadow: none;
        }
        .neuro-menu-card button:hover { color: #f6b8dc; }
        .neuro-menu-card spinbutton,
        .neuro-menu-card spinbutton text,
        .neuro-menu-card checkbutton check {
          background: transparent;
          box-shadow: none;
        }
        .neuro-menu-card spinbutton text {
          min-height: 24px;
          padding: 2px 4px;
        }
        .neuro-menu-card spinbutton button {
          min-height: 20px;
          min-width: 20px;
          padding: 2px;
        }
        .neuro-menu-remove { color: #ffb6c8; }
        .neuro-menu-remove:hover {
          color: #ff8ba5;
        }
        .neuro-menu-empty {
          padding: 9px;
          color: rgba(255, 255, 255, 0.62);
        }
        window.neuro-manager-popup {
          background: rgba(24, 27, 41, 0.97);
          background-image: none;
          color: #f7f7fb;
          border: 1px solid rgba(255, 255, 255, 0.18);
          border-radius: 14px;
        }
        .neuro-manager-popup button {
          background-image: none;
          background-color: rgba(255, 255, 255, 0.08);
          color: #f7f7fb;
          min-height: 28px;
          border-radius: 7px;
          border: 0;
          padding: 2px 9px;
        }
        .neuro-manager-popup button:hover,
        .neuro-manager-popup button:checked {
          background-color: rgba(248, 187, 220, 0.2);
        }
        .neuro-manager-popup button.suggested-action {
          background-color: #b96899;
          color: white;
        }
        .neuro-manager-popup button:disabled { opacity: 0.45; }
        """
    )
    display = Gdk.Display.get_default()
    if display is not None:
        Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Neuroling desktop pets natively on Hyprland/Wayland.")
    parser.add_argument("--collection", type=Path, default=default_collection())
    parser.add_argument("--image-set", action="append", help="Initial image set; repeat for multiple sets. Otherwise use the saved pending selection.")
    parser.add_argument("--manage", action="store_true", help="Open the pet manager.")
    parser.add_argument("--monitor", default="auto", help="Output name, auto (focused output), or all (one pet per output).")
    parser.add_argument("--fps", type=int, default=25)
    parser.add_argument("--duration", type=float, default=0, help="Exit after N seconds; useful for smoke tests.")
    parser.add_argument("--dry-run", action="store_true", help="Print the startup mode without creating a Wayland window.")
    parser.add_argument("--write-service", type=Path, help="Write a systemd user service file for this runtime and exit.")
    parser.add_argument("--install-user", action="store_true", help="Install the systemd user service for this runtime and exit.")
    parser.add_argument("--start", action="store_true", help="Restart the installed systemd user service after --install-user.")
    parser.add_argument("--python", type=Path, default=Path(sys.executable), help="Python interpreter path for generated services.")
    parser.add_argument(
        "--screen-cover",
        action="store_true",
        help="Use the old full-screen layer-shell prototype instead of the sprite-bounded layer.",
    )
    parser.add_argument(
        "--allow-screen-cover",
        action="store_true",
        help="Allow --screen-cover. This is intentionally separate because that mode can cover the desktop.",
    )
    parser.add_argument(
        "--move-active-window",
        action="store_true",
        help="Allow autonomous carry and throw actions to move floating windows. Manager actions can always move their selected target.",
    )
    parser.add_argument(
        "--debug-state",
        action="store_true",
        help="Print one runtime/layer state line per second to stdout for motion diagnostics.",
    )
    return parser.parse_args(argv)


def run_command(command: list[str]) -> None:
    subprocess.run(command, check=True)


def resolve_collection_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    collection = resolve_collection_path(args.collection)
    if args.write_service or args.install_user:
        if args.image_set:
            save_selection(preferences_path(), tuple(args.image_set))
        service_path = args.write_service or (Path.home() / ".config" / "systemd" / "user" / "neuro-hypr-pet-shimeji.service")
        write_shimeji_user_service(
            service_path,
            repo_root=REPO_ROOT,
            collection=collection,
            image_set=None,
            monitor=args.monitor,
            fps=args.fps,
            python=args.python,
            move_active_window=args.move_active_window,
        )
        print(f"Wrote service to {service_path}")
        if args.install_user:
            launcher = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "applications" / "neuro-hypr-pet.desktop"
            write_manager_desktop_entry(launcher, repo_root=REPO_ROOT, collection=collection, python=args.python)
            print(f"Wrote launcher to {launcher}")
            run_command(["systemctl", "--user", "daemon-reload"])
            run_command(["systemctl", "--user", "enable", "neuro-hypr-pet-shimeji.service"])
            if args.start:
                run_command(["systemctl", "--user", "restart", "neuro-hypr-pet-shimeji.service"])
        return 0
    if args.dry_run:
        print(f"mode={'screen-cover' if args.screen_cover else 'sprite-layer'}")
        print(f"monitor={args.monitor}")
        print(f"fps={args.fps}")
        print(f"move-active-window={'on' if args.move_active_window else 'off'}")
        print(f"debug-state={'on' if args.debug_state else 'off'}")
        return 0
    if args.screen_cover and not args.allow_screen_cover:
        print(
            "Refusing to start the experimental full-screen prototype without --allow-screen-cover. "
            "Use the sprite-bounded runtime or neuro-hypr-pet-shimeji.service for normal operation.",
            file=sys.stderr,
        )
        return 2
    app = Gtk.Application(application_id="dev.chesszyh.neuro-hypr-shimeji")

    def show_manager() -> None:
        manager = app._neuro_hypr_manager
        if not hasattr(app, "_neuro_hypr_manager_popup"):
            app._neuro_hypr_manager_popup = ManagerPopup(manager)
        app._neuro_hypr_manager_popup.show_manager()

    startup_error = 0

    def on_activate(application: Gtk.Application) -> None:
        nonlocal startup_error
        if hasattr(application, "_neuro_hypr_manager"):
            show_manager()
            return
        application.hold()
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        install_css()
        world = pet_world_for_application(application)
        try:
            manager = PetManager(application, collection, lambda name, monitor: create_window(application, name, monitor, world), monitor=args.monitor)
            if not manager.available:
                raise ValueError(f"No usable image sets in {collection}; import Neurolings v1.zip first.")
        except (OSError, ValueError) as error:
            print(str(error), file=sys.stderr)
            startup_error = 2
            application.quit()
            return
        if args.image_set:
            manager.set_selection(args.image_set)
        actions = {
            "manage": show_manager,
            "summon": manager.spawn_selected,
            "pause": lambda: manager.set_paused(not manager.paused),
            "follow": lambda: manager.set_following(not manager.following),
            "keep-one": manager.keep_one,
            "remove-all": manager.remove_all,
            "restore-windows": manager.restore_windows,
            "quit": application.quit,
        }
        for name, callback in actions.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _action, _parameter, callback=callback: callback())
            application.add_action(action)
        application._neuro_hypr_tray = PetTray(manager, show_manager)
        manager.spawn_selected()
        if args.manage:
            show_manager()
        if args.duration > 0:
            GLib.timeout_add(round(args.duration * 1000), application.quit)

    def create_window(application: Gtk.Application, name: str, monitor: MonitorInfo, world: PetWorld) -> Gtk.Window:
        catalog, behavior_catalog = load_image_set(collection, name)
        if args.screen_cover:
            window = ScreenCoverShimejiWindow(
                application,
                collection,
                catalog,
                monitor,
                args.fps,
                behavior_catalog,
                debug_state=args.debug_state,
            )
        else:
            window = SpriteLayerWindow(
                application,
                collection,
                catalog,
                monitor,
                args.fps,
                behavior_catalog,
                move_active_window=args.move_active_window,
                world=world,
                debug_state=args.debug_state,
            )
        return window

    app.connect("activate", on_activate)
    def on_shutdown(application):
        if hasattr(application, "_neuro_hypr_manager"):
            application._neuro_hypr_manager.shutdown()
        if hasattr(application, "_neuro_hypr_tray"):
            application._neuro_hypr_tray.close()
    app.connect("shutdown", on_shutdown)
    return app.run([]) or startup_error


if __name__ == "__main__":
    raise SystemExit(main())
