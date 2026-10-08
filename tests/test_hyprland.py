import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from neuro_hypr_pet.hyprland import (
    ActiveWindowMoveGuard,
    WindowMotion,
    WindowPlacement,
    CursorPos,
    active_window_rect_for_monitor,
    cursor_pos_for_monitor,
    cursor_pos,
    monitor_from_hyprctl,
    move_window_to_monitor_rect,
    floating_window_rects_for_monitor,
    window_from_hyprctl,
    minimize_window,
)
from neuro_hypr_pet.runtime import Rect


class HyprlandTest(unittest.TestCase):
    def setUp(self):
        query = patch("neuro_hypr_pet.hyprland.window_animation_disabled", return_value="false")
        setting = patch("neuro_hypr_pet.hyprland.set_window_animation_disabled")
        self.animation_query = query.start()
        self.animation_set = setting.start()
        self.addCleanup(query.stop)
        self.addCleanup(setting.stop)

    def test_motion_restores_the_windows_animation_setting_on_release(self):
        monitor = monitor_from_hyprctl({"name": "test", "width": 1600, "height": 900})
        window = window_from_hyprctl({"address": "0xabc", "at": [100, 100], "size": [600, 400], "floating": True})
        for value in ("true", "false"):
            self.animation_query.return_value = value
            self.animation_set.reset_mock()
            motion = WindowMotion()
            with (patch("neuro_hypr_pet.hyprland.move_window_to_rect"),
                  patch("neuro_hypr_pet.hyprland.load_windows", return_value=[window])):
                motion.move(window, Rect(200, 100, 600, 400), [monitor])
                motion.move(window, Rect(203, 100, 600, 400), [monitor])
                motion.release()
            self.assertEqual([call.args[1] for call in self.animation_set.call_args_list], ["1", value])
            self.assertIsNone(motion.target)

    def test_minimize_saves_original_state_for_alt_m_and_can_restore(self):
        window = window_from_hyprctl({"address": "0xabc", "at": [200, 100], "size": [600, 400], "floating": True,
                                     "workspace": {"id": 3}, "pinned": True})
        placement = WindowPlacement(Rect(100, 200, 800, 500), False, 3, True)
        monitor = monitor_from_hyprctl({"name": "test", "width": 1600, "height": 900})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "0xabc.json"
            with (patch("neuro_hypr_pet.hyprland.minimized_cache_path", return_value=path),
                  patch("neuro_hypr_pet.hyprland.set_window_floating"),
                  patch("neuro_hypr_pet.hyprland._window_dispatch") as dispatch):
                minimize_window(window, placement)
                saved = json.loads(path.read_text())
                self.assertEqual(saved["at"], [100, 200])
                self.assertEqual(saved["size"], [800, 500])
                self.assertEqual(saved["workspace"], {"name": "3"})
                self.assertFalse(saved["floating"])
                self.assertTrue(saved["pinned"])
                self.assertIn('workspace = "special:minimized", follow = false', dispatch.call_args_list[1].args[0])
                hidden = window_from_hyprctl({"address": "0xabc", "workspace": {"id": -99}, "floating": False})
                WindowMotion({window.address: placement}).restore([hidden], [monitor])
                self.assertIn('workspace = "3", follow = false', dispatch.call_args_list[-2].args[0])
                self.assertFalse(path.exists())

    def test_cursor_pos_uses_hyprland_socket_before_hyprctl_subprocess(self) -> None:
        with (
            patch("neuro_hypr_pet.hyprland._hyprctl_socket_json", return_value={"x": 3441, "y": 1280}) as socket_json,
            patch("neuro_hypr_pet.hyprland.subprocess.check_output") as check_output,
        ):
            self.assertEqual(cursor_pos(), CursorPos(3441, 1280))

        socket_json.assert_called_once_with("cursorpos")
        check_output.assert_not_called()

    def test_monitor_from_hyprctl_converts_reserved_to_local_work_area(self) -> None:
        monitor = monitor_from_hyprctl(
            {
                "name": "eDP-1",
                "x": 3200,
                "y": 0,
                "width": 2560,
                "height": 1600,
                "scale": 1,
                "reserved": [0, 35, 0, 12],
            }
        )

        self.assertEqual(monitor.work_area, Rect(0, 35, 2560, 1553))

    def test_window_from_hyprctl_reads_active_window_geometry(self) -> None:
        window = window_from_hyprctl(
            {
                "address": "0xabc",
                "at": [3206, 41],
                "size": [1203, 1553],
                "workspace": {"id": 4, "name": "4"},
                "class": "kitty",
                "title": "terminal",
                "fullscreen": 0,
            }
        )

        self.assertEqual(window.class_name, "kitty")
        self.assertEqual(window.title, "terminal")
        self.assertEqual(window.rect, Rect(3206, 41, 1203, 1553))

    def test_monitor_converts_global_window_rect_to_local_coordinates(self) -> None:
        monitor = monitor_from_hyprctl(
            {
                "name": "eDP-1",
                "x": 3200,
                "y": 0,
                "width": 2560,
                "height": 1600,
                "scale": 1,
                "reserved": [0, 35, 0, 12],
            }
        )

        local = monitor.to_local_rect(Rect(3206, 41, 1203, 1553))

        self.assertEqual(local, Rect(6, 41, 1203, 1553))

    def test_cursor_pos_for_monitor_converts_global_cursor_to_local_coordinates(self) -> None:
        monitor = monitor_from_hyprctl(
            {
                "name": "eDP-1",
                "x": 3200,
                "y": 0,
                "width": 2560,
                "height": 1600,
                "scale": 1,
                "reserved": [0, 35, 0, 12],
            }
        )

        self.assertEqual(cursor_pos_for_monitor(monitor, CursorPos(3441, 1280)), CursorPos(241, 1280))

    def test_active_window_rect_for_monitor_returns_local_non_fullscreen_window(self) -> None:
        monitor = monitor_from_hyprctl(
            {
                "name": "eDP-1",
                "x": 3200,
                "y": 0,
                "width": 2560,
                "height": 1600,
                "scale": 1,
                "reserved": [0, 35, 0, 12],
            }
        )
        window = window_from_hyprctl(
            {
                "address": "0xabc",
                "at": [3206, 41],
                "size": [1203, 800],
                "workspace": {"id": 4},
                "class": "kitty",
                "title": "terminal",
                "fullscreen": 0,
            }
        )

        self.assertEqual(active_window_rect_for_monitor(monitor, window), Rect(6, 41, 1203, 800))

    def test_active_window_rect_for_monitor_ignores_fullscreen_or_other_monitor_windows(self) -> None:
        monitor = monitor_from_hyprctl(
            {
                "name": "eDP-1",
                "x": 3200,
                "y": 0,
                "width": 2560,
                "height": 1600,
                "scale": 1,
                "reserved": [0, 35, 0, 12],
            }
        )
        fullscreen = window_from_hyprctl(
            {
                "address": "0xabc",
                "at": [3200, 0],
                "size": [2560, 1600],
                "workspace": {"id": 4},
                "class": "game",
                "title": "fullscreen",
                "fullscreen": 2,
            }
        )
        other_monitor = window_from_hyprctl(
            {
                "address": "0xdef",
                "at": [20, 40],
                "size": [1000, 900],
                "workspace": {"id": 3},
                "class": "kitty",
                "title": "other",
                "fullscreen": 0,
            }
        )

        self.assertIsNone(active_window_rect_for_monitor(monitor, fullscreen))
        self.assertIsNone(active_window_rect_for_monitor(monitor, other_monitor))

    def test_current_workspace_floating_windows_remain_available_without_focus(self) -> None:
        monitor = monitor_from_hyprctl({
            "name": "eDP-1", "x": 3200, "y": 0, "width": 2560, "height": 1600,
            "activeWorkspace": {"id": 4},
        })
        def client(address: str, x: int, workspace: int, **extra):
            return window_from_hyprctl({
                "address": address, "at": [x, 100], "size": [300, 400],
                "workspace": {"id": workspace}, "floating": True, **extra,
            })
        windows = [
            client("a", 3300, 4), client("b", 3700, 4),
            client("other-workspace", 4100, 5),
            client("hidden", 4500, 4, hidden=True),
            client("fullscreen", 4800, 4, fullscreen=2),
        ]

        self.assertEqual(
            floating_window_rects_for_monitor(monitor, windows),
            [Rect(100, 100, 300, 400), Rect(500, 100, 300, 400)],
        )

    def test_move_window_to_monitor_rect_dispatches_exact_global_position(self) -> None:
        monitor = monitor_from_hyprctl(
            {
                "name": "eDP-1",
                "x": 3200,
                "y": 0,
                "width": 2560,
                "height": 1600,
                "scale": 1,
                "reserved": [0, 35, 0, 12],
            }
        )
        window = window_from_hyprctl(
            {
                "address": "0xabc",
                "at": [3206, 41],
                "size": [1203, 800],
                "workspace": {"id": 4},
                "class": "kitty",
                "title": "terminal",
                "fullscreen": 0,
            }
        )

        with patch("neuro_hypr_pet.hyprland.subprocess.run") as run:
            run.return_value.stdout = "ok\n"
            move_window_to_monitor_rect(monitor, window, Rect(16, 51, 1203, 800))

        run.assert_called_once_with(
            ["hyprctl", "dispatch", 'hl.dsp.window.move({ window = "address:0xabc", x = 3216, y = 51 })'],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_active_window_move_guard_dispatches_only_changed_rects(self) -> None:
        monitor = monitor_from_hyprctl(
            {
                "name": "eDP-1",
                "x": 3200,
                "y": 0,
                "width": 2560,
                "height": 1600,
                "scale": 1,
                "reserved": [0, 35, 0, 12],
            }
        )
        window = window_from_hyprctl(
            {
                "address": "0xabc",
                "at": [3206, 41],
                "size": [1203, 800],
                "workspace": {"id": 4},
                "class": "kitty",
                "title": "terminal",
                "fullscreen": 0,
            }
        )
        guard = ActiveWindowMoveGuard()

        with patch("neuro_hypr_pet.hyprland.move_window_to_monitor_rect") as move:
            self.assertTrue(guard.move_if_changed(monitor, window, Rect(16, 51, 1203, 800)))
            self.assertFalse(guard.move_if_changed(monitor, window, Rect(16, 51, 1203, 800)))
            self.assertTrue(guard.move_if_changed(monitor, window, Rect(17, 51, 1203, 800)))

        self.assertEqual(move.call_count, 2)

    def test_window_motion_clamps_and_restores_unfocused_floating_target(self) -> None:
        monitor = monitor_from_hyprctl({"name": "test", "width": 1000, "height": 800, "reserved": [0, 35, 0, 0]})
        window = window_from_hyprctl({"address": "0xabc", "at": [100, 200], "size": [300, 200], "floating": True})
        originals = {}
        motion = WindowMotion(originals)
        with patch("neuro_hypr_pet.hyprland.move_window_to_rect") as move:
            self.assertEqual(motion.move(window, Rect(950, -20, 300, 200), [monitor]), Rect(700, 35, 300, 200))
            motion.move(window, Rect(950, -20, 300, 200), [monitor])
            move.assert_called_once_with(window, Rect(700, 35, 300, 200))
            # Transient cursor pets share the application's saved positions.
            WindowMotion(originals).restore([window], [monitor])
            self.assertEqual(move.call_args.args, (window, window.rect))
        self.assertEqual(originals, {})

    def test_window_motion_does_not_dispatch_to_tiled_or_fullscreen_clients(self) -> None:
        monitor = monitor_from_hyprctl({"name": "test", "width": 1000, "height": 800})
        motion = WindowMotion()
        with patch("neuro_hypr_pet.hyprland.move_window_to_rect") as move:
            for extra in ({"floating": False}, {"floating": True, "fullscreen": 1}, {"floating": True, "hidden": True}):
                window = window_from_hyprctl({"address": "0xabc", "at": [100, 200], "size": [300, 200], **extra})
                self.assertIsNone(motion.move(window, Rect(200, 300, 300, 200), [monitor]))
            move.assert_not_called()

    def test_failed_dispatch_does_not_record_a_successful_move(self) -> None:
        monitor = monitor_from_hyprctl({"name": "test", "width": 1000, "height": 800})
        window = window_from_hyprctl({"address": "0xabc", "at": [100, 200], "size": [300, 200], "floating": True})
        motion = WindowMotion()
        with patch("neuro_hypr_pet.hyprland.subprocess.run") as run:
            run.return_value.stdout = "Invalid dispatcher"
            with self.assertRaises(RuntimeError):
                motion.move(window, Rect(200, 300, 300, 200), [monitor])
        self.assertIsNone(motion.last_rect)
        self.assertEqual(motion.originals, {})

    def test_restore_returns_tiled_window_to_tiling_and_floating_size(self) -> None:
        monitor = monitor_from_hyprctl({"name": "test", "width": 1600, "height": 900})
        original = Rect(100, 100, 1000, 700)
        for was_floating, now_floating in ((True, True), (False, True), (True, False)):
            window = window_from_hyprctl({"address": "0xabc", "at": [200, 200], "size": [600, 400], "floating": now_floating})
            motion = WindowMotion({window.address: WindowPlacement(original, was_floating)})
            with (patch("neuro_hypr_pet.hyprland.resize_window") as resize,
                  patch("neuro_hypr_pet.hyprland.move_window_to_rect") as move,
                  patch("neuro_hypr_pet.hyprland.set_window_floating") as floating):
                motion.restore([window], [monitor])
                move.assert_called_once_with(window, original)
                if was_floating:
                    resize.assert_called_once_with(window, 1000, 700)
                    if now_floating:
                        floating.assert_not_called()
                    else:
                        floating.assert_called_once_with(window, True)
                else:
                    resize.assert_not_called()
                    floating.assert_called_once_with(window, False)
            self.assertEqual(motion.originals, {})


if __name__ == "__main__":
    unittest.main()
