import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from src.hyprland import WindowMotion, desktop_rect, monitor_for_point, monitor_from_hyprctl, window_from_hyprctl
from src.runtime import PetRuntime, Rect, RuntimeConfig
from src.shimeji_model import load_action_catalog


def displays():
    return [
        monitor_from_hyprctl({"name": "HDMI-A-1", "width": 3840, "height": 2160, "scale": 1.2, "reserved": [0, 35, 0, 0]}),
        monitor_from_hyprctl({"name": "eDP-1", "x": 3200, "width": 2560, "height": 1600, "reserved": [0, 35, 0, 0]}),
    ]


def runtime_for(monitor):
    conf = Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml"
    if not conf.is_file():
        raise unittest.SkipTest("Requires the optional extended collection")
    return PetRuntime(load_action_catalog(conf), RuntimeConfig(monitor.global_work_area, monitor.x + 300, 700))


class MultiMonitorTest(unittest.TestCase):
    def test_fractional_scale_uses_logical_coordinates(self):
        external, internal = displays()
        self.assertEqual(external.rect, Rect(0, 0, 3200, 1800))
        self.assertEqual(internal.global_work_area, Rect(3200, 35, 2560, 1565))
        self.assertEqual(desktop_rect(displays()), Rect(0, 0, 5760, 1800))
        self.assertEqual(monitor_for_point(displays(), 3200, 100), internal)

    def test_rotated_output_swaps_dimensions_before_scaling(self):
        output = monitor_from_hyprctl({"name": "DP-1", "x": -1080, "width": 3840, "height": 2160, "scale": 2, "transform": 1})
        self.assertEqual(output.rect, Rect(-1080, 0, 1080, 1920))

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_throw_crosses_inner_seam_without_grabbing_wall(self):
        external, internal = displays()
        runtime = runtime_for(external)
        runtime.update_work_areas(tuple(m.global_work_area for m in displays()), desktop_rect(displays()))
        runtime.anchor_x = 3195
        runtime.start_action("Falling")
        runtime.velocity_x = 30
        runtime.tick()
        self.assertGreater(runtime.anchor_x, 3200)
        self.assertEqual(runtime.config.work_area, internal.global_work_area)
        self.assertEqual(runtime.action_name, "Falling")

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_throw_keeps_outer_wall_when_no_adjacent_output_at_height(self):
        external, _internal = displays()
        runtime = runtime_for(external)
        runtime.update_work_areas(tuple(m.global_work_area for m in displays()), desktop_rect(displays()))
        runtime.anchor_x, runtime.anchor_y = 3195, 1700
        runtime.start_action("Falling")
        runtime.velocity_x = 30
        runtime.tick()
        self.assertEqual(runtime.anchor_x, 3200)
        self.assertEqual(runtime.config.work_area, external.global_work_area)

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_walking_into_taller_output_falls_to_its_floor(self):
        external, internal = displays()
        runtime = runtime_for(internal)
        runtime.update_work_areas(tuple(m.global_work_area for m in displays()), desktop_rect(displays()))
        runtime.anchor_x, runtime.anchor_y = 3201, 1600
        runtime.look_right = False
        runtime.start_action("Walk")
        runtime.target_x = 3000
        runtime.tick()
        self.assertLess(runtime.anchor_x, 3200)
        self.assertEqual(runtime.config.work_area, external.global_work_area)
        self.assertEqual(runtime.action_name, "Falling")
        self.assertEqual(runtime.anchor_y, 1600)

    def entrypoint(self):
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import tools.neuro_hypr_shimeji as entrypoint
        return entrypoint

    def window(self):
        entrypoint = self.entrypoint()
        external, internal = displays()
        window = SimpleNamespace(
            monitor=internal, monitors=[external, internal], runtime=runtime_for(internal),
            _select_gdk_monitor=lambda: None, _last_visual_key="old", _last_geometry="old", _input_region_key="old",
        )
        window._sync_output = lambda: entrypoint.SpriteLayerWindow._sync_output(window)
        return window

    def test_output_switch_preserves_global_position_and_uses_local_rendering(self):
        entrypoint = self.entrypoint()
        window = self.window()
        window.runtime.anchor_x = 1000
        window._sync_output()
        self.assertEqual(window.monitor.name, "HDMI-A-1")
        self.assertEqual(window.runtime.anchor_x, 1000)
        surface = SimpleNamespace(get_width=lambda: 128, get_height=lambda: 128)
        self.assertEqual(entrypoint.SpriteLayerWindow._sprite_local_rect(window, surface), window.runtime.sprite_rect(128, 128))
        self.assertIsNone(window._last_geometry)

    def test_drag_keeps_grab_output_until_release(self):
        window = self.window()
        window.runtime.dragging = True
        window.runtime.anchor_x = 1000
        window._sync_output()
        self.assertEqual(window.monitor.name, "eDP-1")
        window.runtime.dragging = False
        window._sync_output()
        self.assertEqual(window.monitor.name, "HDMI-A-1")

    def test_unplug_recovers_pet_on_remaining_output(self):
        entrypoint = self.entrypoint()
        window = self.window()
        with patch.object(entrypoint, "load_monitors", return_value=[displays()[0]]):
            entrypoint.SpriteLayerWindow._sync_monitors(window)
        self.assertEqual(window.monitor.name, "HDMI-A-1")
        self.assertTrue(window.monitor.global_work_area.contains(window.runtime.anchor_x, window.runtime.anchor_y))

    def test_unplug_releases_drag_before_rebinding_output(self):
        entrypoint = self.entrypoint()
        window = self.window()
        window.runtime.pointer_down(3500, 690, image_width=128, image_height=128)
        window.runtime.pointer_motion(3530, 500)
        self.assertTrue(window.runtime.dragging)
        with patch.object(entrypoint, "load_monitors", return_value=[displays()[0]]):
            entrypoint.SpriteLayerWindow._sync_monitors(window)
        self.assertFalse(window.runtime.pointer_active)
        self.assertEqual(window.monitor.name, "HDMI-A-1")

    def test_layout_change_preserves_position_relative_to_output(self):
        entrypoint = self.entrypoint()
        window = self.window()
        moved = monitor_from_hyprctl({"name": "eDP-1", "width": 2560, "height": 1600, "reserved": [0, 35, 0, 0]})
        with patch.object(entrypoint, "load_monitors", return_value=[moved]):
            entrypoint.SpriteLayerWindow._sync_monitors(window)
        self.assertEqual(window.runtime.anchor_x, 300)
        self.assertEqual(window.runtime.config.work_area, moved.global_work_area)

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_window_carry_stays_bound_to_address_during_focus_change(self):
        entrypoint = self.entrypoint()
        monitor = displays()[1]
        runtime = runtime_for(monitor)
        target = window_from_hyprctl({"address": "0x1", "at": [3300, 400], "size": [300, 200], "floating": True})
        other = window_from_hyprctl({"address": "0x2", "at": [3800, 400], "size": [300, 200], "floating": True})
        runtime.update_active_window_rect(target.rect)
        runtime.start_action("ThrowIEFromLeft")
        motion = WindowMotion()
        motion.target, motion.last_rect = target, Rect(3400, 500, 300, 200)
        with (
            patch.object(entrypoint, "load_monitors", return_value=displays()),
            patch.object(entrypoint, "load_windows", return_value=[target, other]),
            patch.object(entrypoint, "active_window", return_value=other),
        ):
            selected = entrypoint.sync_active_window(runtime, monitor, motion)
        self.assertEqual(selected.address, target.address)
        self.assertEqual(runtime.active_window_rect, motion.last_rect)
        with (
            patch.object(entrypoint, "load_monitors", return_value=displays()),
            patch.object(entrypoint, "load_windows", return_value=[]),
            patch.object(entrypoint, "active_window", return_value=None),
        ):
            self.assertIsNone(entrypoint.sync_active_window(runtime, monitor, motion))
        self.assertIsNone(motion.target)
        self.assertFalse(runtime.window_action_active)


if __name__ == "__main__":
    unittest.main()
