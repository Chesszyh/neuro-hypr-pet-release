from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


MASCOT_NS = {"m": "http://www.group-finity.com/Mascot"}


@dataclass(frozen=True)
class HotspotDef:
    shape: str
    x: int
    y: int
    width: int
    height: int
    behavior: str | None

    def contains(self, x: int, y: int, *, image_width: int, look_right: bool) -> bool:
        if look_right:
            x = image_width - x
        if self.shape.lower() == "rectangle":
            return self.x <= x < self.x + self.width and self.y <= y < self.y + self.height
        if self.shape.lower() == "ellipse":
            radius_x = self.width / 2.0
            radius_y = self.height / 2.0
            if radius_x <= 0 or radius_y <= 0:
                return False
            center_x = self.x + radius_x
            center_y = self.y + radius_y
            normalized_x = (x - center_x) / radius_x
            normalized_y = (y - center_y) / radius_y
            return (normalized_x * normalized_x) + (normalized_y * normalized_y) <= 1.0
        return False


@dataclass(frozen=True)
class PoseFrame:
    image: str
    anchor_x: int
    anchor_y: int
    velocity_x: float
    velocity_y: float
    duration: int
    hotspots: tuple[HotspotDef, ...] = ()
    image_right: str | None = None
    sound: str | None = None
    sound_volume: float = 0.0

    def image_for_direction(self, *, look_right: bool) -> str:
        if look_right and self.image_right:
            return self.image_right
        return self.image

    def needs_horizontal_flip(self, *, look_right: bool) -> bool:
        return look_right and not self.image_right


@dataclass(frozen=True)
class AnimationDef:
    condition: str | None
    is_turn: bool
    frames: tuple[PoseFrame, ...]


@dataclass(frozen=True)
class ActionReference:
    name: str
    params: dict[str, str]


@dataclass(frozen=True)
class ActionDef:
    name: str
    kind: str
    border_type: str | None
    frames: tuple[PoseFrame, ...]
    params: dict[str, str]
    references: tuple["ActionStep", ...] = ()
    animations: tuple[AnimationDef, ...] = ()
    loop: bool = False


ActionStep = ActionReference | ActionDef


@dataclass(frozen=True)
class ActionCatalog:
    image_set_dir: Path
    actions: dict[str, ActionDef]


@dataclass(frozen=True)
class BehaviorReference:
    name: str
    action_name: str
    frequency: int
    condition: str | None
    hidden: bool


@dataclass(frozen=True)
class BehaviorDef:
    name: str
    action_name: str
    frequency: int
    hidden: bool
    condition: str | None
    next_add: bool
    next_behaviors: tuple[BehaviorReference, ...]


@dataclass(frozen=True)
class BehaviorCatalog:
    behaviors: dict[str, BehaviorDef]


def _parse_pair(value: str | None, default: tuple[float, float]) -> tuple[float, float]:
    if not value:
        return default
    left, _, right = value.partition(",")
    if not right:
        return default
    return float(left.strip()), float(right.strip())


def _parse_pose(pose: ET.Element, hotspots: tuple[HotspotDef, ...] = ()) -> PoseFrame | None:
    image = pose.get("Image")
    image_right = pose.get("ImageRight")
    sound = pose.get("Sound")
    anchor_x, anchor_y = _parse_pair(pose.get("ImageAnchor"), (0.0, 0.0))
    velocity_x, velocity_y = _parse_pair(pose.get("Velocity"), (0.0, 0.0))
    duration = int(float(pose.get("Duration", "1")))
    return PoseFrame(
        image=image.lstrip("/") if image else "",
        anchor_x=int(anchor_x),
        anchor_y=int(anchor_y),
        velocity_x=velocity_x,
        velocity_y=velocity_y,
        duration=max(1, duration),
        hotspots=hotspots,
        image_right=image_right.lstrip("/") if image_right else None,
        sound=sound.lstrip("/") if sound else None,
        sound_volume=float(pose.get("Volume", "0")),
    )


def _parse_hotspot(hotspot: ET.Element) -> HotspotDef | None:
    shape = hotspot.get("Shape")
    origin = hotspot.get("Origin")
    size = hotspot.get("Size")
    if not shape or not origin or not size:
        return None
    x, y = _parse_pair(origin, (0.0, 0.0))
    width, height = _parse_pair(size, (0.0, 0.0))
    return HotspotDef(
        shape=shape,
        x=int(x),
        y=int(y),
        width=int(width),
        height=int(height),
        behavior=hotspot.get("Behavior") or hotspot.get("Behaviour"),
    )


def _parse_action_reference(reference: ET.Element) -> ActionReference | None:
    name = reference.get("Name")
    if not name:
        return None
    return ActionReference(
        name=name,
        params={key: value for key, value in reference.attrib.items() if key != "Name"},
    )


def _local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _parse_action(action: ET.Element, synthetic_name: str | None, counter: list[int]) -> ActionDef | None:
    name = action.get("Name") or synthetic_name
    kind = action.get("Type")
    if not name or not kind:
        return None
    frames: list[PoseFrame] = []
    animations: list[AnimationDef] = []
    references: list[ActionStep] = []
    for child in action:
        tag = _local_name(child)
        if tag == "Animation":
            hotspots = tuple(
                parsed
                for parsed in (_parse_hotspot(hotspot) for hotspot in child.findall("m:Hotspot", MASCOT_NS))
                if parsed is not None
            )
            animation_frames: list[PoseFrame] = []
            for pose in child.findall("m:Pose", MASCOT_NS):
                frame = _parse_pose(pose, hotspots)
                if frame is not None:
                    animation_frames.append(frame)
                    frames.append(frame)
            if animation_frames:
                animations.append(
                    AnimationDef(
                        condition=child.get("Condition"),
                        is_turn=_parse_bool(child.get("IsTurn")),
                        frames=tuple(animation_frames),
                    )
                )
        elif tag == "ActionReference":
            parsed = _parse_action_reference(child)
            if parsed is not None:
                references.append(parsed)
        elif tag == "Action":
            counter[0] += 1
            parsed_action = _parse_action(child, f"__inline_action_{counter[0]}", counter)
            if parsed_action is not None:
                references.append(parsed_action)
    params = {key: value for key, value in action.attrib.items() if key not in {"Name", "Type", "BorderType", "Loop"}}
    if not frames and not references and not _is_instant_action(kind, params):
        return None
    if len(animations) >= 2 and _is_legacy_move_with_turn(kind, params):
        last = animations[-1]
        animations[-1] = AnimationDef(condition=last.condition, is_turn=True, frames=last.frames)
    return ActionDef(
        name=name,
        kind=kind,
        border_type=action.get("BorderType"),
        frames=tuple(frames),
        params=params,
        references=tuple(references),
        animations=tuple(animations),
        loop=_parse_bool(action.get("Loop")),
    )


def _is_legacy_move_with_turn(kind: str, params: dict[str, str]) -> bool:
    action_class = params.get("Class", "")
    return kind == "MoveWithTurn" or action_class.endswith(".MoveWithTurn")


def _is_instant_action(kind: str, params: dict[str, str]) -> bool:
    action_class = params.get("Class", "")
    return kind == "Embedded" and (action_class.endswith(".Look") or action_class.endswith(".Offset"))


def load_action_catalog(actions_xml: Path) -> ActionCatalog:
    root = ET.parse(actions_xml).getroot()
    actions: dict[str, ActionDef] = {}
    counter = [0]
    for action_list in root.findall("m:ActionList", MASCOT_NS):
        for action in action_list.findall("m:Action", MASCOT_NS):
            parsed = _parse_action(action, None, counter)
            if parsed is not None and action.get("Name"):
                actions[parsed.name] = parsed
    return ActionCatalog(image_set_dir=actions_xml.parent.parent, actions=actions)


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() == "true"


def _parse_frequency(value: str | None) -> int:
    if not value:
        return 0
    return int(float(value))


def _parse_behavior_reference(reference: ET.Element) -> BehaviorReference | None:
    name = reference.get("Name")
    if not name:
        return None
    return BehaviorReference(
        name=name,
        action_name=reference.get("Action") or name,
        frequency=_parse_frequency(reference.get("Frequency")),
        condition=reference.get("Condition"),
        hidden=_parse_bool(reference.get("Hidden")),
    )


def _parse_next_behaviors(behavior: ET.Element) -> tuple[bool, tuple[BehaviorReference, ...]]:
    next_list = behavior.find("m:NextBehaviorList", MASCOT_NS)
    if next_list is None:
        return False, ()
    references: list[BehaviorReference] = []
    for reference in next_list.findall("m:BehaviorReference", MASCOT_NS):
        parsed = _parse_behavior_reference(reference)
        if parsed is not None:
            references.append(parsed)
    return _parse_bool(next_list.get("Add")), tuple(references)


def _parse_behavior(behavior: ET.Element, inherited_condition: str | None) -> BehaviorDef | None:
    name = behavior.get("Name")
    if not name:
        return None
    own_condition = behavior.get("Condition")
    if inherited_condition and own_condition:
        condition = f"({inherited_condition}) && ({own_condition})"
    else:
        condition = own_condition or inherited_condition
    next_add, next_behaviors = _parse_next_behaviors(behavior)
    return BehaviorDef(
        name=name,
        action_name=behavior.get("Action") or name,
        frequency=_parse_frequency(behavior.get("Frequency")),
        hidden=_parse_bool(behavior.get("Hidden")),
        condition=condition,
        next_add=next_add,
        next_behaviors=next_behaviors,
    )


def _collect_behaviors(element: ET.Element, inherited_condition: str | None, behaviors: dict[str, BehaviorDef]) -> None:
    for child in element:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "Condition":
            condition = child.get("Condition")
            if inherited_condition and condition:
                condition = f"({inherited_condition}) && ({condition})"
            else:
                condition = condition or inherited_condition
            _collect_behaviors(child, condition, behaviors)
        elif tag == "Behavior":
            parsed = _parse_behavior(child, inherited_condition)
            if parsed is not None:
                behaviors[parsed.name] = parsed
        else:
            _collect_behaviors(child, inherited_condition, behaviors)


def load_behavior_catalog(behaviors_xml: Path) -> BehaviorCatalog:
    root = ET.parse(behaviors_xml).getroot()
    behavior_list = root.find("m:BehaviorList", MASCOT_NS)
    behaviors: dict[str, BehaviorDef] = {}
    if behavior_list is not None:
        _collect_behaviors(behavior_list, None, behaviors)
    return BehaviorCatalog(behaviors=behaviors)
