from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, replace
from typing import Any

from neuro_hypr_pet.shimeji_model import ActionCatalog, ActionDef, ActionReference, ActionStep, AnimationDef, BehaviorCatalog, PoseFrame
from neuro_hypr_pet.sound import SoundEvent


FLOOR_IDLE_ACTIONS = (
    "SitDown",
    "LieDown",
    "SitWhileDanglingLegs",
    "HeartHeartHeart",
    "Wink",
    "WalkAlongWorkAreaFloor",
    "RunAlongWorkAreaFloor",
    "CrawlAlongWorkAreaFloor",
    "WalkLeftAlongFloorAndSit",
    "WalkRightAlongFloorAndSit",
    "WalkLeftAndSit",
    "WalkRightAndSit",
    "Walk",
)

ACTIVE_WINDOW_TOP_IDLE_ACTIONS = (
    "WalkAlongIECeiling",
    "RunAlongIECeiling",
    "CrawlAlongIECeiling",
    "SitOnTheLeftEdgeOfIE",
    "SitOnTheRightEdgeOfIE",
    "WalkLeftAlongIEAndSit",
    "WalkRightAlongIEAndSit",
    "JumpFromLeftEdgeOfIE",
    "JumpFromRightEdgeOfIE",
)

WORK_AREA_WALL_IDLE_ACTIONS = ("ClimbAlongWall", "ClimbHalfwayAlongWall", "HoldOntoWall")
WORK_AREA_CEILING_IDLE_ACTIONS = ("ClimbAlongCeiling", "HoldOntoCeiling")
INSTANT_ACTIONS = {"Look", "Offset"}
REFERENCE_CONTROL_PARAMS = {"TargetX", "TargetY", "InitialVX", "InitialVY", "Duration", "LookRight", "Condition"}
MIN_RANDOM_FLOOR_TARGET_DISTANCE = 96
EDGE_TOLERANCE = 3
SCREEN_CEILING_MAX_TICKS = 250
PASSIVE_ACTION_MAX_TICKS = 150
CURSOR_FOLLOW_DISTANCE = 32
PARTNER_BEHAVIOR_REQUIREMENTS = {
    ("Neuron", "HugEvil"): ("Eviling",),
    ("Neuron", "HurlEvil"): ("Eviling",),
    ("Neuron", "NoticeFallingTutel"): ("Tuteling", "Vedaling"),
    ("Eviling", "HugNeuro"): ("Neuron", "Neuroling"),
    ("Eviling", "NoticeFallingTutel"): ("Tuteling", "Vedaling"),
}


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def left(self) -> int:
        return self.x

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def top(self) -> int:
        return self.y

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom

    def intersects(self, other: "Rect") -> bool:
        return self.left < other.right and other.left < self.right and self.top < other.bottom and other.top < self.bottom


@dataclass(frozen=True)
class RuntimeConfig:
    work_area: Rect
    start_x: int
    start_y: int
    work_areas: tuple[Rect, ...] = ()
    screen_area: Rect | None = None


@dataclass(frozen=True)
class TransformEvent:
    image_set: str
    behavior: str


@dataclass(frozen=True)
class SelfDestructEvent:
    action_name: str


@dataclass(frozen=True)
class BreedEvent:
    image_set: str
    behavior: str
    anchor_x: int
    anchor_y: int
    look_right: bool
    transient: bool


@dataclass(frozen=True)
class InteractionEvent:
    target: "PetRuntime"
    target_behavior: str
    target_look: bool
    source_look_right: bool


class PetRuntime:
    def __init__(self, catalog: ActionCatalog, config: RuntimeConfig, behavior_catalog: BehaviorCatalog | None = None) -> None:
        self.catalog = catalog
        self.config = config
        self.behavior_catalog = behavior_catalog
        self.anchor_x = config.start_x
        self.anchor_y = config.start_y
        self.look_right = False
        self.action_name = "Falling" if "Falling" in catalog.actions and config.start_y < config.work_area.bottom else "Stand"
        self.frame_index = 0
        self.frame_time = 0
        self.target_x: int | None = None
        self.target_y: int | None = None
        self.velocity_x = 0.0
        self.velocity_y = 0.0
        self.dragging = False
        self._pending_hotspot: tuple[str, int, int, int, int] | None = None
        self._drag_offset_x = 0
        self._drag_offset_y = 0
        self._last_pointer_x: int | None = None
        self._last_pointer_y: int | None = None
        self._pointer_dx = 0
        self._pointer_dy = 0
        self._pointer_velocity_samples: list[tuple[int, int]] = []
        self._drag_foot_x = float(config.start_x)
        self._drag_foot_dx = 0.0
        self.cursor_x = config.start_x
        self.cursor_y = config.start_y
        self.cursor_dx = 0
        self.cursor_dy = 0
        self.active_window_rect: Rect | None = None
        self.window_rects: tuple[Rect, ...] = ()
        self.floating_window_rects: tuple[Rect, ...] = ()
        self.desired_active_window_rect: Rect | None = None
        self._auto_edge_climb = False
        self._screen_ceiling_ticks = 0
        self._sequence_queue: list[ActionStep] = []
        self._sequence_loop_steps: list[ActionStep] | None = None
        self._action_ticks_remaining: int | None = None
        self._action_elapsed_ticks = 0
        self._fall_from_throw = False
        self._fall_mod_x = 0.0
        self._fall_mod_y = 0.0
        self._animation_cache_key: tuple[Any, ...] | None = None
        self._animation_cache: AnimationDef | None = None
        self._turning = False
        self._turn_ticks = 0
        self._sound_events: list[SoundEvent] = []
        self._transform_events: list[TransformEvent] = []
        self._transform_emitted = False
        self._self_destruct_events: list[SelfDestructEvent] = []
        self._self_destruct_emitted = False
        self._breed_events: list[BreedEvent] = []
        self.allow_split = True
        self._breed_emitted = False
        self._interaction_events: list[InteractionEvent] = []
        self.world: PetWorld | None = None
        self._scan_target: PetRuntime | None = None
        self._behavior_name: str | None = None
        self._window_tick_credit = 0.0

    def advance(self, window_speed: float = 1.0) -> None:
        if not self.window_action_active:
            self._window_tick_credit = 0.0
            self.tick()
            return
        self._window_tick_credit += window_speed
        while self._window_tick_credit >= 1 and self.window_action_active:
            self._window_tick_credit -= 1
            self.tick()

    def update_work_areas(self, work_areas: tuple[Rect, ...], screen_area: Rect) -> None:
        self.config = replace(self.config, work_areas=work_areas, screen_area=screen_area)
        self._cross_work_area(self.anchor_x, self.anchor_y)

    def _cross_work_area(self, x: float, y: float) -> bool:
        for area in self.config.work_areas:
            if area.left <= x < area.right and area.top <= y <= area.bottom:
                if area != self.config.work_area:
                    self.config = replace(self.config, work_area=area)
                    return True
                return False
        return False

    @property
    def window_action_active(self) -> bool:
        for step in [self.action, *self._sequence_queue]:
            action = self.catalog.actions.get(step.name) if isinstance(step, ActionReference) else step
            if action is not None and action.params.get("Class", "").rsplit(".", 1)[-1] in {"FallWithIE", "WalkWithIE", "ThrowIE"}:
                return True
        return False

    @property
    def ready_for_idle(self) -> bool:
        return (
            not self.pointer_active and self.action_name == "Stand"
            and self._action_ticks_remaining is None and not self._sequence_queue
        )

    @property
    def supports_window_interaction(self) -> bool:
        classes = {action.params.get("Class", "").rsplit(".", 1)[-1] for action in self.catalog.actions.values()}
        return {"Jump", "FallWithIE", "WalkWithIE", "ThrowIE"} <= classes

    def start_window_interaction(self, window: Rect, *, throw: bool, transient: bool = False) -> bool:
        classes = {action.params.get("Class", "").rsplit(".", 1)[-1]: action for action in self.catalog.actions.values()}
        if not self.supports_window_interaction:
            return False
        area = self.config.work_area
        rightward = area.right - window.right >= window.left - area.left
        fall, walk = classes["FallWithIE"], classes["WalkWithIE"]
        offset_x, offset_y = self._active_window_action_offset(fall)
        pickup_x = window.left + offset_x if rightward else window.right - offset_x
        room = area.right - window.right if rightward else window.left - area.left
        distance = min(240, max(0, room - 80))
        target_x = pickup_x + distance * (1 if rightward else -1)
        self.update_active_window_rect(window)
        self._behavior_name = None
        self._sequence_loop_steps = None
        self._sequence_queue = [
            ActionReference(classes["Jump"].name, {"TargetX": str(pickup_x), "TargetY": str(window.bottom - offset_y)}),
            ActionReference("Look", {"LookRight": self._bool_literal(rightward)}),
            ActionReference(fall.name, {"LookRight": self._bool_literal(rightward)}),
            ActionReference(walk.name, {"TargetX": str(target_x)}),
        ]
        if throw:
            self._sequence_queue.append(ActionReference(classes["ThrowIE"].name, {}))
        if transient and "SelfDestruct" in self.catalog.actions:
            self._sequence_queue.append(ActionReference("SelfDestruct", {}))
        self._continue_sequence("Stand")
        return True

    @property
    def action(self) -> ActionDef:
        return self.catalog.actions[self.action_name]

    @property
    def frame(self) -> PoseFrame:
        frames = self._current_frames()
        return frames[self.frame_index % len(frames)]

    def _current_frames(self) -> tuple[PoseFrame, ...]:
        animation = self._current_animation()
        if animation is not None:
            return animation.frames
        return self.action.frames

    def _current_animation(self) -> AnimationDef | None:
        animations = self.action.animations
        if not animations:
            return None
        cache_key = (
            self.action_name,
            self.anchor_x,
            self.anchor_y,
            self.target_x,
            self.target_y,
            self.cursor_x,
            self.cursor_y,
            self.cursor_dx,
            self.cursor_dy,
            self.look_right,
            self._turning,
            round(self._drag_foot_x, 3),
            round(self._drag_foot_dx, 3),
            self.active_window_rect,
        )
        if self._animation_cache_key == cache_key:
            return self._animation_cache
        for animation in animations:
            if self._uses_turn_animations() and animation.is_turn != self._turning:
                continue
            if self._animation_is_effective(animation):
                self._animation_cache_key = cache_key
                self._animation_cache = animation
                return animation
        self._animation_cache_key = cache_key
        self._animation_cache = animations[-1]
        return self._animation_cache

    def _animation_is_effective(self, animation: AnimationDef) -> bool:
        if not animation.condition:
            return True
        return self._resolve_bool_expression(animation.condition)

    def _uses_turn_animations(self) -> bool:
        if not any(animation.is_turn for animation in self.action.animations):
            return False
        action_class = self.action.params.get("Class", "")
        return (
            self._is_move_action(self.action)
            or self._is_scan_move_action(self.action)
            or self._is_scan_interact_action()
            or action_class.endswith(".WalkWithIE")
        )

    def start_action(
        self,
        name: str,
        *,
        look_right: bool | None = None,
        target_x: int | None = None,
        target_y: int | None = None,
        auto_edge_climb: bool | None = None,
        duration: int | None = None,
    ) -> None:
        self._start_action(
            name,
            look_right=look_right,
            target_x=target_x,
            target_y=target_y,
            auto_edge_climb=auto_edge_climb,
            duration=duration,
            behavior_name=None,
        )

    def _start_behavior(
        self,
        name: str,
        *,
        action_name: str | None = None,
        look_right: bool | None = None,
        target_x: int | None = None,
        target_y: int | None = None,
        duration: int | None = None,
    ) -> None:
        if action_name is None and self.behavior_catalog is not None:
            behavior = self.behavior_catalog.behaviors.get(name)
            if behavior is not None:
                action_name = behavior.action_name
        self._start_action(
            action_name or name,
            look_right=look_right,
            target_x=target_x,
            target_y=target_y,
            duration=duration,
            behavior_name=name,
        )

    def _start_action(
        self,
        name: str,
        *,
        look_right: bool | None = None,
        target_x: int | None = None,
        target_y: int | None = None,
        auto_edge_climb: bool | None = None,
        duration: int | None = None,
        behavior_name: str | None = None,
    ) -> None:
        if not self.allow_split and self._is_split_action(name):
            name = "Stand"
        action = self.catalog.actions.get(name)
        if action is not None and self._is_complex_action(action):
            self._start_complex_action(action, behavior_name=behavior_name)
            return
        self._sequence_queue = []
        self._sequence_loop_steps = None
        self._start_direct_action(
            name,
            look_right=look_right,
            target_x=target_x,
            target_y=target_y,
            auto_edge_climb=auto_edge_climb,
            duration=duration,
            behavior_name=behavior_name,
        )

    def _start_direct_action(
        self,
        name: str,
        *,
        look_right: bool | None = None,
        target_x: int | None = None,
        target_y: int | None = None,
        auto_edge_climb: bool | None = None,
        duration: int | None = None,
        behavior_name: str | None = None,
    ) -> None:
        if name not in self.catalog.actions:
            name = "Stand"
        previous_look_right = self.look_right
        self._behavior_name = behavior_name
        self.action_name = name
        self.frame_index = 0
        self.frame_time = 0
        self._action_elapsed_ticks = 0
        self.target_x = target_x
        self.target_y = target_y
        self._turning = False
        self._turn_ticks = 0
        self._transform_emitted = False
        self._self_destruct_emitted = False
        self._breed_emitted = False
        self._animation_cache_key = None
        self._animation_cache = None
        self._scan_target = None
        if look_right is None and target_x is not None and self._is_floor_motion_action(name):
            look_right = target_x > self.anchor_x
        if auto_edge_climb is not None:
            self._auto_edge_climb = auto_edge_climb
        else:
            self._auto_edge_climb = name in {"GrabWall", "GrabCeiling"}
        if look_right is not None:
            self.look_right = look_right
        if self._is_floor_scan_move_action() and self.target_x is None:
            self._update_scan_move_target()
        if self._is_floor_scan_move_action() and self.target_x is None and self.world is None:
            self.target_x = self._fallback_floor_scan_move_target()
            self.look_right = self.target_x > self.anchor_x
        if self._is_scan_jump_action() and self.target_x is None:
            self._update_scan_affordance_target()
        if self._is_scan_interact_action() and self.target_x is None:
            self._update_scan_affordance_target()
        if self._uses_turn_animations() and self.target_x is not None and self.look_right != previous_look_right:
            self._turning = True
        if duration is None and self._is_dragged_action():
            duration = 250
        if duration is None and self._is_regist_action():
            duration = self._action_frame_duration(name)
        if duration is None and self.action.kind == "Animate":
            duration = self._action_frame_duration(name)
        if duration is None and (
            self._is_transform_action()
            or self._is_self_destruct_action()
            or self._is_breed_action()
            or self._is_interact_action()
        ):
            duration = self._action_frame_duration(name)
        if self.action.kind == "Stay" and name != "Stand":
            duration = min(duration, PASSIVE_ACTION_MAX_TICKS) if duration is not None else PASSIVE_ACTION_MAX_TICKS
        self._action_ticks_remaining = duration
        if self._apply_instant_action(self.action):
            self._finish_action("Stand")
            return
        if self._is_fall_action():
            self.velocity_x = 0.0
            self.velocity_y = 0.0
            self._fall_mod_x = 0.0
            self._fall_mod_y = 0.0
            self._fall_from_throw = False

    def _is_complex_action(self, action: ActionDef) -> bool:
        return bool(action.references and not action.frames and action.kind in {"Sequence", "Select"})

    def _start_complex_action(self, action: ActionDef, *, behavior_name: str | None = None) -> None:
        self._behavior_name = behavior_name
        self._sequence_queue = []
        self._sequence_loop_steps = None
        if not self._step_is_effective(action):
            self.start_action("Stand")
            return
        if action.kind == "Select":
            selected = self._select_action_step(action)
            if selected is not None:
                self._sequence_queue.append(selected)
        else:
            self._sequence_queue.extend(action.references)
            if action.loop:
                self._sequence_loop_steps = list(action.references)
        self._continue_sequence("Stand")

    def _continue_sequence(self, default_action: str, **default_kwargs) -> None:
        restarted_loop = False
        while True:
            while self._sequence_queue:
                step = self._sequence_queue.pop(0)
                if not self._step_is_effective(step):
                    continue
                if isinstance(step, ActionReference):
                    if self._start_action_reference(step):
                        return
                    continue
                if step.kind == "Select":
                    selected = self._select_action_step(step)
                    if selected is not None:
                        self._sequence_queue.insert(0, selected)
                    continue
                if self._is_complex_action(step):
                    self._sequence_queue = list(step.references) + self._sequence_queue
                    continue
                self._start_direct_action(step.name, behavior_name=self._behavior_name)
                return
            if self._sequence_loop_steps is not None and not restarted_loop:
                self._sequence_queue = list(self._sequence_loop_steps)
                restarted_loop = True
                continue
            break
        if self._finish_behavior_if_needed():
            return
        self.start_action(default_action, **default_kwargs)

    def _select_action_step(self, action: ActionDef) -> ActionStep | None:
        for step in action.references:
            if self._step_is_effective(step):
                return step
        return None

    def _step_is_effective(self, step: ActionStep) -> bool:
        condition = step.params.get("Condition")
        return True if condition is None else self._resolve_bool_expression(condition)

    def _start_action_reference(self, reference: ActionReference) -> bool:
        if not self._step_is_effective(reference):
            return False
        if self._apply_instant_reference(reference):
            return False
        referenced_action = self.catalog.actions.get(reference.name)
        if referenced_action is not None and self._is_complex_action(referenced_action):
            if not self._step_is_effective(referenced_action):
                return False
            if referenced_action.kind == "Select":
                selected = self._select_action_step(referenced_action)
                if selected is not None:
                    self._sequence_queue.insert(0, selected)
            else:
                self._sequence_queue = list(referenced_action.references) + self._sequence_queue
            return False
        local_params = self._resolve_reference_local_params(reference)
        target_x = self._resolve_int_param(reference.params.get("TargetX"), local_params=local_params)
        target_y = self._resolve_int_param(reference.params.get("TargetY"), local_params=local_params)
        target_x = self._retarget_near_random_floor_reference(reference, target_x)
        if self._floor_motion_reference_already_reached(reference.name, target_x):
            return False
        initial_vx = self._resolve_int_param(reference.params.get("InitialVX"), local_params=local_params)
        initial_vy = self._resolve_int_param(reference.params.get("InitialVY"), local_params=local_params)
        duration = self._resolve_int_param(reference.params.get("Duration"), local_params=local_params)
        look_right = self._resolve_bool_param(reference.params.get("LookRight"), local_params=local_params)
        if duration is None:
            duration = self._default_reference_duration(reference.name)
        if look_right is None and target_x is not None and self._is_floor_motion_action(reference.name):
            look_right = target_x > self.anchor_x
        self._start_direct_action(
            reference.name,
            look_right=look_right,
            target_x=target_x,
            target_y=target_y,
            duration=duration,
            behavior_name=self._behavior_name,
        )
        if initial_vx is not None:
            self.velocity_x = float(initial_vx)
        if initial_vy is not None:
            self.velocity_y = float(initial_vy)
        return True

    def _resolve_reference_local_params(self, reference: ActionReference) -> dict[str, str]:
        local_params: dict[str, str] = {}
        for key, value in reference.params.items():
            if key in REFERENCE_CONTROL_PARAMS:
                continue
            resolved = self._resolve_int_param(value, local_params=local_params)
            if resolved is not None:
                local_params[key] = str(resolved)
        return local_params

    def _retarget_near_random_floor_reference(self, reference: ActionReference, target_x: int | None) -> int | None:
        target_expression = reference.params.get("TargetX", "")
        if target_x is None or "Math.random" not in target_expression:
            return target_x
        if "mascot.environment.cursor" in target_expression:
            return target_x
        if target_x != self.anchor_x:
            return target_x
        if not self._is_floor_motion_action(reference.name):
            return target_x
        return self._distant_floor_target_if_needed(target_x)

    def _floor_motion_reference_already_reached(self, name: str, target_x: int | None) -> bool:
        return target_x is not None and target_x == self.anchor_x and self._is_floor_motion_action(name)

    def _apply_instant_reference(self, reference: ActionReference) -> bool:
        if reference.name == "Offset":
            self.anchor_x += self._resolve_int_param(reference.params.get("X")) or 0
            self.anchor_y += self._resolve_int_param(reference.params.get("Y")) or 0
            return True
        if reference.name == "Look":
            look_right = self._resolve_bool_param(reference.params.get("LookRight"))
            self.look_right = (not self.look_right) if look_right is None else look_right
            return True
        return False

    def _apply_instant_action(self, action: ActionDef) -> bool:
        action_class = action.params.get("Class", "")
        if action_class.endswith(".Offset"):
            self.anchor_x += self._resolve_int_param(action.params.get("X")) or 0
            self.anchor_y += self._resolve_int_param(action.params.get("Y")) or 0
            return True
        if action_class.endswith(".Look"):
            look_right = self._resolve_bool_param(action.params.get("LookRight"))
            self.look_right = (not self.look_right) if look_right is None else look_right
            return True
        return False

    def _finish_action(self, default_action: str, **default_kwargs) -> None:
        if self._sequence_queue or self._sequence_loop_steps is not None:
            self._continue_sequence(default_action, **default_kwargs)
            return
        if self._finish_behavior_if_needed():
            return
        self.start_action(default_action, **default_kwargs)

    def _finish_behavior_if_needed(self) -> bool:
        behavior_name = self._behavior_name
        if behavior_name is not None:
            next_behavior = self._choose_next_behavior(behavior_name)
            if next_behavior is not None:
                next_name, next_action_name = next_behavior
                self._start_behavior(next_name, action_name=next_action_name)
                return True
        return False

    def _expression_replacements(self, random_value: str, local_params: dict[str, str] | None = None) -> dict[str, str]:
        window = self.active_window_rect
        work_area = self.config.work_area
        screen = self.config.screen_area or work_area
        total_count = self.world.total_count() if self.world is not None else 1
        replacements = {
            "mascot.environment.workArea.left": str(work_area.left),
            "mascot.environment.workArea.right": str(work_area.right),
            "mascot.environment.workArea.top": str(work_area.top),
            "mascot.environment.workArea.bottom": str(work_area.bottom),
            "mascot.environment.workArea.width": str(work_area.width),
            "mascot.environment.workArea.height": str(work_area.height),
            "mascot.environment.screen.left": str(screen.left),
            "mascot.environment.screen.right": str(screen.right),
            "mascot.environment.screen.top": str(screen.top),
            "mascot.environment.screen.bottom": str(screen.bottom),
            "mascot.environment.screen.width": str(screen.width),
            "mascot.environment.screen.height": str(screen.height),
            "mascot.environment.floor.isOn(mascot.anchor)": self._bool_literal(self._is_floor_anchor()),
            "mascot.environment.ceiling.isOn(mascot.anchor)": self._bool_literal(self._is_ceiling_anchor()),
            "mascot.environment.wall.isOn(mascot.anchor)": self._bool_literal(self._is_wall_anchor()),
            "mascot.environment.workArea.bottomBorder.isOn(mascot.anchor)": self._bool_literal(self.work_area_edge(tolerance=EDGE_TOLERANCE) == "bottom"),
            "mascot.environment.workArea.topBorder.isOn(mascot.anchor)": self._bool_literal(self.work_area_edge(tolerance=EDGE_TOLERANCE) == "top"),
            "mascot.environment.workArea.leftBorder.isOn(mascot.anchor)": self._bool_literal(self.work_area_edge(tolerance=EDGE_TOLERANCE) == "left"),
            "mascot.environment.workArea.rightBorder.isOn(mascot.anchor)": self._bool_literal(self.work_area_edge(tolerance=EDGE_TOLERANCE) == "right"),
            "mascot.environment.activeIE.visible": self._bool_literal(window is not None),
            "mascot.anchor.x": str(self.anchor_x),
            "mascot.anchor.y": str(self.anchor_y),
            "mascot.environment.cursor.x": str(self.cursor_x),
            "mascot.environment.cursor.y": str(self.cursor_y),
            "mascot.environment.cursor.dx": str(self.cursor_dx),
            "mascot.environment.cursor.dy": str(self.cursor_dy),
            "mascot.lookRight": "1" if self.look_right else "0",
            "mascot.totalCount": str(total_count),
            "TargetX": str(self.target_x if self.target_x is not None else self.anchor_x),
            "TargetY": str(self.target_y if self.target_y is not None else self.anchor_y),
            "target.anchor.x": str(self.target_x if self.target_x is not None else self.anchor_x),
            "target.anchor.y": str(self.target_y if self.target_y is not None else self.anchor_y),
            "FootX": str(self._drag_foot_x),
            "FootDX": str(self._drag_foot_dx),
            "FootY": str(self.anchor_y),
            "Math.random()": random_value,
            "Math.random": random_value,
            "Math.abs": "abs",
            "Math.min": "min",
            "Math.max": "max",
        }
        if window is not None:
            replacements.update(
                {
                    "mascot.environment.activeIE.left": str(window.left),
                    "mascot.environment.activeIE.right": str(window.right),
                    "mascot.environment.activeIE.top": str(window.top),
                    "mascot.environment.activeIE.bottom": str(window.bottom),
                    "mascot.environment.activeIE.width": str(window.width),
                    "mascot.environment.activeIE.height": str(window.height),
                    "mascot.environment.activeIE.topBorder.isOn(mascot.anchor)": self._bool_literal(self.active_window_edge(tolerance=EDGE_TOLERANCE) == "top"),
                    "mascot.environment.activeIE.bottomBorder.isOn(mascot.anchor)": self._bool_literal(self.active_window_edge(tolerance=EDGE_TOLERANCE) == "bottom"),
                    "mascot.environment.activeIE.leftBorder.isOn(mascot.anchor)": self._bool_literal(self.active_window_edge(tolerance=EDGE_TOLERANCE) == "left"),
                    "mascot.environment.activeIE.rightBorder.isOn(mascot.anchor)": self._bool_literal(self.active_window_edge(tolerance=EDGE_TOLERANCE) == "right"),
                }
            )
        if local_params:
            replacements.update(local_params)
        return replacements

    @staticmethod
    def _bool_literal(value: bool) -> str:
        return "True" if value else "False"

    def _substitute_expression(
        self,
        expression: str,
        random_value: str,
        local_params: dict[str, str] | None = None,
    ) -> str:
        substituted = expression
        replacements = self._expression_replacements(random_value, local_params=local_params)
        for key in sorted(replacements, key=len, reverse=True):
            replacement = replacements[key]
            substituted = substituted.replace(key, replacement)
        return substituted

    def _resolve_int_param(self, value: str | None, *, local_params: dict[str, str] | None = None) -> int | None:
        if value is None:
            return None
        stripped = value.strip()
        if stripped.startswith("${") and stripped.endswith("}"):
            stripped = stripped[2:-1]
        elif stripped.startswith("#{") and stripped.endswith("}"):
            stripped = stripped[2:-1]
        stripped = self._normalize_expression_delimiters(stripped)
        try:
            return int(float(stripped))
        except ValueError:
            pass
        ternary = self._split_ternary(stripped)
        if ternary is not None:
            condition, true_expression, false_expression = ternary
            stripped = true_expression if self._resolve_bool_expression(condition, local_params=local_params) else false_expression
        random_value = str(random.random())
        expression = self._substitute_expression(stripped, random_value, local_params=local_params)
        try:
            return int(float(eval(expression, {"__builtins__": {}}, {"abs": abs, "min": min, "max": max})))
        except Exception:
            return None

    def _resolve_bool_param(self, value: str | None, *, local_params: dict[str, str] | None = None) -> bool | None:
        if value is None:
            return None
        stripped = value.strip()
        if stripped.startswith("${") and stripped.endswith("}"):
            stripped = stripped[2:-1]
        elif stripped.startswith("#{") and stripped.endswith("}"):
            stripped = stripped[2:-1]
        lowered = stripped.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        return self._resolve_bool_expression(stripped, local_params=local_params)

    def _resolve_bool_expression(self, value: str, *, local_params: dict[str, str] | None = None) -> bool:
        stripped = value.strip()
        if stripped.startswith("${") and stripped.endswith("}"):
            stripped = stripped[2:-1]
        elif stripped.startswith("#{") and stripped.endswith("}"):
            stripped = stripped[2:-1]
        stripped = self._normalize_expression_delimiters(stripped)
        lowered = stripped.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        if stripped == "mascot.lookRight":
            return self.look_right
        random_value = str(random.random())
        expression = self._substitute_expression(stripped, random_value, local_params=local_params)
        expression = expression.replace("&&", " and ").replace("||", " or ")
        expression = re.sub(r"!(?!=)", " not ", expression)
        expression = re.sub(r"\btrue\b", "True", expression)
        expression = re.sub(r"\bfalse\b", "False", expression)
        expression = " ".join(expression.split())
        try:
            return bool(eval(expression, {"__builtins__": {}}, {"abs": abs, "min": min, "max": max}))
        except Exception:
            pass
        for operator in ("<=", ">=", "==", "!=", "<", ">"):
            left, found, right = stripped.partition(operator)
            if not found:
                continue
            left_number = self._resolve_int_param(left, local_params=local_params)
            right_number = self._resolve_int_param(right, local_params=local_params)
            if left_number is None or right_number is None:
                return False
            if operator == "<":
                return left_number < right_number
            if operator == ">":
                return left_number > right_number
            if operator == "<=":
                return left_number <= right_number
            if operator == ">=":
                return left_number >= right_number
            if operator == "==":
                return left_number == right_number
            if operator == "!=":
                return left_number != right_number
        number = self._resolve_int_param(stripped, local_params=local_params)
        if number is not None:
            return bool(number)
        return False

    @staticmethod
    def _normalize_expression_delimiters(expression: str) -> str:
        return expression.replace("#{", "(").replace("${", "(").replace("}", ")")

    def _split_ternary(self, expression: str) -> tuple[str, str, str] | None:
        question_index = expression.find("?")
        if question_index < 0:
            return None
        depth = 0
        for index in range(question_index + 1, len(expression)):
            char = expression[index]
            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth = max(0, depth - 1)
            elif char == ":" and depth == 0:
                return (
                    expression[:question_index].strip(),
                    expression[question_index + 1 : index].strip(),
                    expression[index + 1 :].strip(),
                )
        return None

    def _default_reference_duration(self, name: str) -> int | None:
        action = self.catalog.actions.get(name)
        if action is None:
            return None
        if self._is_dragged_action_def(action):
            return 250
        if action.kind != "Animate" and not self._is_interact_action_def(action) and not self._is_regist_action_def(action):
            return None
        return self._action_frame_duration(name)

    def _action_frame_duration(self, name: str) -> int:
        action = self.catalog.actions[name]
        if name == self.action_name:
            return max(1, sum(frame.duration for frame in self._current_frames()))
        return max(1, sum(frame.duration for frame in action.frames))

    def tick(self) -> None:
        if self._pending_hotspot is not None:
            return
        if self.dragging:
            self._tick_dragging()
            return
        if self.action.border_type == "Ceiling" and self._work_area_ceiling_edge(tolerance=EDGE_TOLERANCE) == "top":
            self._screen_ceiling_ticks += 1
            if self._screen_ceiling_ticks > SCREEN_CEILING_MAX_TICKS:
                self._screen_ceiling_ticks = 0
                if "FallFromCeiling" in self.catalog.actions:
                    self.start_action("FallFromCeiling")
                else:
                    self.anchor_y = self.config.work_area.top + 1
                    self.start_action("Falling")
                return
        else:
            self._screen_ceiling_ticks = 0
        if self.action.border_type == "Floor":
            self._snap_to_work_area_floor_if_near()
        if not self._is_fall_action() and self._is_unsupported():
            self.start_action("Falling")
        if self._is_fall_with_ie_action():
            self._tick_fall_with_ie()
        elif self._is_walk_with_ie_action():
            self._tick_walk_with_ie()
        elif self._is_throw_ie_action():
            self._tick_throw_ie()
        elif self._is_fall_action():
            self._tick_falling()
        elif self._is_scan_jump_action():
            self._tick_scan_jump()
        elif self._is_jump_action():
            self._tick_jump()
        elif self._is_move_action(self.action) or self._is_floor_scan_move_action():
            self._tick_move()
        elif self._is_scan_interact_action():
            self._tick_scan_interact()
        else:
            if self._maybe_start_edge_climb():
                return
            self._tick_timed_action()

    def update_active_window_rect(self, rect: Rect | None) -> None:
        self.update_window_rects([rect] if rect is not None else [], floating_count=0)

    def update_window_rects(self, rects: list[Rect], *, floating_count: int | None = None) -> None:
        previous = self.active_window_rect
        self.window_rects = tuple(rects)
        self.floating_window_rects = tuple(rects[:floating_count]) if floating_count is not None else self.window_rects
        if previous in rects and self._anchor_touches_window(previous):
            selected = previous
        else:
            selected = min(rects, key=self._window_distance_from_anchor) if rects else None
        if previous is not None and selected is not None and previous.intersects(selected):
            self._project_active_window_border(previous, selected)
        self.active_window_rect = selected
        if selected is None:
            self.desired_active_window_rect = None

    def _anchor_touches_window(self, window: Rect) -> bool:
        x, y = self.anchor_x, self.anchor_y
        return (
            (window.left <= x <= window.right and y in {window.top, window.bottom})
            or (window.top <= y <= window.bottom and x in {window.left, window.right})
        )

    def _window_distance_from_anchor(self, window: Rect) -> int:
        dx = max(window.left - self.anchor_x, 0, self.anchor_x - window.right)
        dy = max(window.top - self.anchor_y, 0, self.anchor_y - window.bottom)
        return dx * dx + dy * dy

    def _project_active_window_border(self, previous: Rect, current: Rect) -> None:
        border_type = self.action.border_type
        if border_type == "Floor" and previous.left <= self.anchor_x <= previous.right and self.anchor_y == previous.top:
            self._project_floor_ceiling_border(previous, current, previous.top, current.top)
        elif (
            border_type == "Ceiling"
            and previous.left <= self.anchor_x <= previous.right
            and self.anchor_y == previous.bottom
        ):
            self._project_floor_ceiling_border(previous, current, previous.bottom, current.bottom)
        elif border_type == "Wall" and previous.top <= self.anchor_y <= previous.bottom:
            if self.anchor_x == previous.left:
                self._project_wall_border(previous, current, previous.left, current.left)
            elif self.anchor_x == previous.right:
                self._project_wall_border(previous, current, previous.right, current.right)

    def _project_floor_ceiling_border(self, previous: Rect, current: Rect, previous_y: int, current_y: int) -> None:
        if previous.width == 0:
            return
        new_x = int(((self.anchor_x - previous.left) * current.width / previous.width) + current.left)
        new_y = self.anchor_y + (current_y - previous_y)
        if abs(new_x - self.anchor_x) >= 80 or new_y - self.anchor_y > 20 or new_y - self.anchor_y < -80:
            return
        self.anchor_x = new_x
        self.anchor_y = new_y

    def _project_wall_border(self, previous: Rect, current: Rect, previous_x: int, current_x: int) -> None:
        if previous.height == 0:
            return
        new_x = self.anchor_x + (current_x - previous_x)
        new_y = int(((self.anchor_y - previous.top) * current.height / previous.height) + current.top)
        if abs(new_x - self.anchor_x) >= 80 or abs(new_y - self.anchor_y) >= 80:
            return
        self.anchor_x = new_x
        self.anchor_y = new_y

    def update_cursor_pos(self, x: int, y: int) -> None:
        self.cursor_dx = x - self.cursor_x
        self.cursor_dy = y - self.cursor_y
        self.cursor_x = x
        self.cursor_y = y

    def follow_cursor(self) -> None:
        if self.pointer_active or self.window_action_active:
            return
        if not self._is_floor_move_action("Dash"):
            return
        distance = self.cursor_x - self.anchor_x
        if self._is_floor_anchor() and abs(distance) <= CURSOR_FOLLOW_DISTANCE:
            if not self.ready_for_idle:
                self.start_action("Stand")
            if distance:
                self.look_right = distance > 0
        elif self._is_floor_move_action(self.action_name):
            self.target_x = self.cursor_x
        elif self.ready_for_idle:
            self.start_action("ChaseMouse")

    def _is_floor_anchor(self) -> bool:
        return self._is_near_work_area_floor() or self._is_on_active_window_top()

    def _is_near_work_area_floor(self) -> bool:
        return self.work_area_edge(tolerance=EDGE_TOLERANCE) == "bottom"

    def _snap_to_work_area_floor_if_near(self) -> bool:
        if not self._is_near_work_area_floor():
            return False
        self.anchor_y = self.config.work_area.bottom
        return True

    def _is_wall_anchor(self) -> bool:
        return self._work_area_wall_edge(tolerance=EDGE_TOLERANCE) in {"left", "right"} or self.active_window_edge(tolerance=EDGE_TOLERANCE) in {"left", "right"}

    def _is_ceiling_anchor(self) -> bool:
        return self._work_area_ceiling_edge(tolerance=EDGE_TOLERANCE) == "top" or self.active_window_edge(tolerance=EDGE_TOLERANCE) == "bottom"

    def active_window_edge(self, *, tolerance: int = 0) -> str:
        x = self.anchor_x
        y = self.anchor_y
        for window in self._candidate_windows():
            inside_x = window.left - tolerance <= x <= window.right + tolerance
            inside_y = window.top - tolerance <= y <= window.bottom + tolerance
            if inside_x and abs(y - window.top) <= tolerance:
                edge = "top"
            elif inside_x and abs(y - window.bottom) <= tolerance:
                edge = "bottom"
            elif inside_y and abs(x - window.left) <= tolerance:
                edge = "left"
            elif inside_y and abs(x - window.right) <= tolerance:
                edge = "right"
            else:
                continue
            self.active_window_rect = window
            return edge
        return "none"

    def _candidate_windows(self) -> tuple[Rect, ...]:
        selected = self.active_window_rect
        if selected is None:
            return self.window_rects
        return (selected, *(window for window in self.window_rects if window != selected))

    def sprite_rect(self, image_width: int, image_height: int) -> Rect:
        frame = self.frame
        if self.look_right:
            x = self.anchor_x - (image_width - frame.anchor_x)
        else:
            x = self.anchor_x - frame.anchor_x
        return Rect(x, self.anchor_y - frame.anchor_y, image_width, image_height)

    @property
    def pointer_active(self) -> bool:
        return self.dragging or self._pending_hotspot is not None

    def pointer_down(self, x: int, y: int, *, image_width: int, image_height: int) -> bool:
        if not self.sprite_rect(image_width, image_height).contains(x, y):
            return False
        hotspot_behavior = self._hotspot_behavior_at(x, y, image_width=image_width, image_height=image_height)
        if hotspot_behavior is not None and hotspot_behavior in self.catalog.actions:
            if self._is_current_action_draggable():
                self._pending_hotspot = (hotspot_behavior, x, y, image_width, image_height)
                return True
            self.dragging = False
            self._last_pointer_x = None
            self._last_pointer_y = None
            self._pointer_dx = 0
            self._pointer_dy = 0
            self._pointer_velocity_samples = []
            self.velocity_x = 0.0
            self.velocity_y = 0.0
            self.start_action(hotspot_behavior)
            return True
        if not self._is_current_action_draggable():
            return True
        self._begin_drag(x, y, image_width=image_width, image_height=image_height)
        return True

    def _begin_drag(self, x: int, y: int, *, image_width: int, image_height: int) -> None:
        self.dragging = True
        self._drag_offset_x = x - self.anchor_x
        self._drag_offset_y = y - self.anchor_y
        self._last_pointer_x = x
        self._last_pointer_y = y
        self._pointer_dx = 0
        self._pointer_dy = 0
        self._pointer_velocity_samples = []
        self._drag_foot_x = float(x)
        self._drag_foot_dx = 0.0
        self.velocity_x = 0.0
        self.velocity_y = 0.0
        self.start_action(self._initial_drag_action_name())
        if self._is_dragged_action():
            offset_x, offset_y = self._dragged_anchor_offset(image_width, image_height)
            self._drag_offset_x = -offset_x
            self._drag_offset_y = -offset_y

    def _hotspot_behavior_at(self, x: int, y: int, *, image_width: int, image_height: int) -> str | None:
        rect = self.sprite_rect(image_width, image_height)
        local_x = x - rect.x
        local_y = y - rect.y
        for hotspot in self.frame.hotspots:
            if hotspot.behavior and hotspot.contains(local_x, local_y, image_width=image_width, look_right=self.look_right):
                return hotspot.behavior
        return None

    def _is_current_action_draggable(self) -> bool:
        return self._resolve_bool_param(self.action.params.get("Draggable")) is not False

    def pointer_motion(self, x: int, y: int) -> bool:
        if self._pending_hotspot is not None:
            _behavior, press_x, press_y, image_width, image_height = self._pending_hotspot
            if (x - press_x) ** 2 + (y - press_y) ** 2 < 25:
                return False
            self._pending_hotspot = None
            self._begin_drag(press_x, press_y, image_width=image_width, image_height=image_height)
        if not self.dragging:
            return False
        if self._last_pointer_x is not None and self._last_pointer_y is not None:
            self._pointer_dx = x - self._last_pointer_x
            self._pointer_dy = y - self._last_pointer_y
            self._pointer_velocity_samples.append((self._pointer_dx, self._pointer_dy))
            self._pointer_velocity_samples = self._pointer_velocity_samples[-5:]
        self._last_pointer_x = x
        self._last_pointer_y = y
        self.anchor_x = x - self._drag_offset_x
        self.anchor_y = y - self._drag_offset_y
        if self._is_regist_action() and abs(self._pointer_dx) >= 5:
            self._restart_dragged_sequence(x)
        elif self._is_dragged_action():
            self._action_ticks_remaining = 250
            self._action_elapsed_ticks = 0
        return True

    def _restart_dragged_sequence(self, cursor_x: int) -> None:
        self._drag_foot_x = float(cursor_x)
        self._drag_foot_dx = 0.0
        self._animation_cache_key = None
        self._animation_cache = None
        self.start_action(self._initial_drag_action_name())

    def _initial_drag_action_name(self) -> str:
        if "Dragged" in self.catalog.actions:
            return "Dragged"
        if "Pinched" in self.catalog.actions:
            return "Pinched"
        return "Stand"

    def _dragged_anchor_offset(self, image_width: int, image_height: int) -> tuple[int, int]:
        offset_x = self._resolve_int_param(self.action.params.get("OffsetX"))
        offset_y = self._resolve_int_param(self.action.params.get("OffsetY"))
        if offset_x is None:
            offset_x = 0
        if offset_y is None:
            offset_y = 120
        if self.action.params.get("OffsetType", "ImageAnchor") == "Origin":
            offset_x = -offset_x + (image_width // 2)
            offset_y = -offset_y + (image_height // 2)
        return offset_x, offset_y

    def pointer_up(self, x: int, y: int) -> bool:
        if self._pending_hotspot is not None:
            behavior, _press_x, _press_y, _image_width, _image_height = self._pending_hotspot
            self._pending_hotspot = None
            self.start_action(behavior)
            return True
        if not self.dragging:
            return False
        throw_vx, throw_vy = self._smoothed_throw_velocity()
        self.dragging = False
        self._last_pointer_x = None
        self._last_pointer_y = None
        self.cursor_dx, self.cursor_dy = int(throw_vx), int(throw_vy)
        action = "Thrown" if "Thrown" in self.catalog.actions else "Falling"
        self.start_action(action if action in self.catalog.actions else "Stand")
        if self._is_fall_action():
            self.velocity_x = float(throw_vx)
            self.velocity_y = float(throw_vy)
            self._fall_from_throw = True
        return True

    def _smoothed_throw_velocity(self) -> tuple[float, float]:
        samples = self._pointer_velocity_samples or [(self._pointer_dx, self._pointer_dy)]
        weights = list(range(1, len(samples) + 1))
        total_weight = float(sum(weights))
        avg_x = sum(dx * weight for (dx, _dy), weight in zip(samples, weights)) / total_weight
        avg_y = sum(dy * weight for (_dx, dy), weight in zip(samples, weights)) / total_weight
        return self._clamp(avg_x * 0.9, -34.0, 34.0), self._clamp(avg_y * 0.9, -38.0, 38.0)

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    def _tick_frame(self) -> None:
        animation = self._current_animation()
        frames = self._current_frames()
        frame = frames[self.frame_index % len(frames)]
        if self.frame_time == 0 and frame.sound:
            self._sound_events.append(SoundEvent(frame.sound, frame.sound_volume))
        self.frame_time += 1
        if self.frame_time >= frame.duration:
            self.frame_time = 0
            self.frame_index = (self.frame_index + 1) % len(frames)
        if self._turning and animation is not None and animation.is_turn:
            self._turn_ticks += 1
            if self._turn_ticks >= self._animation_duration(animation):
                self._turning = False
                self._turn_ticks = 0
                self.frame_index = 0
                self.frame_time = 0
                self._animation_cache_key = None
                self._animation_cache = None

    def _tick_dragging(self) -> None:
        if self._is_dragged_action():
            self._tick_dragged_action()
            return
        if self._is_regist_action():
            self._tick_regist_action()
            return
        self._tick_frame()

    def _tick_dragged_action(self) -> None:
        self.look_right = False
        self._drag_foot_dx = (self._drag_foot_dx + ((self.cursor_x - self._drag_foot_x) * 0.1)) * 0.8
        self._drag_foot_x += self._drag_foot_dx
        self._animation_cache_key = None
        self._animation_cache = None
        self._tick_frame()
        if self._action_ticks_remaining is None:
            return
        if self._action_ticks_remaining == 1 and random.random() >= 0.1:
            self._action_ticks_remaining += 1
        self._action_ticks_remaining -= 1
        self._action_elapsed_ticks += 1
        if self._action_ticks_remaining <= 0:
            self._finish_action("Stand")

    def _tick_regist_action(self) -> None:
        self._tick_frame()
        self._action_elapsed_ticks += 1
        if self._action_elapsed_ticks >= self._action_frame_duration(self.action_name):
            if self.dragging:
                self.start_action(self._initial_drag_action_name())
                return
            self.start_action("Falling" if "Falling" in self.catalog.actions else "Stand")

    def pop_sound_events(self) -> list[SoundEvent]:
        events = self._sound_events
        self._sound_events = []
        return events

    @staticmethod
    def _animation_duration(animation: AnimationDef) -> int:
        return max(1, sum(frame.duration for frame in animation.frames))

    def _current_pose_delta(self) -> tuple[int, int]:
        frame = self.frame
        dx = -frame.velocity_x if self.look_right else frame.velocity_x
        return int(dx), int(frame.velocity_y)

    def _apply_current_pose_velocity(self) -> None:
        dx, dy = self._current_pose_delta()
        if not dx and not dy:
            return
        self.anchor_x += dx
        self.anchor_y += dy

    def _face_move_target_x(self) -> None:
        if self.target_x is None or self.anchor_x == self.target_x:
            return
        look_right = self.anchor_x < self.target_x
        if look_right == self.look_right:
            return
        if self._uses_turn_animations():
            self._turning = True
            self._turn_ticks = 0
            self.frame_index = 0
            self.frame_time = 0
            self._animation_cache_key = None
            self._animation_cache = None
        self.look_right = look_right

    def _tick_timed_action(self) -> None:
        if self._is_interact_action() and not self._has_overlapping_mascot_at_anchor():
            self._finish_action("Stand")
            return
        if self._action_ticks_remaining == 1:
            self._maybe_emit_transform_event()
            self._maybe_emit_self_destruct_event()
            self._maybe_emit_breed_events()
        self._apply_current_pose_velocity()
        self._tick_frame()
        if self._action_ticks_remaining is None:
            return
        self._action_ticks_remaining -= 1
        if self._action_ticks_remaining <= 0:
            if self._is_interact_action():
                behavior = self.action.params.get("Behavior", self.action.params.get("Behaviour", ""))
                self.start_action(behavior if behavior in self.catalog.actions else "Stand")
                return
            self._finish_action("Stand")

    def _maybe_emit_transform_event(self) -> None:
        if self._transform_emitted or not self._is_transform_action():
            return
        self._transform_emitted = True
        self._transform_events.append(
            TransformEvent(
                self.action.params.get("TransformMascot", ""),
                self.action.params.get("TransformBehavior", self.action.params.get("TransformBehaviour", "")),
            )
        )

    def pop_transform_events(self) -> list[TransformEvent]:
        events = self._transform_events
        self._transform_events = []
        return events

    def _maybe_emit_self_destruct_event(self) -> None:
        if self._self_destruct_emitted or not self._is_self_destruct_action():
            return
        self._self_destruct_emitted = True
        self._self_destruct_events.append(SelfDestructEvent(self.action_name))

    def pop_self_destruct_events(self) -> list[SelfDestructEvent]:
        events = self._self_destruct_events
        self._self_destruct_events = []
        return events

    def _maybe_emit_breed_events(self) -> None:
        if self._breed_emitted or not self._is_breed_action():
            return
        self._breed_emitted = True
        self._emit_breed_events()

    def _maybe_emit_interval_breed_events(self) -> None:
        if not self._is_interval_breed_action():
            return
        self._action_elapsed_ticks += 1
        interval = max(1, self._resolve_int_param(self.action.params.get("BornInterval")) or 1)
        if self._action_elapsed_ticks % interval == 0:
            self._emit_breed_events()

    def _emit_breed_events(self) -> None:
        params = self.action.params
        if not self.allow_split and params.get("BornBehavior", params.get("BornBehaviour")) == "Divided":
            return
        born_x = self._resolve_int_param(params.get("BornX")) or 0
        born_y = self._resolve_int_param(params.get("BornY")) or 0
        born_count = max(1, self._resolve_int_param(params.get("BornCount")) or 1)
        behavior = params.get("BornBehavior", params.get("BornBehaviour", ""))
        image_set = params.get("BornMascot") or self.catalog.image_set_dir.name
        transient = self._resolve_bool_param(params.get("BornTransient")) or False
        anchor_x = self.anchor_x - born_x if self.look_right else self.anchor_x + born_x
        anchor_y = self.anchor_y + born_y
        for _ in range(born_count):
            self._breed_events.append(
                BreedEvent(
                    image_set=image_set,
                    behavior=behavior,
                    anchor_x=anchor_x,
                    anchor_y=anchor_y,
                    look_right=self.look_right,
                    transient=transient,
                )
            )

    def pop_breed_events(self) -> list[BreedEvent]:
        events = self._breed_events
        self._breed_events = []
        return [event for event in events if self.allow_split or event.behavior != "Divided"]

    def pop_interaction_events(self) -> list[InteractionEvent]:
        events = self._interaction_events
        self._interaction_events = []
        return events

    def apply_transform(
        self,
        catalog: ActionCatalog,
        behavior_catalog: BehaviorCatalog | None,
        behavior_name: str,
    ) -> None:
        self.catalog = catalog
        self.behavior_catalog = behavior_catalog
        self._sequence_queue = []
        self._transform_events = []
        self._transform_emitted = False
        self.start_action(behavior_name if behavior_name in self.catalog.actions else "Stand")

    def _tick_move(self) -> None:
        if self.action.border_type == "Wall":
            self._tick_wall_move()
            return
        if self.action.border_type == "Ceiling":
            self._tick_ceiling_move()
            return
        self._tick_floor_move()

    def _is_jump_action(self) -> bool:
        action_class = self.action.params.get("Class", "")
        return self.action_name == "Jumping" or action_class.endswith(".Jump") or action_class.endswith(".BreedJump")

    def _is_floor_move_action(self, name: str) -> bool:
        action = self.catalog.actions.get(name)
        return action is not None and self._is_move_action(action) and action.border_type == "Floor"

    def _is_floor_motion_action(self, name: str) -> bool:
        action = self.catalog.actions.get(name)
        return action is not None and action.border_type == "Floor" and (self._is_move_action(action) or self._is_scan_move_action(action))

    def _is_floor_scan_move_action(self) -> bool:
        return self.action.border_type == "Floor" and self._is_scan_move_action(self.action)

    def _scan_move_needs_affordance_target(self) -> bool:
        return self.world is not None and bool(self.action.params.get("Affordance"))

    @staticmethod
    def _is_move_action(action: ActionDef) -> bool:
        action_class = action.params.get("Class", "")
        return action.kind in {"Move", "MoveWithTurn"} or action_class.endswith(".MoveWithTurn") or action_class.endswith(".BreedMove")

    @staticmethod
    def _is_scan_move_action(action: ActionDef) -> bool:
        return action.params.get("Class", "").endswith(".ScanMove")

    @staticmethod
    def _is_scan_jump_action_def(action: ActionDef) -> bool:
        return action.params.get("Class", "").endswith(".ScanJump")

    def _is_scan_jump_action(self) -> bool:
        return self._is_scan_jump_action_def(self.action)

    @staticmethod
    def _is_scan_interact_action_def(action: ActionDef) -> bool:
        return action.params.get("Class", "").endswith(".ScanInteract")

    def _is_scan_interact_action(self) -> bool:
        return self._is_scan_interact_action_def(self.action)

    def current_affordance(self) -> str | None:
        if self._is_scan_move_action(self.action) or self._is_scan_jump_action() or self._is_scan_interact_action():
            return None
        return self.action.params.get("Affordance")

    def _update_scan_move_target(self) -> bool:
        return self._update_scan_affordance_target()

    def _update_scan_affordance_target(self) -> bool:
        affordance = self.action.params.get("Affordance")
        if not affordance or self.world is None:
            return False
        if self._scan_target is None or self._scan_target.current_affordance() != affordance:
            self._scan_target = self.world.find_with_affordance(self, affordance)
        if self._scan_target is None:
            return False
        self.target_x = self._scan_target.anchor_x
        self.target_y = self._scan_target.anchor_y
        if self.anchor_x != self.target_x:
            self.look_right = self.anchor_x < self.target_x
        return True

    def _fallback_floor_scan_move_target(self) -> int:
        work_area = self.config.work_area
        left = work_area.left + 96
        right = work_area.right - 96
        if left > right:
            left = work_area.left
            right = work_area.right
        if self.look_right:
            return left if self.anchor_x >= right else right
        return right if self.anchor_x <= left else left

    def _is_fall_with_ie_action(self) -> bool:
        return self.action.params.get("Class", "").endswith(".FallWithIE")

    def _is_fall_action(self) -> bool:
        return self._is_fall_action_def(self.action)

    @staticmethod
    def _is_fall_action_def(action: ActionDef) -> bool:
        return action.params.get("Class", "").rsplit(".", 1)[-1] in {"Fall", "FallWithIE"}

    def _is_walk_with_ie_action(self) -> bool:
        return self.action.params.get("Class", "").endswith(".WalkWithIE")

    def _is_throw_ie_action(self) -> bool:
        return self.action.params.get("Class", "").endswith(".ThrowIE")

    def _is_transform_action(self) -> bool:
        return self.action.params.get("Class", "").endswith(".Transform")

    def _is_self_destruct_action(self) -> bool:
        return self.action.params.get("Class", "").endswith(".SelfDestruct")

    def _is_breed_action(self) -> bool:
        return self.action.params.get("Class", "").endswith(".Breed")

    def _is_interval_breed_action(self) -> bool:
        action_class = self.action.params.get("Class", "")
        return action_class.endswith(".BreedMove") or action_class.endswith(".BreedJump")

    def _is_interact_action(self) -> bool:
        return self._is_interact_action_def(self.action)

    @staticmethod
    def _is_interact_action_def(action: ActionDef) -> bool:
        action_class = action.params.get("Class", "")
        return action_class.endswith(".Interact")

    def _is_dragged_action(self) -> bool:
        return self._is_dragged_action_def(self.action)

    @staticmethod
    def _is_dragged_action_def(action: ActionDef) -> bool:
        return action.params.get("Class", "").endswith(".Dragged")

    def _is_regist_action(self) -> bool:
        return self._is_regist_action_def(self.action)

    @staticmethod
    def _is_regist_action_def(action: ActionDef) -> bool:
        return action.params.get("Class", "").endswith(".Regist")

    def _has_overlapping_mascot_at_anchor(self) -> bool:
        return self.world is not None and self.world.has_overlapping_anchor(self)

    def _active_window_action_offset(self, action: ActionDef | None = None) -> tuple[int, int]:
        action = self.action if action is None else action
        return int(float(action.params.get("IeOffsetX", "0"))), int(float(action.params.get("IeOffsetY", "0")))

    def _active_window_rect_for_anchor(self, action: ActionDef | None = None) -> Rect | None:
        window = self.active_window_rect
        if window is None:
            return None
        offset_x, offset_y = self._active_window_action_offset(action)
        bottom = self.anchor_y + offset_y
        if self.look_right:
            left = self.anchor_x - offset_x
        else:
            left = self.anchor_x + offset_x - window.width
        return Rect(left, bottom - window.height, window.width, window.height)

    def _active_window_is_attached_to_anchor(self, action: ActionDef | None = None) -> bool:
        window = self.active_window_rect
        if window is None:
            return False
        offset_x, offset_y = self._active_window_action_offset(action)
        if window.bottom != self.anchor_y + offset_y:
            return False
        if self.look_right:
            return window.left == self.anchor_x - offset_x
        return window.right == self.anchor_x + offset_x

    def _set_active_window_rect(self, rect: Rect) -> None:
        self.active_window_rect = rect
        self.desired_active_window_rect = rect

    def _lose_active_window_ground(self) -> None:
        self.desired_active_window_rect = None
        self.start_action("Falling" if "Falling" in self.catalog.actions else "Stand")

    @staticmethod
    def _java_round(value: float) -> int:
        return math.floor(value + 0.5)

    def _tick_jump(self) -> None:
        finished = self._tick_jump_motion()
        self._maybe_emit_interval_breed_events()
        if finished:
            self._finish_action("Stand")

    def _tick_scan_jump(self) -> None:
        if not self._update_scan_affordance_target():
            self.target_x = None
            self.target_y = None
            self._finish_action("Stand")
            return
        if self._tick_jump_motion():
            self._finish_scan_affordance_action()

    def _tick_scan_interact(self) -> None:
        if not self._update_scan_affordance_target():
            self.target_x = None
            self.target_y = None
            self._finish_action("Stand")
            return
        self._face_move_target_x()
        was_turning = self._turning
        self._tick_frame()
        if was_turning:
            return
        self._action_elapsed_ticks += 1
        if self._action_elapsed_ticks >= self._action_frame_duration(self.action_name):
            self._finish_scan_affordance_action()

    def _tick_jump_motion(self) -> bool:
        target_x = self.target_x if self.target_x is not None else self.anchor_x
        target_y = self.target_y if self.target_y is not None else self.anchor_y
        distance_x = target_x - self.anchor_x
        distance_y = (target_y - self.anchor_y) - (abs(distance_x) / 2.0)
        distance = math.sqrt((distance_x * distance_x) + (distance_y * distance_y))
        if distance == 0:
            return True
        velocity = float(self.action.params.get("VelocityParam", "20"))
        self.look_right = self.anchor_x < target_x
        step_x = int(velocity * distance_x / distance)
        step_y = int(velocity * distance_y / distance)
        if distance <= velocity:
            self.anchor_x = target_x
            self.anchor_y = target_y
            self._tick_frame()
            return True
        self.anchor_x += step_x
        self.anchor_y += step_y
        self._tick_frame()
        return False

    def _tick_floor_move(self) -> None:
        if self._is_floor_scan_move_action():
            if not self._update_scan_move_target() and self._scan_move_needs_affordance_target():
                self.target_x = None
                self.target_y = None
                self._finish_action("Stand")
                return
        self._face_move_target_x()
        dx, _dy = self._current_pose_delta()
        previous_x = self.anchor_x
        next_x = self.anchor_x + dx
        previous_area = self.config.work_area
        crossed = self._cross_work_area(next_x, self.anchor_y)
        reached_work_area_edge = False
        if self.target_x is not None:
            if self.look_right and next_x >= self.target_x:
                next_x = self.target_x
            elif not self.look_right and next_x <= self.target_x:
                next_x = self.target_x
        elif self.look_right:
            reached_work_area_edge = next_x >= self.config.work_area.right
        else:
            reached_work_area_edge = next_x <= self.config.work_area.left
        self.anchor_x = max(self.config.work_area.left, min(self.config.work_area.right, next_x))
        if self._is_on_active_window_top(self.anchor_x):
            self.anchor_y = self.active_window_rect.top  # type: ignore[union-attr]
        elif self._is_on_active_window_top(previous_x) and "Falling" in self.catalog.actions:
            self.start_action("Falling")
            return
        elif crossed and previous_area.bottom < self.config.work_area.bottom:
            self.start_action("Falling")
            self.anchor_x = next_x
            return
        else:
            self.anchor_y = self.config.work_area.bottom
        self._tick_frame()
        if not self._turning:
            self._maybe_emit_interval_breed_events()
        if self.target_x is not None and self.anchor_x == self.target_x:
            self._finish_floor_move()
        elif reached_work_area_edge:
            self._finish_floor_move()

    def _finish_floor_move(self) -> None:
        if not self._is_floor_scan_move_action() or self._scan_target is None:
            self._finish_action("Stand")
            return
        self._finish_scan_affordance_action()

    def _finish_scan_affordance_action(self) -> None:
        target = self._scan_target
        params = self.action.params
        behavior = params.get("Behavior", params.get("Behaviour", ""))
        target_behavior = params.get("TargetBehavior", params.get("TargetBehaviour", ""))
        target_look = self._resolve_bool_param(params.get("TargetLook")) or False
        if target is not None and target_behavior:
            self._interaction_events.append(
                InteractionEvent(
                    target=target,
                    target_behavior=target_behavior,
                    target_look=target_look,
                    source_look_right=self.look_right,
                )
            )
        self._scan_target = None
        self.start_action(behavior if behavior in self.catalog.actions else "Stand")

    def _tick_fall_with_ie(self) -> None:
        action = self.action
        if not self._active_window_is_attached_to_anchor(action):
            self._lose_active_window_ground()
            return
        self._tick_falling()
        rect = self._active_window_rect_for_anchor(action)
        if rect is not None:
            self._set_active_window_rect(rect)

    def _tick_walk_with_ie(self) -> None:
        if not self._active_window_is_attached_to_anchor():
            self._lose_active_window_ground()
            return
        self._face_move_target_x()
        dx, _dy = self._current_pose_delta()
        next_x = self.anchor_x + dx
        if self.target_x is not None:
            if self.look_right and next_x >= self.target_x:
                next_x = self.target_x
            elif not self.look_right and next_x <= self.target_x:
                next_x = self.target_x
        self.anchor_x = max(self.config.work_area.left, min(self.config.work_area.right, next_x))
        self.anchor_y = self.config.work_area.bottom
        rect = self._active_window_rect_for_anchor()
        if rect is not None:
            self._set_active_window_rect(rect)
        self._tick_frame()
        if self.target_x is not None and self.anchor_x == self.target_x:
            self._finish_action("Stand")

    def _tick_throw_ie(self) -> None:
        window = self.active_window_rect
        if window is None:
            self._finish_action("Stand")
            return
        initial_vx = int(float(self.action.params.get("InitialVX", "32")))
        initial_vy = int(float(self.action.params.get("InitialVY", "-10")))
        gravity = float(self.action.params.get("Gravity", "0.5"))
        direction = 1 if self.look_right else -1
        dx = direction * self._java_round(initial_vx)
        dy = initial_vy + math.trunc(self._action_elapsed_ticks * gravity)
        self._set_active_window_rect(Rect(window.x + dx, window.y + dy, window.width, window.height))
        self._action_elapsed_ticks += 1
        self._tick_frame()
        if self._action_elapsed_ticks >= self._action_frame_duration(self.action_name):
            self._finish_action("Stand")

    def _tick_wall_move(self) -> None:
        window = self.active_window_rect
        edge = self.active_window_edge(tolerance=EDGE_TOLERANCE)
        top = bottom = anchor_x = None
        if window is not None and edge in {"left", "right"}:
            top = window.top
            bottom = window.bottom
            anchor_x = window.left if edge == "left" else window.right
        else:
            edge = self._work_area_wall_edge(tolerance=EDGE_TOLERANCE)
            if edge in {"left", "right"}:
                top = self.config.work_area.top
                bottom = self.config.work_area.bottom
                anchor_x = self.config.work_area.left if edge == "left" else self.config.work_area.right
            else:
                self.start_action("Falling")
                return
        target_y = self.target_y if self.target_y is not None else top
        down = target_y > self.anchor_y
        _dx, dy = self._current_pose_delta()
        next_y = self.anchor_y + dy
        if down and next_y >= target_y:
            next_y = target_y
        elif not down and next_y <= target_y:
            next_y = target_y
        self.anchor_y = max(top, min(bottom, next_y))
        self.anchor_x = anchor_x
        self._tick_frame()
        if self.anchor_y == target_y:
            self._finish_action("GrabWall" if "GrabWall" in self.catalog.actions else "Stand", auto_edge_climb=False)

    def _tick_ceiling_move(self) -> None:
        window = self.active_window_rect
        edge = self.active_window_edge(tolerance=EDGE_TOLERANCE)
        left = right = anchor_y = None
        if window is not None and edge == "bottom":
            left = window.left
            right = window.right
            anchor_y = window.bottom
        else:
            edge = self._work_area_ceiling_edge(tolerance=EDGE_TOLERANCE)
            if edge == "top":
                left = self.config.work_area.left
                right = self.config.work_area.right
                anchor_y = self.config.work_area.top
            else:
                self.start_action("Falling")
                return
        self._face_move_target_x()
        target_x = self.target_x if self.target_x is not None else left
        dx, _dy = self._current_pose_delta()
        next_x = self.anchor_x + dx
        if self.look_right and next_x >= target_x:
            next_x = target_x
        elif not self.look_right and next_x <= target_x:
            next_x = target_x
        self.anchor_x = max(left, min(right, next_x))
        self.anchor_y = anchor_y
        self._tick_frame()
        if self.anchor_x == target_x:
            self._finish_action("GrabCeiling" if "GrabCeiling" in self.catalog.actions else "Stand", auto_edge_climb=False)

    def _tick_falling(self) -> None:
        previous_x = self.anchor_x
        previous_y = self.anchor_y
        gravity = float(self.action.params.get("Gravity", "2"))
        resistance_x = float(self.action.params.get("ResistanceX", self.action.params.get("RegistanceX", "0.05")))
        resistance_y = float(self.action.params.get("ResistanceY", self.action.params.get("RegistanceY", "0.1")))
        if self.velocity_x != 0:
            self.look_right = self.velocity_x > 0
        self.velocity_x = self.velocity_x - (self.velocity_x * resistance_x)
        self.velocity_y = self.velocity_y - (self.velocity_y * resistance_y) + gravity
        dx, dy = self._fall_step_delta()
        raw_next_x = self.anchor_x + dx
        raw_next_y = self.anchor_y + dy
        self._cross_work_area(raw_next_x, raw_next_y)
        next_y_for_wall = int(max(self.config.work_area.top, min(self.config.work_area.bottom, raw_next_y)))
        if self._grab_work_area_wall(previous_x, raw_next_x, next_y_for_wall):
            self._tick_frame()
            return
        self.anchor_x = int(max(self.config.work_area.left, min(self.config.work_area.right, raw_next_x)))
        if self._grab_work_area_ceiling(previous_y, raw_next_y):
            self._tick_frame()
            return
        next_y = int(max(self.config.work_area.top, min(self.config.work_area.bottom, raw_next_y)))
        if self._grab_active_window_wall(previous_x, self.anchor_x, next_y):
            self._tick_frame()
            return
        if self._grab_active_window_ceiling(previous_y, next_y):
            self._tick_frame()
            return
        ground_y = self._falling_ground_y(self.anchor_x, previous_y, next_y)
        self.anchor_y = int(min(ground_y, next_y))
        self._tick_frame()
        if self.anchor_y >= ground_y:
            self.anchor_y = ground_y
            self._finish_falling()

    def _fall_step_delta(self) -> tuple[int, int]:
        velocity_x_int = math.trunc(self.velocity_x)
        velocity_y_int = math.trunc(self.velocity_y)
        self._fall_mod_x += self.velocity_x - velocity_x_int
        self._fall_mod_y += self.velocity_y - velocity_y_int
        dx = velocity_x_int + math.trunc(self._fall_mod_x)
        dy = velocity_y_int + math.trunc(self._fall_mod_y)
        self._fall_mod_x = self._fall_mod_x - math.trunc(self._fall_mod_x)
        self._fall_mod_y = self._fall_mod_y - math.trunc(self._fall_mod_y)
        return dx, dy

    def _finish_falling(self) -> None:
        if self._sequence_queue:
            self._fall_from_throw = False
            self._finish_action("Stand")
            return
        recovery = self._landing_recovery_action() if self._fall_from_throw else None
        self._fall_from_throw = False
        self.velocity_x = 0.0
        self.velocity_y = 0.0
        if recovery is not None:
            self._start_direct_action(recovery, duration=self._action_frame_duration(recovery), auto_edge_climb=False)
            return
        self._finish_action("Stand")

    def _landing_recovery_action(self) -> str | None:
        for name in ("Bouncing", "Tripping"):
            if name in self.catalog.actions:
                return name
        return None

    def _falling_ground_y(self, x: int, previous_y: int, next_y: int) -> int:
        floating_ahead = [
            window for window in self.floating_window_rects
            if window.left <= x < window.right and window.top >= previous_y
        ]
        candidates = floating_ahead if floating_ahead else self._candidate_windows()
        crossings = [
            window for window in candidates
            if window.left <= x < window.right and previous_y <= window.top <= next_y
        ]
        if not crossings:
            return self.config.work_area.bottom
        window = min(crossings, key=lambda item: item.top)
        self.active_window_rect = window
        return min(window.top, self.config.work_area.bottom)

    def _is_on_active_window_top(self, x: int | None = None) -> bool:
        anchor_x = self.anchor_x if x is None else x
        for window in self._candidate_windows():
            if window.left <= anchor_x < window.right and self.anchor_y == window.top:
                if window not in self.floating_window_rects and any(
                    floating.left <= anchor_x < floating.right and floating.top > window.top
                    for floating in self.floating_window_rects
                ):
                    continue
                self.active_window_rect = window
                return True
        return False

    def _grab_active_window_wall(self, previous_x: int, next_x: int, next_y: int) -> bool:
        if "GrabWall" not in self.catalog.actions:
            return False
        crossings = [
            window for window in self._candidate_windows()
            if window.top <= next_y <= window.bottom
            and ((previous_x < window.left <= next_x) or (previous_x > window.right >= next_x))
        ]
        if not crossings:
            return False
        floating_crossings = [window for window in crossings if window in self.floating_window_rects]
        if floating_crossings:
            crossings = floating_crossings
        window = min(crossings, key=lambda item: abs((item.left if next_x > previous_x else item.right) - previous_x))
        self.active_window_rect = window
        if next_x > previous_x:
            self.anchor_x = window.left
            self.anchor_y = next_y
            self.look_right = True
        else:
            self.anchor_x = window.right
            self.anchor_y = next_y
            self.look_right = False
        self.velocity_x = 0.0
        self.velocity_y = 0.0
        self.start_action("GrabWall")
        return True

    def _grab_active_window_ceiling(self, previous_y: int, next_y: int) -> bool:
        if "GrabCeiling" not in self.catalog.actions:
            return False
        crossings = [
            window for window in self._candidate_windows()
            if window.left <= self.anchor_x <= window.right and previous_y > window.bottom >= next_y
        ]
        if not crossings:
            return False
        floating_crossings = [window for window in crossings if window in self.floating_window_rects]
        if floating_crossings:
            crossings = floating_crossings
        window = max(crossings, key=lambda item: item.bottom)
        self.active_window_rect = window
        self.anchor_y = window.bottom
        self.velocity_x = 0.0
        self.velocity_y = 0.0
        self.start_action("GrabCeiling")
        return True

    def _grab_work_area_wall(self, previous_x: int, next_x: float, next_y: int) -> bool:
        if "GrabWall" not in self.catalog.actions:
            return False
        work_area = self.config.work_area
        if not (work_area.top <= next_y <= work_area.bottom):
            return False
        if previous_x > work_area.left >= next_x:
            self.anchor_x = work_area.left
            self.anchor_y = next_y
            self.look_right = True
        elif previous_x < work_area.right <= next_x:
            self.anchor_x = work_area.right
            self.anchor_y = next_y
            self.look_right = False
        else:
            return False
        self.velocity_x = 0.0
        self.velocity_y = 0.0
        self.start_action("GrabWall")
        return True

    def _grab_work_area_ceiling(self, previous_y: int, next_y: float) -> bool:
        if "GrabCeiling" not in self.catalog.actions:
            return False
        work_area = self.config.work_area
        if not (work_area.left <= self.anchor_x <= work_area.right):
            return False
        if not (previous_y > work_area.top >= next_y):
            return False
        self.anchor_y = work_area.top
        self.velocity_x = 0.0
        self.velocity_y = 0.0
        self.start_action("GrabCeiling")
        return True

    def _maybe_start_edge_climb(self) -> bool:
        window = self.active_window_rect
        if not self._auto_edge_climb:
            return False
        if window is not None and self.action_name == "GrabWall" and "ClimbWall" in self.catalog.actions:
            edge = self.active_window_edge(tolerance=EDGE_TOLERANCE)
            if edge in {"left", "right"} and self.anchor_y > window.top:
                self.start_action("ClimbWall", target_y=window.top)
                self._auto_edge_climb = False
                return True
        if window is not None and self.action_name == "GrabCeiling" and "ClimbCeiling" in self.catalog.actions:
            edge = self.active_window_edge(tolerance=EDGE_TOLERANCE)
            if edge == "bottom" and self.anchor_x > window.left:
                self.start_action("ClimbCeiling", target_x=window.left)
                self._auto_edge_climb = False
                return True
        work_edge = self._work_area_wall_edge(tolerance=EDGE_TOLERANCE)
        if self.action_name == "GrabWall" and "ClimbWall" in self.catalog.actions:
            if work_edge in {"left", "right"} and self.anchor_y > self.config.work_area.top:
                self.start_action("ClimbWall", target_y=self.config.work_area.top)
                self._auto_edge_climb = False
                return True
        work_edge = self._work_area_ceiling_edge(tolerance=EDGE_TOLERANCE)
        if self.action_name == "GrabCeiling" and "ClimbCeiling" in self.catalog.actions:
            if work_edge == "top" and self.anchor_x > self.config.work_area.left:
                self.start_action("ClimbCeiling", target_x=self.config.work_area.left)
                self._auto_edge_climb = False
                return True
        return False

    def _is_unsupported(self) -> bool:
        if self.anchor_y >= self.config.work_area.bottom:
            return False
        if self._is_jump_action():
            return False
        if self._is_on_active_window_top():
            return False
        if self.action.border_type == "Wall" and self.active_window_edge(tolerance=EDGE_TOLERANCE) in {"left", "right"}:
            return False
        if self.action.border_type == "Ceiling" and self.active_window_edge(tolerance=EDGE_TOLERANCE) == "bottom":
            return False
        if self.action.border_type == "Wall" and self._work_area_wall_edge(tolerance=EDGE_TOLERANCE) in {"left", "right"}:
            return False
        if self.action.border_type == "Ceiling" and self._work_area_ceiling_edge(tolerance=EDGE_TOLERANCE) == "top":
            return False
        return True

    def work_area_edge(self, *, tolerance: int = 0) -> str:
        work_area = self.config.work_area
        x = self.anchor_x
        y = self.anchor_y
        inside_x = work_area.left - tolerance <= x <= work_area.right + tolerance
        inside_y = work_area.top - tolerance <= y <= work_area.bottom + tolerance
        if inside_x and abs(y - work_area.top) <= tolerance:
            return "top"
        if inside_x and abs(y - work_area.bottom) <= tolerance:
            return "bottom"
        if inside_y and abs(x - work_area.left) <= tolerance:
            return "left"
        if inside_y and abs(x - work_area.right) <= tolerance:
            return "right"
        return "none"

    def _work_area_wall_edge(self, *, tolerance: int = 0) -> str:
        work_area = self.config.work_area
        inside_y = work_area.top - tolerance <= self.anchor_y <= work_area.bottom + tolerance
        if inside_y and abs(self.anchor_x - work_area.left) <= tolerance:
            return "left"
        if inside_y and abs(self.anchor_x - work_area.right) <= tolerance:
            return "right"
        return "none"

    def _work_area_ceiling_edge(self, *, tolerance: int = 0) -> str:
        work_area = self.config.work_area
        inside_x = work_area.left - tolerance <= self.anchor_x <= work_area.right + tolerance
        if inside_x and abs(self.anchor_y - work_area.top) <= tolerance:
            return "top"
        return "none"

    def available_idle_actions(self) -> list[str]:
        weighted_actions = self._weighted_idle_actions()
        actions: list[str] = []
        for name, _weight in weighted_actions:
            if name not in actions:
                actions.append(name)
        return actions

    def available_manual_behaviors(self) -> list[str]:
        if self.behavior_catalog is None:
            return self.available_idle_actions()
        return [
            behavior.name
            for behavior in self.behavior_catalog.behaviors.values()
            if not behavior.hidden
            and (self.allow_split or not self._is_split_action(behavior.action_name))
            and behavior.action_name in self.catalog.actions
            and self._behavior_partner_available(behavior.name)
            and self._behavior_condition_matches(behavior.condition)
        ]

    def start_manual_behavior(self, name: str, *, rng: Any = random) -> bool:
        if self.pointer_active or name not in self.available_manual_behaviors():
            return False
        action_name = self.behavior_catalog.behaviors[name].action_name if self.behavior_catalog else name
        self._start_idle_behavior(name, action_name, rng)
        return True

    def _weighted_idle_actions(self) -> list[tuple[str, int]]:
        behavior_actions = self._weighted_behavior_idle_actions()
        if behavior_actions:
            return behavior_actions
        return [(name, 100) for name in self._fallback_idle_actions()]

    def _weighted_behavior_candidates(self, previous_behavior: str | None = None) -> list[tuple[str, str, int]]:
        if self.behavior_catalog is None:
            return []
        weighted_actions: list[tuple[str, str, int]] = []
        for behavior in self.behavior_catalog.behaviors.values():
            if not self.allow_split and self._is_split_action(behavior.action_name):
                continue
            if behavior.frequency <= 0:
                continue
            if behavior.action_name not in self.catalog.actions:
                continue
            if not self._behavior_partner_available(behavior.name):
                continue
            if not self._behavior_condition_matches(behavior.condition):
                continue
            weighted_actions.append((behavior.name, behavior.action_name, behavior.frequency))
        if previous_behavior is None:
            return weighted_actions
        previous = self.behavior_catalog.behaviors.get(previous_behavior)
        if previous is None or not previous.next_behaviors:
            return weighted_actions
        if not previous.next_add:
            weighted_actions = []
        for behavior in previous.next_behaviors:
            if not self.allow_split and self._is_split_action(behavior.action_name):
                continue
            if behavior.frequency <= 0:
                continue
            if behavior.action_name not in self.catalog.actions:
                continue
            if not self._behavior_partner_available(behavior.name):
                continue
            if not self._behavior_condition_matches(behavior.condition):
                continue
            weighted_actions.append((behavior.name, behavior.action_name, behavior.frequency))
        return weighted_actions

    def _is_split_action(self, name: str) -> bool:
        # The original Neurolings archive calls its split sequence Glitch.
        seen: set[str] = set()

        def visits(action) -> bool:
            if action is None or action.name in seen:
                return False
            seen.add(action.name)
            if action.params.get("BornBehavior", action.params.get("BornBehaviour")) == "Divided":
                return True
            return any(visits(self.catalog.actions.get(step.name) if isinstance(step, ActionReference) else step)
                       for step in action.references)

        return visits(self.catalog.actions.get(name))

    def _behavior_partner_available(self, name: str) -> bool:
        partners = PARTNER_BEHAVIOR_REQUIREMENTS.get((self.catalog.image_set_dir.name, name))
        return not partners or (self.world is not None and self.world.has_image_set(*partners))

    def _weighted_behavior_idle_actions(self, previous_behavior: str | None = None) -> list[tuple[str, int]]:
        return [(name, frequency) for name, _action_name, frequency in self._weighted_behavior_candidates(previous_behavior)]

    def _behavior_condition_matches(self, condition: str | None) -> bool:
        if not condition:
            return True
        return self._resolve_bool_expression(condition)

    def _choose_next_behavior(self, previous_behavior: str) -> tuple[str, str] | None:
        weighted_actions = self._weighted_behavior_candidates(previous_behavior=previous_behavior)
        if not weighted_actions:
            return None
        alternatives = [item for item in weighted_actions if item[0] != previous_behavior]
        if alternatives:
            weighted_actions = alternatives
        candidates = [(name, action_name) for name, action_name, _weight in weighted_actions]
        weights = [weight for _name, _action_name, weight in weighted_actions]
        return random.choices(candidates, weights=weights, k=1)[0]

    def _fallback_idle_actions(self) -> list[str]:
        if self._work_area_wall_edge(tolerance=EDGE_TOLERANCE) in {"left", "right"}:
            return self._existing_actions(WORK_AREA_WALL_IDLE_ACTIONS)
        if self._work_area_ceiling_edge(tolerance=EDGE_TOLERANCE) == "top":
            return self._existing_actions(WORK_AREA_CEILING_IDLE_ACTIONS)
        if self.active_window_edge(tolerance=EDGE_TOLERANCE) == "top":
            return self._existing_actions(ACTIVE_WINDOW_TOP_IDLE_ACTIONS)
        if self.anchor_y >= self.config.work_area.bottom:
            return self._existing_actions(FLOOR_IDLE_ACTIONS)
        return []

    def start_idle_action(self, *, rng: Any = random) -> bool:
        if self.dragging or self.action_name != "Stand":
            return False
        behavior_candidates = self._weighted_behavior_candidates()
        if behavior_candidates:
            candidates = [name for name, _action_name, _weight in behavior_candidates]
            weights = [weight for _name, _action_name, weight in behavior_candidates]
            if hasattr(rng, "choices"):
                name = rng.choices(candidates, weights=weights, k=1)[0]
            else:
                name = rng.choice(candidates)
            action_name = next(action_name for candidate_name, action_name, _weight in behavior_candidates if candidate_name == name)
            self._start_idle_behavior(name, action_name, rng)
            return True
        weighted_actions = self._weighted_idle_actions()
        if not weighted_actions:
            return False
        candidates = [name for name, _weight in weighted_actions]
        weights = [weight for _name, weight in weighted_actions]
        if hasattr(rng, "choices"):
            name = rng.choices(candidates, weights=weights, k=1)[0]
        else:
            name = rng.choice(candidates)
        self._start_idle_behavior(name, name, rng)
        return True

    def _start_idle_behavior(self, name: str, action_name: str, rng: Any) -> None:
        action = self.catalog.actions[action_name]
        duration = self._action_frame_duration(action_name) if action.kind == "Animate" else None
        if self._is_move_action(action) and action.border_type == "Floor":
            target = self._random_floor_target(rng)
            self._start_behavior(name, action_name=action_name, look_right=target > self.anchor_x, target_x=target, duration=duration)
        else:
            self._start_behavior(name, action_name=action_name, duration=duration)

    def _existing_actions(self, names: tuple[str, ...]) -> list[str]:
        return [name for name in names if name in self.catalog.actions]

    def _random_floor_target(self, rng: Any) -> int:
        left = self.config.work_area.left + 96
        right = self.config.work_area.right - 96
        if left > right:
            return self.config.work_area.left + (self.config.work_area.width // 2)
        return self._distant_floor_target_if_needed(int(rng.randint(left, right)))

    def _distant_floor_target_if_needed(self, target_x: int) -> int:
        if abs(target_x - self.anchor_x) >= MIN_RANDOM_FLOOR_TARGET_DISTANCE:
            return target_x
        left = self.config.work_area.left + MIN_RANDOM_FLOOR_TARGET_DISTANCE
        right = self.config.work_area.right - MIN_RANDOM_FLOOR_TARGET_DISTANCE
        if left > right:
            return target_x
        left_distance = abs(self.anchor_x - left)
        right_distance = abs(right - self.anchor_x)
        if right_distance >= MIN_RANDOM_FLOOR_TARGET_DISTANCE and right_distance >= left_distance:
            return right
        if left_distance >= MIN_RANDOM_FLOOR_TARGET_DISTANCE:
            return left
        return target_x


class PetWorld:
    def __init__(self) -> None:
        self._runtimes: list[PetRuntime] = []

    def register(self, runtime: PetRuntime) -> None:
        if runtime in self._runtimes:
            return
        runtime.world = self
        self._runtimes.append(runtime)

    def unregister(self, runtime: PetRuntime) -> None:
        if runtime not in self._runtimes:
            return
        self._runtimes.remove(runtime)
        if runtime.world is self:
            runtime.world = None

    def total_count(self) -> int:
        return len(self._runtimes)

    def has_image_set(self, *names: str) -> bool:
        return any(runtime.catalog.image_set_dir.name in names for runtime in self._runtimes)

    def find_with_affordance(self, requester: PetRuntime, affordance: str) -> PetRuntime | None:
        for runtime in self._runtimes:
            if runtime is requester:
                continue
            if runtime.current_affordance() == affordance:
                return runtime
        return None

    def has_overlapping_anchor(self, requester: PetRuntime) -> bool:
        count = 0
        for runtime in self._runtimes:
            if runtime.anchor_x == requester.anchor_x and runtime.anchor_y == requester.anchor_y:
                count += 1
            if count > 1:
                return True
        return False
