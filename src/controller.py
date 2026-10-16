from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.desktop import MonitorInfo
from src.runtime import PetRuntime, PetWorld, RuntimeConfig
from src.shimeji_model import ActionCatalog, BehaviorCatalog, load_action_catalog, load_behavior_catalog
from src.sound import SoundPlayer


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


def play_pending_sounds(runtime: PetRuntime, player: SoundPlayer) -> None:
    for event in runtime.pop_sound_events():
        player.play(event)


def close_if_self_destructed(runtime: PetRuntime, window: Any) -> bool:
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


def pet_world_for_application(application: Any) -> PetWorld:
    world = getattr(application, "_neuro_hypr_shimeji_world", None)
    if world is None:
        world = PetWorld()
        application._neuro_hypr_shimeji_world = world  # type: ignore[attr-defined]
    return world


def remember_window(application: Any, window: Any, *, parent=None) -> None:
    manager = getattr(application, "_neuro_hypr_manager", None)
    if manager is not None:
        manager.register(window, parent=parent)
        return
    windows = getattr(application, "_neuro_hypr_shimeji_windows", None)
    if windows is None:
        windows = []
        application._neuro_hypr_shimeji_windows = windows  # type: ignore[attr-defined]
    windows.append(window)


def forget_window(application: Any, window: Any) -> None:
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


def image_set_for_event(collection: Path, requested: str, current: str) -> str:
    return requested if requested and (collection / "img" / requested / "conf/actions.xml").is_file() else current


def apply_pending_transforms(runtime: PetRuntime, collection: Path, on_catalog_changed) -> None:
    for event in runtime.pop_transform_events():
        name = image_set_for_event(collection, event.image_set, runtime.catalog.image_set_dir.name)
        catalog, behaviors = load_image_set(collection, name)
        runtime.apply_transform(catalog, behaviors, event.behavior)
        on_catalog_changed(catalog)


def apply_pending_interactions(runtime: PetRuntime) -> None:
    for event in runtime.pop_interaction_events():
        apply_interaction_event(event)


def apply_pending_breeds(runtime: PetRuntime, collection: Path, spawn) -> None:
    for event in runtime.pop_breed_events():
        name = image_set_for_event(collection, event.image_set, runtime.catalog.image_set_dir.name)
        catalog, behaviors = load_image_set(collection, name)
        spawn(event, catalog, behaviors)



class PetController:
    def __init__(self, application, collection, catalog, monitor, behaviors, *, desktop, view_factory, sound_factory, world, fps=25):
        self.application = application
        self.collection = collection
        self.catalog = catalog
        self.monitor = monitor
        self.desktop = desktop
        self.runtime = make_runtime(catalog, monitor, behaviors)
        self.world = world
        world.register(self.runtime)
        self.fps = fps
        self.ticks = 0
        self.paused = False
        self.following_cursor = False
        self.transient = False
        self.closed = False
        self._sound_factory = sound_factory
        self.sound_player = sound_factory(catalog)
        self.view = view_factory(self)
        self.window_motion = desktop.WindowMotion(application._neuro_hypr_window_originals)
        self.minimize_after_throw = False
        self.move_active_window = False
        self.monitors = [monitor]
        self._tick_credit = 0.0
        self._previous_anchor = (self.runtime.anchor_x, self.runtime.anchor_y)
        self.display_anchor = self._previous_anchor

    def start(self):
        self.reset_display()
        self.view.show()
        self.view.render()

    def reset_display(self):
        self._tick_credit = 0.0
        self._previous_anchor = (self.runtime.anchor_x, self.runtime.anchor_y)
        self.display_anchor = self._previous_anchor

    def sync_environment(self, monitors, windows):
        from src.desktop import desktop_rect, monitor_for_point

        previous = self.monitor
        self.monitors = monitors
        current = next((monitor for monitor in monitors if monitor.name == previous.name), None)
        if current is not None and current.rect != previous.rect:
            self.runtime.anchor_x += current.x - previous.x
            self.runtime.anchor_y += current.y - previous.y
        if current is None:
            if self.runtime.pointer_active:
                self.runtime.pointer_up(self.runtime.cursor_x, self.runtime.cursor_y)
            destination = monitor_for_point(monitors, self.runtime.anchor_x, self.runtime.anchor_y)
            area = destination.global_work_area
            self.runtime.anchor_x = max(area.left, min(self.runtime.anchor_x, area.right - 1))
            self.runtime.anchor_y = max(area.top, min(self.runtime.anchor_y, area.bottom))
            self.runtime.start_action('Falling' if 'Falling' in self.catalog.actions else 'Stand')
        self.monitor = monitor_for_point(monitors, self.runtime.anchor_x, self.runtime.anchor_y - 1)
        self.runtime.update_work_areas(tuple(monitor.global_work_area for monitor in monitors), desktop_rect(monitors))
        target = self.window_motion.target
        rects = tuple(window.rect for window in windows)
        if target is not None and self.runtime.window_action_active:
            # The carried target owns this action; nearby platforms must not replace it or project its anchor.
            self.runtime.window_rects = rects
            self.runtime.floating_window_rects = rects
        else:
            self.runtime.update_window_rects(list(rects), floating_count=len(windows))
        if target is not None:
            live = next((window for window in windows if window.address == target.address), None)
            if live is None:
                self.cancel_window_interaction()

    def step(self, cursor, *, elapsed=None):
        if self.closed:
            return
        self.runtime.update_cursor_pos(cursor.x, cursor.y)
        if self.paused:
            self._tick_credit = 0.0
            self.display_anchor = (self.runtime.anchor_x, self.runtime.anchor_y)
            return
        if elapsed is None:
            self._step_runtime()
            self.display_anchor = (self.runtime.anchor_x, self.runtime.anchor_y)
        else:
            speed = self.application._neuro_hypr_manager.fall_speed if self.runtime._is_fall_action() else 1.0
            self._tick_credit += min(.12, max(0, elapsed)) * 25 * speed
            while self._tick_credit >= 1 - 1e-9:
                self._tick_credit = max(0, self._tick_credit - 1)
                self._previous_anchor = (self.runtime.anchor_x, self.runtime.anchor_y)
                self._step_runtime()
                if self.closed:
                    return
            alpha = self._tick_credit
            self.display_anchor = tuple(old + (new - old) * alpha for old, new in
                                        zip(self._previous_anchor, (self.runtime.anchor_x, self.runtime.anchor_y)))
        if not self.closed:
            self.view.render()

    def _step_runtime(self):
        self.ticks += 1
        if self.following_cursor:
            self.runtime.follow_cursor()
        was_throwing = self.runtime.action.params.get('Class', '').endswith('.ThrowIE')
        self.runtime.advance(self.application._neuro_hypr_manager.window_speed)
        play_pending_sounds(self.runtime, self.sound_player)
        apply_pending_transforms(self.runtime, self.collection, self._catalog_changed)
        apply_pending_interactions(self.runtime)
        apply_pending_breeds(self.runtime, self.collection, self._breed)
        target = self.window_motion.target
        desired = self.runtime.desired_active_window_rect
        if target is not None and desired is not None:
            try:
                actual = self.window_motion.move(target, desired, self.monitors)
                if actual is not None:
                    self.runtime.active_window_rect = actual
                    action_class = self.runtime.action.params.get('Class', '').rsplit('.', 1)[-1]
                    if action_class in {'FallWithIE', 'WalkWithIE'}:
                        self.runtime.anchor_x += actual.x - desired.x
                        self.runtime.anchor_y += actual.y - desired.y
            except Exception:
                self.cancel_window_interaction()
                raise
        if was_throwing and not self.runtime.action.params.get('Class', '').endswith('.ThrowIE') and self.minimize_after_throw:
            if target is not None:
                cancel = self.desktop.backend.minimize(target.address)
                self.application._neuro_hypr_manager.minimizations[target.address] = cancel
            self.minimize_after_throw = False
        if not self.runtime.window_action_active:
            self.window_motion.finish()
        if close_if_self_destructed(self.runtime, self):
            return
        if self.runtime.ready_for_idle and not self.following_cursor and self.ticks % 75 == 0:
            self.runtime.start_idle_action()

    def _catalog_changed(self, catalog):
        self.catalog = catalog
        self.sound_player = self._sound_factory(catalog)
        self.view.clear_images()
        self.application._neuro_hypr_manager.changed()

    def _breed(self, event, catalog, behaviors):
        child = self.application.create_pet(catalog.image_set_dir.name, self.monitor)
        configure_runtime_from_breed(child.runtime, event)
        child.transient = event.transient
        remember_window(self.application, child, parent=self)
        child.start()

    def cancel_window_interaction(self):
        self.window_motion.release()
        self.runtime.desired_active_window_rect = None
        self.minimize_after_throw = False
        self.runtime.start_action('Falling' if 'Falling' in self.catalog.actions else 'Stand')

    def summon_companion(self, name):
        companion = self.application._neuro_hypr_manager.spawn(name, self.monitor)
        area = self.monitor.global_work_area
        companion.runtime.anchor_x = max(area.left + 64, min(area.right - 64, self.runtime.anchor_x + 96))
        companion.runtime.anchor_y = area.bottom
        companion.runtime.start_action('Stand')
        companion.view.render()
        return companion

    def request_window_interaction(self, window, *, throw, minimize=False):
        actor = self
        if self.catalog.image_set_dir.name == 'Tuteling':
            actor = self.application.create_pet('Tuteling Cursor', self.monitor)
            actor.transient = True
        if not actor.runtime.supports_window_interaction:
            if actor is not self:
                actor.close()
            return False
        try:
            actor.window_motion.begin(window)
            actor.minimize_after_throw = minimize
            actor.move_active_window = True
            started = actor.runtime.start_window_interaction(window.rect, throw=throw, transient=actor.transient)
            if actor is not self:
                remember_window(self.application, actor, parent=self)
                actor.start()
            return started
        except Exception:
            actor.window_motion.release()
            if actor is not self:
                actor.close()
            raise

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.runtime.pointer_active:
            self.runtime.pointer_up(self.runtime.cursor_x, self.runtime.cursor_y)
        self.world.unregister(self.runtime)
        self.window_motion.release()
        self.view.close()
        forget_window(self.application, self)


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

