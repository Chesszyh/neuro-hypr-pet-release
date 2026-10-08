from pathlib import Path
import unittest

from neuro_hypr_pet.runtime import PetRuntime, Rect, RuntimeConfig
from neuro_hypr_pet.shimeji_model import load_action_catalog, load_behavior_catalog


def real_runtime(image_set: str) -> PetRuntime:
    conf = Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img" / image_set / "conf"
    return PetRuntime(
        load_action_catalog(conf / "actions.xml"),
        RuntimeConfig(Rect(0, 0, 1920, 1080), 500, 1080),
        load_behavior_catalog(conf / "behaviors.xml"),
    )


@unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
class NeurolingRegressionTest(unittest.TestCase):
    def test_zero_weight_native_actions_are_manual_but_not_automatic(self) -> None:
        runtime = real_runtime("Eviling")
        self.assertIn("Jumpscare", runtime.available_manual_behaviors())
        self.assertNotIn("Jumpscare", runtime.available_idle_actions())
        self.assertTrue(runtime.start_manual_behavior("Jumpscare"))
        self.assertEqual(runtime._behavior_name, "Jumpscare")

    def test_tutel_release_preserves_broadcast_throw_speed_and_landing_sequence(self) -> None:
        runtime = real_runtime("Tuteling")
        runtime.pointer_down(500, 1060, image_width=128, image_height=128)
        runtime.pointer_motion(550, 760)
        speed = runtime._smoothed_throw_velocity()
        runtime.pointer_up(550, 760)
        self.assertEqual(runtime.action_name, "FallBroadcast")
        self.assertEqual(runtime.current_affordance(), "SayItBack")
        self.assertEqual((runtime.velocity_x, runtime.velocity_y), speed)
        self.assertTrue(runtime._sequence_queue)
        self.assertEqual(runtime._sequence_queue[0].kind, "Select")

    def test_tutel_native_throw_condition_turns_before_spawning_cursor(self) -> None:
        runtime = real_runtime("Tuteling")
        runtime.anchor_x = 100
        runtime.update_active_window_rect(Rect(400, 200, 700, 400))
        runtime.look_right = False
        runtime.start_action("ThrowIEFromLeft")
        self.assertTrue(runtime.look_right)
        self.assertEqual(runtime.action_name, "CreateCursorThrowFromLeft")

    def test_logical_not_does_not_change_not_equal_operator(self) -> None:
        runtime = real_runtime("Tuteling")
        self.assertTrue(runtime._resolve_bool_expression("${!mascot.lookRight && mascot.anchor.x != 100}"))

    def test_carry_falls_with_window_from_above_floor(self) -> None:
        runtime = real_runtime("Neuron")
        runtime.anchor_x, runtime.anchor_y = 399, 665
        runtime.update_active_window_rect(Rect(400, 300, 320, 300))
        runtime.start_action("FallWithIe", look_right=True)
        runtime.tick()
        self.assertEqual(runtime.action_name, "FallWithIe")
        self.assertGreater(runtime.anchor_y, 665)
        self.assertEqual(runtime.desired_active_window_rect.bottom, runtime.anchor_y - 65)

    def test_scripted_stand_waits_for_cursor_self_destruct(self) -> None:
        runtime = real_runtime("Tuteling Cursor")
        runtime.start_action("ThrowIEFromLeft")
        # The final Stand is timed and still has SelfDestruct queued.
        runtime._continue_sequence("Stand")
        while runtime.action_name != "Stand":
            runtime._continue_sequence("Stand")
        self.assertFalse(runtime.ready_for_idle)
        self.assertTrue(runtime._sequence_queue)
        for _ in range(110):
            runtime.tick()
        self.assertTrue(runtime.pop_self_destruct_events())


if __name__ == "__main__":
    unittest.main()
