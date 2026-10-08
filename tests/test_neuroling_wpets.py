import tempfile
import os
import subprocess
import unittest
from pathlib import Path

from PIL import Image

from tools.neuroling_wpets import (
    ROWS,
    choose_frames,
    install_runtime_files,
    parse_actions,
    render_combined_sprite_sheet,
    render_sprite_sheet,
    write_config,
)


XML = """<?xml version="1.0" encoding="UTF-8" ?>
<Mascot xmlns="http://www.group-finity.com/Mascot">
  <ActionList>
    <Action Name="Stand" Type="Stay">
      <Animation>
        <Pose Image="/stand.png" ImageAnchor="4,4" Duration="1"/>
        <Pose Duration="1"/>
      </Animation>
    </Action>
    <Action Name="Walk" Type="Move">
      <Animation>
        <Pose Image="/walk1.png" ImageAnchor="4,4" Duration="1"/>
        <Pose Image="/walk2.png" ImageAnchor="4,4" Duration="1"/>
      </Animation>
    </Action>
  </ActionList>
</Mascot>
"""


def write_png(path: Path, size: tuple[int, int], color: tuple[int, int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, color).save(path)


def make_fake_runtime(root: Path) -> Path:
    binary = root / "bongocat-all"
    binary.write_text(
        "\n".join(
            [
                "#!/usr/bin/env sh",
                'printf "%s\\n" "$*" >> "$LOG"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    binary.chmod(0o755)
    return binary


def write_launcher_configs(output: Path) -> None:
    for name in ["All", "Neuron", "Eviling"]:
        config = output / name / "wpets.conf"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text("# test\n", encoding="utf-8")


def run_launcher(launcher: Path, log: Path, **env_values: str) -> list[str]:
    env = os.environ.copy()
    env["LOG"] = str(log)
    env.update(env_values)
    subprocess.run([str(launcher)], env=env, check=True, timeout=5)
    return log.read_text(encoding="utf-8").splitlines()


class NeurolingWpetsTest(unittest.TestCase):
    def test_parse_actions_skips_poses_without_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml_path = Path(tmp) / "actions.xml"
            xml_path.write_text(XML, encoding="utf-8")

            actions = parse_actions(xml_path)

        self.assertEqual(actions["Stand"], ["stand.png"])
        self.assertEqual(actions["Walk"], ["walk1.png", "walk2.png"])

    def test_choose_frames_uses_action_then_existing_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image_set = Path(tmp)
            for name in ["stand.png", "walk1.png", "walk2.png", "shime1.png", "shime11.png", "shime20.png", "run1.png"]:
                write_png(image_set / name, (4, 4), (255, 0, 0, 255))
            rows = choose_frames(image_set, {"Stand": ["stand.png"], "Walk": ["walk1.png", "walk2.png"]}, max_frames=2)

        row_map = {row.key: frames for row, frames in rows}
        self.assertEqual(row_map["idle"], ["stand.png"])
        self.assertEqual(row_map["moving"], ["walk1.png", "walk2.png"])
        self.assertEqual(row_map["running"], ["run1.png"])

    def test_render_sprite_sheet_pads_mixed_frame_sizes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_png(root / "small.png", (2, 2), (255, 0, 0, 255))
            write_png(root / "wide.png", (4, 3), (0, 255, 0, 255))
            rows = [(type("Row", (), {"key": "idle"})(), ["small.png", "wide.png"])]
            output = root / "sprite.png"

            frame_width, frame_height, columns = render_sprite_sheet(root, rows, output)
            sheet = Image.open(output)

        self.assertEqual((frame_width, frame_height, columns), (4, 3, 2))
        self.assertEqual(sheet.size, (8, 3))
        self.assertEqual(sheet.getpixel((0, 0)), (0, 0, 0, 0))
        self.assertEqual(sheet.getpixel((1, 1)), (255, 0, 0, 255))

    def test_write_config_uses_relative_sprite_path_and_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [
                (type("Row", (), {"config_prefix": "idle"})(), ["a.png"]),
                (type("Row", (), {"config_prefix": "moving"})(), ["b.png", "c.png"]),
            ]
            config = root / "set" / "wpets.conf"
            sprite = root / "set" / "sprite.png"

            write_config(
                config,
                sprite,
                rows,
                cat_height=96,
                overlay_height=128,
                x_offset=10,
                monitor="eDP-1",
                keyboard_devices=["/dev/input/by-id/example-event-kbd"],
                fps=12,
                input_fps=20,
                animation_speed=320,
                movement_radius=0,
                movement_speed=0,
            )
            text = config.read_text(encoding="utf-8")

        self.assertIn("custom_sprite_sheet_filename=sprite.png", text)
        self.assertIn("cat_height=96", text)
        self.assertIn("fps=12", text)
        self.assertIn("input_fps=20", text)
        self.assertIn("animation_speed=320", text)
        self.assertIn("movement_radius=0", text)
        self.assertIn("custom_idle_frames=1", text)
        self.assertIn("custom_idle_row=1", text)
        self.assertIn("custom_moving_frames=2", text)
        self.assertIn("custom_moving_row=2", text)
        self.assertIn("monitor=eDP-1", text)
        self.assertIn("keyboard_device=/dev/input/by-id/example-event-kbd", text)

    def test_render_combined_sprite_sheet_composes_multiple_sets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            set_a = root / "A"
            set_b = root / "B"
            write_png(set_a / "a1.png", (4, 4), (255, 0, 0, 255))
            write_png(set_a / "a2.png", (4, 4), (200, 0, 0, 255))
            write_png(set_b / "b1.png", (2, 3), (0, 255, 0, 255))
            rows_a = [(row, ["a1.png", "a2.png"]) for row in ROWS]
            rows_b = [(row, ["b1.png"]) for row in ROWS]
            output = root / "combined.png"

            width, height, columns = render_combined_sprite_sheet([(set_a, rows_a), (set_b, rows_b)], output, spacing=1)
            sheet = Image.open(output)

        self.assertEqual((width, height, columns), (9, 4, 2))
        self.assertEqual(sheet.size, (18, 4 * len(ROWS)))
        self.assertEqual(sheet.getpixel((0, 0)), (255, 0, 0, 255))
        self.assertEqual(sheet.getpixel((6, 1)), (0, 255, 0, 255))
        self.assertEqual(sheet.getpixel((9, 0)), (200, 0, 0, 255))
        self.assertEqual(sheet.getpixel((15, 1)), (0, 255, 0, 255))

    def test_launcher_defaults_to_single_neuron_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "out"
            write_launcher_configs(output)
            launcher = install_runtime_files(root, output, make_fake_runtime(root))
            log = root / "runtime.log"

            lines = run_launcher(launcher, log)

        self.assertEqual(len(lines), 1)
        self.assertIn("/Neuron/wpets.conf", lines[0])
        self.assertNotIn("/All/wpets.conf", lines[0])
        self.assertNotIn("/Eviling/wpets.conf", lines[0])

    def test_launcher_single_mode_can_select_image_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "out"
            write_launcher_configs(output)
            launcher = install_runtime_files(root, output, make_fake_runtime(root))
            log = root / "runtime.log"

            lines = run_launcher(launcher, log, NEURO_WPETS_SET="Eviling")

        self.assertEqual(len(lines), 1)
        self.assertIn("/Eviling/wpets.conf", lines[0])

    def test_launcher_separate_mode_skips_combined_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "out"
            write_launcher_configs(output)
            launcher = install_runtime_files(root, output, make_fake_runtime(root))
            log = root / "runtime.log"

            lines = run_launcher(launcher, log, NEURO_WPETS_MODE="separate")

        self.assertEqual(len(lines), 2)
        self.assertTrue(any("/Neuron/wpets.conf" in line for line in lines))
        self.assertTrue(any("/Eviling/wpets.conf" in line for line in lines))
        self.assertFalse(any("/All/wpets.conf" in line for line in lines))

    def test_generated_service_uses_absolute_launcher_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_cwd = Path.cwd()
            os.chdir(root)
            try:
                Path("out").mkdir()
                launcher = install_runtime_files(root, Path("out"), make_fake_runtime(root))
                expected_launcher = (root / launcher).resolve() if not launcher.is_absolute() else launcher.resolve()
                service = Path("out") / "neuro-hypr-pet-wayland.service"
                text = service.read_text(encoding="utf-8")
            finally:
                os.chdir(old_cwd)

        self.assertIn(f"ExecStart={expected_launcher}", text)
        self.assertIn(f"ExecStop={expected_launcher} --stop", text)


if __name__ == "__main__":
    unittest.main()
