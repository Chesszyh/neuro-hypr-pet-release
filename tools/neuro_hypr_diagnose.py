#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.assets import default_collection

from src.hyprland import active_window, active_window_rect_for_monitor, cursor_pos, select_monitor  # noqa: E402
from src.runtime import PetRuntime, RuntimeConfig  # noqa: E402
from src.shimeji_model import ActionCatalog, ActionDef, PoseFrame, load_action_catalog, load_behavior_catalog  # noqa: E402


def parse_anchor(value: str) -> tuple[int, int]:
    left, sep, right = value.partition(",")
    if not sep:
        raise argparse.ArgumentTypeError("expected X,Y")
    return int(left), int(right)


def make_probe_runtime(work_area, anchor: tuple[int, int]) -> PetRuntime:
    frame = PoseFrame("probe.png", 0, 0, 0.0, 0.0, 1)
    catalog = ActionCatalog(
        image_set_dir=Path("."),
        actions={"Stand": ActionDef("Stand", "Stay", None, (frame,), {})},
    )
    return PetRuntime(catalog, RuntimeConfig(work_area=work_area, start_x=anchor[0], start_y=anchor[1]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose Hyprland data used by neuro-hypr-pet.")
    parser.add_argument("--monitor")
    parser.add_argument("--anchor", type=parse_anchor, help="Local monitor anchor X,Y to classify against the active window.")
    parser.add_argument("--collection", type=Path, default=default_collection())
    parser.add_argument("--image-set", default="Neuron")
    args = parser.parse_args(argv)

    monitor = select_monitor(args.monitor)
    cursor = cursor_pos()
    cursor_local = (cursor.x - monitor.x, cursor.y - monitor.y)
    anchor = args.anchor or cursor_local
    window = active_window()
    print(f"monitor={monitor.name} geometry={monitor.x},{monitor.y} {monitor.width}x{monitor.height}")
    print(
        f"work_area=local:{monitor.work_area.x},{monitor.work_area.y} "
        f"{monitor.work_area.width}x{monitor.work_area.height}"
    )
    print(f"cursor=global:{cursor.x},{cursor.y}")
    print(f"cursor_local={cursor_local[0]},{cursor_local[1]}")
    if window is None:
        print("active_window=none")
    else:
        local = monitor.to_local_rect(window.rect)
        target = active_window_rect_for_monitor(monitor, window)
        print(
            f"active_window=class:{window.class_name} title:{window.title} "
            f"global={window.x},{window.y} {window.width}x{window.height} "
            f"local={local.x},{local.y} {local.width}x{local.height} fullscreen={window.fullscreen}"
        )
        if target is None:
            print("active_window_runtime_target=none")
        else:
            print(f"active_window_runtime_target=local:{target.x},{target.y} {target.width}x{target.height}")
            runtime = make_probe_runtime(monitor.work_area, anchor)
            runtime.update_active_window_rect(target)
            print(f"active_window_edge_at_anchor={anchor[0]},{anchor[1]}:{runtime.active_window_edge(tolerance=3)}")
    behaviors_xml = args.collection / "img" / args.image_set / "conf" / "behaviors.xml"
    actions_xml = args.collection / "img" / args.image_set / "conf" / "actions.xml"
    if actions_xml.is_file():
        action_catalog = load_action_catalog(actions_xml)
        sequence_actions = [action for action in action_catalog.actions.values() if action.references]
        framed_actions = [action for action in action_catalog.actions.values() if action.frames]
        print(f"action_catalog={args.image_set}:framed={len(framed_actions)} sequence={len(sequence_actions)}")
        for action_name in ("WalkAlongIECeiling", "ClimbIEWall", "ClimbIEBottom", "GrabIEBottomLeftWall", "GrabIEBottomRightWall"):
            action = action_catalog.actions.get(action_name)
            if action is None:
                continue
            refs = ",".join(reference.name for reference in action.references) or "none"
            print(f"action={action.name} kind={action.kind} loop={str(action.loop).lower()} refs={refs}")
    if behaviors_xml.is_file():
        behavior_catalog = load_behavior_catalog(behaviors_xml)
        print(f"behavior_catalog={args.image_set}:{len(behavior_catalog.behaviors)}")
        for behavior_name in ("Fall", "Dragged", "Thrown", "WalkAlongIECeiling", "ClimbIEWall", "ClimbIEBottom"):
            behavior = behavior_catalog.behaviors.get(behavior_name)
            if behavior is None:
                continue
            condition = behavior.condition or "none"
            print(
                f"behavior={behavior.name} frequency={behavior.frequency} hidden={str(behavior.hidden).lower()} "
                f"condition={condition} next={len(behavior.next_behaviors)} add={str(behavior.next_add).lower()}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
