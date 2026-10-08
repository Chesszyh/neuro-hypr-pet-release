import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from neuro_hypr_pet.hyprland import Rect, WindowPlacement, monitor_from_hyprctl, window_from_hyprctl
from neuro_hypr_pet.window_effects import animate_minimize


class MinimizeEffectTest(unittest.TestCase):
    def test_window_shrinks_before_hiding_and_cancel_restores_animation(self):
        window = window_from_hyprctl({"address": "0xabc", "at": [200, 100], "size": [600, 400], "floating": True,
                                     "workspace": {"id": 3}})
        placement = WindowPlacement(window.rect, True, 3)
        monitor = monitor_from_hyprctl({"name": "test", "width": 1600, "height": 900})
        manager = SimpleNamespace(application=SimpleNamespace(_neuro_hypr_window_originals={window.address: placement}),
                                  minimizations={}, changed=Mock(), message="")
        with (patch("neuro_hypr_pet.window_effects.load_monitors", return_value=[monitor]),
              patch("neuro_hypr_pet.window_effects.load_windows", return_value=[window]),
              patch("neuro_hypr_pet.window_effects.window_move_animation_ms", return_value=700),
              patch("neuro_hypr_pet.window_effects.resize_window") as resize,
              patch("neuro_hypr_pet.window_effects.move_window_to_rect") as move,
              patch("neuro_hypr_pet.window_effects.minimize_window") as hide,
              patch("neuro_hypr_pet.window_effects.set_window_animation_disabled") as animation,
              patch("neuro_hypr_pet.window_effects.GLib.timeout_add", return_value=42) as timer,
              patch("neuro_hypr_pet.window_effects.GLib.source_remove") as remove):
            animate_minimize(window, manager, "true")
            resize.assert_called_once_with(window, 100, 80)
            move.assert_called_once_with(window, Rect(750, 820, 100, 80))
            hide.assert_not_called()
            self.assertEqual(timer.call_args.args[0], 760)
            finish = timer.call_args.args[1]
            finish()
            hide.assert_called_once_with(window, placement)
            self.assertFalse(manager.minimizations)
            self.assertEqual(animation.call_args.args, (window, "true"))
            hide.reset_mock()
            animate_minimize(window, manager, "false")
            manager.minimizations.pop(window.address)()
            remove.assert_called_once_with(42)
            self.assertEqual(animation.call_args.args, (window, "false"))
            hide.assert_not_called()


if __name__ == "__main__":
    unittest.main()
