#!/usr/bin/env python3
"""Export The-Neuroling-Collection image sets to wayland-vpets configs."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from neuro_hypr_pet.assets import default_collection

from PIL import Image


MASCOT_NS = {"m": "http://www.group-finity.com/Mascot"}


@dataclass(frozen=True)
class AnimationRow:
    key: str
    config_prefix: str
    action_candidates: tuple[str, ...]
    fallback_images: tuple[str, ...]


ROWS: tuple[AnimationRow, ...] = (
    AnimationRow("idle", "idle", ("Stand",), ("shime1.png",)),
    AnimationRow("boring", "boring", ("Sit", "Sprawl"), ("shime11.png", "shime1.png")),
    AnimationRow(
        "start_writing",
        "start_writing",
        ("Bouncing", "DanceAction", "HeartHeartHeartAction"),
        ("shime18.png", "shime1.png"),
    ),
    AnimationRow(
        "writing",
        "writing",
        ("Bouncing", "DanceAction", "HeartHeartHeartAction"),
        ("shime18.png", "shime19.png", "shime1.png"),
    ),
    AnimationRow("end_writing", "end_writing", ("Stand",), ("shime1.png",)),
    AnimationRow(
        "happy",
        "happy",
        ("HeartHeartHeartAction", "DanceAction", "Bouncing"),
        ("shime15.png", "shime16.png", "shime1.png"),
    ),
    AnimationRow("asleep", "asleep", ("Sprawl", "Sit"), ("shime20.png", "shime11.png", "shime1.png")),
    AnimationRow("sleep", "sleep", ("Sprawl", "Sit"), ("shime20.png", "shime11.png", "shime1.png")),
    AnimationRow("wake_up", "wake_up", ("Stand",), ("shime1.png",)),
    AnimationRow("start_moving", "start_moving", ("Walk",), ("shime1a.png", "shime2.png", "shime1.png")),
    AnimationRow("moving", "moving", ("Walk",), ("shime1a.png", "shime2.png", "shime3.png", "shime1.png")),
    AnimationRow("end_moving", "end_moving", ("Stand",), ("shime1.png",)),
    AnimationRow("start_running", "start_running", ("Run", "Dash"), ("run1.png",)),
    AnimationRow("running", "running", ("Run", "Dash"), ("run1.png", "run2.png", "run3.png", "run4.png")),
    AnimationRow("end_running", "end_running", ("Stand",), ("shime1.png",)),
)


def parse_actions(actions_xml: Path) -> dict[str, list[str]]:
    root = ET.parse(actions_xml).getroot()
    actions: dict[str, list[str]] = {}
    for action in root.findall(".//m:Action", MASCOT_NS):
        name = action.get("Name")
        if not name:
            continue
        images: list[str] = []
        for pose in action.findall(".//m:Pose", MASCOT_NS):
            image = pose.get("Image")
            if image:
                images.append(image.lstrip("/"))
        if images:
            actions[name] = images
    return actions


def _first_existing(image_set_dir: Path, names: Iterable[str]) -> list[str]:
    existing: list[str] = []
    for name in names:
        if (image_set_dir / name).is_file():
            existing.append(name)
    return existing


def choose_frames(image_set_dir: Path, actions: dict[str, list[str]], max_frames: int) -> list[tuple[AnimationRow, list[str]]]:
    chosen: list[tuple[AnimationRow, list[str]]] = []
    for row in ROWS:
        frames: list[str] = []
        for action_name in row.action_candidates:
            action_frames = _first_existing(image_set_dir, actions.get(action_name, ()))
            if action_frames:
                frames = action_frames
                break
        if not frames:
            frames = _first_existing(image_set_dir, row.fallback_images)
        if not frames:
            raise FileNotFoundError(f"{image_set_dir}: no frames found for {row.key}")
        chosen.append((row, frames[:max_frames]))
    return chosen


def load_frame(path: Path, target_height: int | None = None) -> Image.Image:
    with Image.open(path) as image:
        frame = image.convert("RGBA")
    if target_height and target_height > 0 and frame.height != target_height:
        width = max(1, round(frame.width * (target_height / frame.height)))
        frame = frame.resize((width, target_height), Image.Resampling.NEAREST)
    return frame


def render_sprite_sheet(
    image_set_dir: Path,
    rows: list[tuple[AnimationRow, list[str]]],
    output_png: Path,
    *,
    target_height: int | None = None,
) -> tuple[int, int, int]:
    unique_images = []
    for _, names in rows:
        unique_images.extend(names)

    frame_width = 0
    frame_height = 0
    for name in unique_images:
        frame = load_frame(image_set_dir / name, target_height)
        frame_width = max(frame_width, frame.width)
        frame_height = max(frame_height, frame.height)

    columns = max(len(names) for _, names in rows)
    sheet = Image.new("RGBA", (frame_width * columns, frame_height * len(rows)), (0, 0, 0, 0))
    for row_index, (_, names) in enumerate(rows):
        for col_index, name in enumerate(names):
            frame = load_frame(image_set_dir / name, target_height)
            x = (col_index * frame_width) + ((frame_width - frame.width) // 2)
            y = (row_index * frame_height) + (frame_height - frame.height)
            sheet.alpha_composite(frame, (x, y))

    output_png.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_png)
    return frame_width, frame_height, columns


def render_combined_sprite_sheet(
    set_rows: list[tuple[Path, list[tuple[AnimationRow, list[str]]]]],
    output_png: Path,
    *,
    spacing: int,
    target_height: int | None = None,
) -> tuple[int, int, int]:
    frame_width = 0
    frame_height = 0
    for image_set_dir, rows in set_rows:
        for _, names in rows:
            for name in names:
                frame = load_frame(image_set_dir / name, target_height)
                frame_width = max(frame_width, frame.width)
                frame_height = max(frame_height, frame.height)

    row_count = len(ROWS)
    frame_counts: list[int] = []
    for row_index in range(row_count):
        frame_counts.append(max(len(rows[row_index][1]) for _, rows in set_rows))
    columns = max(frame_counts)
    combined_width = (frame_width * len(set_rows)) + (spacing * max(0, len(set_rows) - 1))
    sheet = Image.new("RGBA", (combined_width * columns, frame_height * row_count), (0, 0, 0, 0))

    for row_index in range(row_count):
        for col_index in range(frame_counts[row_index]):
            for pet_index, (image_set_dir, rows) in enumerate(set_rows):
                names = rows[row_index][1]
                name = names[col_index % len(names)]
                frame = load_frame(image_set_dir / name, target_height)
                cell_x = (col_index * combined_width) + (pet_index * (frame_width + spacing))
                x = cell_x + ((frame_width - frame.width) // 2)
                y = (row_index * frame_height) + (frame_height - frame.height)
                sheet.alpha_composite(frame, (x, y))

    output_png.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_png)
    return combined_width, frame_height, columns


def write_config(
    config_path: Path,
    sprite_sheet_path: Path,
    rows: list[tuple[AnimationRow, list[str]]],
    *,
    cat_height: int,
    overlay_height: int,
    x_offset: int,
    monitor: str | None,
    keyboard_devices: list[str],
    fps: int,
    input_fps: int,
    animation_speed: int,
    movement_radius: int,
    movement_speed: int,
) -> None:
    rel_sprite = os.path.relpath(sprite_sheet_path, config_path.parent)
    lines = [
        "# Generated by tools/neuroling_wpets.py",
        f"custom_sprite_sheet_filename={rel_sprite}",
        "animation_name=custom",
        f"cat_height={cat_height}",
        f"overlay_height={overlay_height}",
        "overlay_opacity=0",
        "overlay_position=bottom",
        "overlay_layer=overlay",
        "cat_align=center",
        f"cat_x_offset={x_offset}",
        "cat_y_offset=0",
        "idle_frame=0",
        "idle_animation=1",
        f"animation_speed={animation_speed}",
        "keypress_duration=350",
        f"fps={fps}",
        f"input_fps={input_fps}",
        "enable_antialiasing=0",
        "invert_color=0",
        "mirror_x=0",
        "mirror_y=0",
        f"movement_radius={movement_radius}",
        f"movement_speed={movement_speed}",
        "movement_wait_factor=1.5",
    ]
    if monitor:
        lines.append(f"monitor={monitor}")
    for keyboard_device in keyboard_devices:
        lines.append(f"keyboard_device={keyboard_device}")
    for row_index, (row, frames) in enumerate(rows):
        lines.append(f"custom_{row.config_prefix}_frames={len(frames)}")
        lines.append(f"custom_{row.config_prefix}_row={row_index + 1}")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def discover_image_sets(collection_dir: Path, names: list[str]) -> list[str]:
    if names:
        return names
    image_root = collection_dir / "img"
    found = []
    for child in sorted(image_root.iterdir()):
        if child.is_dir() and (child / "conf" / "actions.xml").is_file():
            found.append(child.name)
    return found


def discover_keyboard_devices() -> list[str]:
    by_id = Path("/dev/input/by-id")
    if by_id.is_dir():
        devices = sorted(str(path) for path in by_id.glob("*-event-kbd") if path.exists())
        if devices:
            return devices
    return []


def export_set(
    collection_dir: Path,
    output_dir: Path,
    image_set: str,
    *,
    max_frames: int,
    cat_height: int,
    overlay_height: int,
    x_offset: int,
    monitor: str | None,
    keyboard_devices: list[str],
    fps: int,
    input_fps: int,
    animation_speed: int,
    movement_radius: int,
    movement_speed: int,
) -> Path:
    image_set_dir = collection_dir / "img" / image_set
    actions_xml = image_set_dir / "conf" / "actions.xml"
    if not actions_xml.is_file():
        raise FileNotFoundError(f"missing actions.xml for {image_set}: {actions_xml}")
    actions = parse_actions(actions_xml)
    rows = choose_frames(image_set_dir, actions, max_frames)
    set_output_dir = output_dir / image_set
    sprite_sheet = set_output_dir / "sprite.png"
    render_sprite_sheet(image_set_dir, rows, sprite_sheet, target_height=cat_height)
    config_path = set_output_dir / "wpets.conf"
    write_config(
        config_path,
        sprite_sheet,
        rows,
        cat_height=cat_height,
        overlay_height=overlay_height,
        x_offset=x_offset,
        monitor=monitor,
        keyboard_devices=keyboard_devices,
        fps=fps,
        input_fps=input_fps,
        animation_speed=animation_speed,
        movement_radius=movement_radius,
        movement_speed=movement_speed,
    )
    return config_path


def install_runtime_files(repo_root: Path, output_dir: Path, binary: Path) -> Path:
    launcher = output_dir / "neuro-hypr-pet-wayland"
    launcher.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"',
                f'BIN="${{NEURO_WPETS_BIN:-{binary}}}"',
                'CONFIG_DIR="${NEURO_WPETS_CONFIG_DIR:-$SCRIPT_DIR}"',
                'if [[ "${1:-}" == "--stop" ]]; then',
                '  pkill -f "$BIN.*$CONFIG_DIR" || true',
                "  exit 0",
                "fi",
                "pids=()",
                "cleanup() {",
                '  for pid in "${pids[@]:-}"; do',
                '    kill "$pid" 2>/dev/null || true',
                "  done",
                '  wait "${pids[@]:-}" 2>/dev/null || true',
                "}",
                "trap cleanup EXIT INT TERM",
                'nr=6100',
                'mode="${NEURO_WPETS_MODE:-single}"',
                'if [[ "${NEURO_WPETS_SEPARATE:-0}" == "1" && "${NEURO_WPETS_MODE:-}" == "" ]]; then',
                '  mode="separate"',
                "fi",
                'set_name="${NEURO_WPETS_SET:-Neuron}"',
                "case \"$mode\" in",
                "  single)",
                '    cfg="$CONFIG_DIR/$set_name/wpets.conf"',
                '    if [[ ! -f "$cfg" ]]; then',
                '      echo "Missing Neuroling wpets config: $cfg" >&2',
                "      exit 1",
                "    fi",
                '    configs=("$cfg")',
                "    ;;",
                "  combined)",
                '    cfg="$CONFIG_DIR/All/wpets.conf"',
                '    if [[ ! -f "$cfg" ]]; then',
                '      echo "Missing combined Neuroling wpets config: $cfg" >&2',
                "      exit 1",
                "    fi",
                '    configs=("$cfg")',
                "    ;;",
                "  separate)",
                "    shopt -s nullglob",
                "    configs=()",
                '    for cfg in "$CONFIG_DIR"/*/wpets.conf; do',
                '      [[ "$cfg" == "$CONFIG_DIR/All/wpets.conf" ]] && continue',
                '      configs+=("$cfg")',
                "    done",
                "    if [[ ${#configs[@]} -eq 0 ]]; then",
                '      echo "No separate Neuroling wpets configs found in: $CONFIG_DIR" >&2',
                "      exit 1",
                "    fi",
                "    ;;",
                "  *)",
                '    echo "Invalid NEURO_WPETS_MODE=$mode; use single, combined, or separate" >&2',
                "    exit 1",
                "    ;;",
                "esac",
                'for cfg in "${configs[@]}"; do',
                '  [[ -f "$cfg" ]] || continue',
                '  cfg_abs="$(readlink -f "$cfg")"',
                '  cfg_dir="$(dirname "$cfg_abs")"',
                '  (cd "$cfg_dir" && "$BIN" --ignore-running --nr "$nr" --config "$cfg_abs" --watch-config) &',
                '  pids+=("$!")',
                '  nr=$((nr + 1))',
                "done",
                'wait "${pids[@]}"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    launcher.chmod(0o755)

    write_service_file(output_dir / "neuro-hypr-pet-wayland.service", launcher)
    return launcher


def write_service_file(service: Path, launcher: Path) -> None:
    launcher = launcher.resolve()
    service.write_text(
        "\n".join(
            [
                "[Unit]",
                "Description=Neuroling native Wayland desktop pets",
                "After=graphical-session.target",
                "PartOf=graphical-session.target",
                "",
                "[Service]",
                "Type=simple",
                f"ExecStart={launcher}",
                f"ExecStop={launcher} --stop",
                "Restart=on-failure",
                "RestartSec=2",
                "",
                "[Install]",
                "WantedBy=graphical-session.target",
                "",
            ]
        ),
        encoding="utf-8",
    )


def run_command(command: list[str]) -> None:
    subprocess.run(command, check=True)


def load_set_rows(collection_dir: Path, image_set: str, max_frames: int) -> tuple[Path, list[tuple[AnimationRow, list[str]]]]:
    image_set_dir = collection_dir / "img" / image_set
    actions_xml = image_set_dir / "conf" / "actions.xml"
    if not actions_xml.is_file():
        raise FileNotFoundError(f"missing actions.xml for {image_set}: {actions_xml}")
    actions = parse_actions(actions_xml)
    return image_set_dir, choose_frames(image_set_dir, actions, max_frames)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", type=Path, default=default_collection())
    parser.add_argument("--output", type=Path, default=Path("build/neuroling-wpets"))
    parser.add_argument("--binary", type=Path, required=True, help="Path to the separately built wayland-vpets bongocat-all executable.")
    parser.add_argument("--image-set", action="append", default=[])
    parser.add_argument("--max-frames", type=int, default=8)
    parser.add_argument("--cat-height", type=int, default=112)
    parser.add_argument("--overlay-height", type=int, default=128)
    parser.add_argument("--fps", type=int, default=8)
    parser.add_argument("--input-fps", type=int, default=15)
    parser.add_argument("--animation-speed", type=int, default=420)
    parser.add_argument("--movement-radius", type=int, default=0)
    parser.add_argument("--movement-speed", type=int, default=0)
    parser.add_argument("--no-combined", action="store_true")
    parser.add_argument("--combined-spacing", type=int, default=28)
    parser.add_argument("--monitor")
    parser.add_argument("--keyboard-device", action="append", default=[])
    parser.add_argument("--no-auto-keyboard", action="store_true")
    parser.add_argument("--install-user", action="store_true")
    parser.add_argument("--start", action="store_true")
    args = parser.parse_args(argv)

    if args.max_frames < 1:
        parser.error("--max-frames must be at least 1")
    if not args.binary.is_file():
        parser.error(f"wayland-vpets binary not found: {args.binary}")

    repo_root = Path.cwd()
    image_sets = discover_image_sets(args.collection, args.image_set)
    if not image_sets:
        parser.error("no image sets found")

    args.output.mkdir(parents=True, exist_ok=True)
    count = len(image_sets)
    spacing = max(args.cat_height + 40, 160)
    start_offset = -spacing * (count - 1) // 2
    configs = []
    keyboard_devices = args.keyboard_device if args.keyboard_device else ([] if args.no_auto_keyboard else discover_keyboard_devices())
    loaded_rows = [load_set_rows(args.collection, image_set, args.max_frames) for image_set in image_sets]
    for index, image_set in enumerate(image_sets):
        configs.append(
            export_set(
                args.collection,
                args.output,
                image_set,
                max_frames=args.max_frames,
                cat_height=args.cat_height,
                overlay_height=args.overlay_height,
                x_offset=start_offset + (index * spacing),
                monitor=args.monitor,
                keyboard_devices=keyboard_devices,
                fps=args.fps,
                input_fps=args.input_fps,
                animation_speed=args.animation_speed,
                movement_radius=args.movement_radius,
                movement_speed=args.movement_speed,
            )
        )

    if not args.no_combined and loaded_rows:
        combined_dir = args.output / "All"
        combined_sprite = combined_dir / "sprite.png"
        render_combined_sprite_sheet(loaded_rows, combined_sprite, spacing=args.combined_spacing, target_height=args.cat_height)
        combined_rows: list[tuple[AnimationRow, list[str]]] = []
        for row_index, row in enumerate(ROWS):
            frames = ["combined"] * max(len(rows[row_index][1]) for _, rows in loaded_rows)
            combined_rows.append((row, frames))
        combined_config = combined_dir / "wpets.conf"
        write_config(
            combined_config,
            combined_sprite,
            combined_rows,
            cat_height=args.cat_height,
            overlay_height=args.overlay_height,
            x_offset=0,
            monitor=args.monitor,
            keyboard_devices=keyboard_devices,
            fps=args.fps,
            input_fps=args.input_fps,
            animation_speed=args.animation_speed,
            movement_radius=args.movement_radius,
            movement_speed=args.movement_speed,
        )
        configs.insert(0, combined_config)

    launcher = install_runtime_files(repo_root, args.output, args.binary)

    if args.install_user:
        config_target = Path.home() / ".config" / "neuro-hypr-pet"
        service_target = Path.home() / ".config" / "systemd" / "user" / "neuro-hypr-pet-wayland.service"
        if config_target.exists():
            shutil.rmtree(config_target)
        shutil.copytree(args.output, config_target)
        write_service_file(
            config_target / "neuro-hypr-pet-wayland.service",
            config_target / "neuro-hypr-pet-wayland",
        )
        service_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(config_target / "neuro-hypr-pet-wayland.service", service_target)
        run_command(["systemctl", "--user", "daemon-reload"])
        run_command(["systemctl", "--user", "enable", "neuro-hypr-pet-wayland.service"])
        if args.start:
            run_command(["systemctl", "--user", "restart", "neuro-hypr-pet-wayland.service"])
        print(f"Installed configs to {config_target}")
        print(f"Installed service to {service_target}")
    elif args.start:
        run_command([str(launcher)])

    for config in configs:
        print(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
