import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.hyprland import WindowMotion, monitor_from_hyprctl, window_from_hyprctl
from src.manager import PetManager, load_selection
from src.runtime import PetRuntime, Rect, RuntimeConfig
from src.shimeji_model import load_action_catalog


COLLECTION = Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection"
MONITOR = monitor_from_hyprctl({"name": "test", "width": 1600, "height": 935, "reserved": [0, 35, 0, 0],
                              "activeWorkspace": {"id": 1}})


class FakePet:
    def __init__(self, manager, name, monitor):
        self.manager = manager
        self.catalog = load_action_catalog(COLLECTION / "img" / name / "conf/actions.xml")
        self.monitor = monitor
        self.runtime = PetRuntime(self.catalog, RuntimeConfig(work_area=monitor.global_work_area,
                                 start_x=monitor.global_work_area.left + 800, start_y=monitor.global_work_area.bottom))
        self.window_motion = WindowMotion(manager.application._neuro_hypr_window_originals)
        self.transient = False
        self.started = False
        self.request_window_interaction = Mock(return_value=True)

    def start(self):
        self.started = True

    def close(self):
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            from tools.neuro_hypr_shimeji import forget_window
        forget_window(self.manager.application, self)


@unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
class PetManagerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "preferences.json"
        self.application = SimpleNamespace(quit=Mock(), get_application_id=lambda: "test.manager")
        self.manager = PetManager(self.application, COLLECTION, lambda name, monitor: FakePet(self.manager, name, monitor),
                                  selection_path=self.path)

    def test_selection_is_remembered_including_empty_selection(self):
        self.manager.set_selection(["Neuron", "Eviling", "Neuron"])
        self.assertEqual(load_selection(self.path, self.manager.available), ("Neuron", "Eviling"))
        self.manager.set_selection([])
        self.assertEqual(load_selection(self.path, self.manager.available), ())

    def test_multiple_materials_spawn_on_each_selected_output(self):
        self.manager.monitor = "all"
        self.manager.set_selection(["Neuron", "Eviling"])
        other = monitor_from_hyprctl({"name": "second", "x": 1600, "width": 1200, "height": 900})
        with patch("src.manager.load_monitors", return_value=[MONITOR, other]):
            self.manager.spawn_selected()
        self.assertEqual([(pet.catalog.image_set_dir.name, pet.monitor.name) for pet in self.manager.pets],
                         [("Neuron", "test"), ("Neuron", "second"), ("Eviling", "test"), ("Eviling", "second")])
        self.assertTrue(all(pet.started for pet in self.manager.pets))

    def test_summoning_selected_resumes_pets_and_consumes_selection(self):
        first = self.manager.spawn("Neuron", MONITOR)
        self.manager.set_paused(True)
        self.manager.set_selection(["Neuron", "Eviling"])
        with patch("src.manager.select_monitor", return_value=MONITOR):
            self.manager.spawn_selected()
            self.manager.spawn_selected()
        self.assertFalse(self.manager.paused)
        self.assertTrue(all(not pet.paused and pet.started for pet in self.manager.pets))
        self.assertIn(first, self.manager.pets)
        self.assertEqual(len(self.manager.pets), 3)
        self.assertEqual(self.manager.selected, ())
        self.assertEqual(load_selection(self.path, self.manager.available), ())

    def test_failed_summon_keeps_only_unfinished_selections(self):
        self.manager.set_selection(["Neuron", "Eviling", "Vedaling"])
        factory = self.manager.factory
        def fail_eviling(name, monitor):
            if name == "Eviling":
                raise ValueError("Failed to load Eviling")
            return factory(name, monitor)
        self.manager.factory = fail_eviling
        with patch("src.manager.select_monitor", return_value=MONITOR):
            with self.assertRaisesRegex(ValueError, "Failed to load Eviling"):
                self.manager.spawn_selected()
        self.assertEqual(self.manager.selected, ("Eviling", "Vedaling"))
        self.assertEqual(load_selection(self.path, self.manager.available), self.manager.selected)
        self.assertEqual([pet.catalog.image_set_dir.name for pet in self.manager.pets], ["Neuron"])

    def test_last_pet_removal_keeps_manager_and_can_resummon(self):
        pet = self.manager.spawn("Neuron", MONITOR)
        self.manager.remove_all()
        self.assertEqual(self.manager.pets, [])
        self.application.quit.assert_not_called()
        self.assertIs(self.application._neuro_hypr_manager, self.manager)
        same = self.manager.resummon(pet)
        self.assertEqual(same.catalog.image_set_dir.name, "Neuron")
        self.assertEqual(self.manager.pets, [same])

    def test_window_speed_is_remembered_when_selection_changes(self):
        self.assertEqual(self.manager.window_speed, 1.5)
        self.manager.set_window_speed(2.25)
        self.manager.set_selection(["Eviling"])
        reloaded = PetManager(self.application, COLLECTION, self.manager.factory, selection_path=self.path)
        self.assertEqual(reloaded.window_speed, 2.25)
        self.assertEqual(reloaded.selected, ("Eviling",))

    def test_pause_follow_and_keep_one_apply_to_new_pets(self):
        first = self.manager.spawn("Neuron", MONITOR)
        first.runtime.update_cursor_pos(1100, 500)
        self.manager.set_following(True)
        self.assertNotEqual(first.runtime.action_name, "Stand")
        self.manager.set_paused(True)
        second = self.manager.resummon(first)
        self.assertTrue(second.paused)
        self.assertTrue(second.following_cursor)
        self.manager.keep_one(second)
        self.assertEqual(self.manager.pets, [second])
        self.manager.set_paused(False)
        self.manager.set_following(False)
        self.assertFalse(second.paused)
        self.assertEqual(second.runtime.action_name, "Stand")

    def test_follow_toggle_preserves_window_sequences_and_transient_cursors(self):
        pet = self.manager.spawn("Neuron", MONITOR)
        window = Rect(200, 500, 400, 300)
        self.assertTrue(pet.runtime.start_window_interaction(window, throw=True))
        cursor = self.manager.factory("Tuteling Cursor", MONITOR)
        cursor.transient = True
        self.assertTrue(cursor.runtime.start_window_interaction(window, throw=True, transient=True))
        self.manager.register(cursor)
        actions = [item.runtime.action_name for item in (pet, cursor)]

        for following in (True, False):
            self.manager.set_following(following)
            self.assertEqual([item.runtime.action_name for item in (pet, cursor)], actions)
            self.assertTrue(all(item.runtime.window_action_active for item in (pet, cursor)))
            self.assertFalse(cursor.following_cursor)

        self.manager.set_following(True)
        other = self.manager.factory("Tuteling Cursor", MONITOR)
        other.transient = True
        self.manager.register(other)
        self.assertFalse(other.following_cursor)

    def test_explicit_target_and_random_target_use_fresh_visible_clients(self):
        pet = self.manager.spawn("Neuron", MONITOR)
        target = window_from_hyprctl({"address": "0xabc", "at": [200, 100], "size": [600, 400],
                                     "workspace": {"id": 1}, "class": "test.window"})
        manager_window = window_from_hyprctl({"address": "0xdef", "at": [200, 100], "size": [600, 400],
                                             "workspace": {"id": 1}, "class": "test.manager"})
        with (patch("src.manager.load_monitors", return_value=[MONITOR]),
              patch("src.manager.load_windows", return_value=[manager_window, target])):
            self.manager.interact(address=target.address, throw=False, pet=pet)
            pet.request_window_interaction.assert_called_with(target, throw=False, minimize=False)
            self.manager.interact(throw=True)
            pet.request_window_interaction.assert_called_with(target, throw=True, minimize=False)
            self.manager.interact(address=target.address, throw=True, minimize=True, pet=pet)
            pet.request_window_interaction.assert_called_with(target, throw=True, minimize=True)
            with self.assertRaises(ValueError):
                self.manager.interact(address="closed-window")
        self.assertEqual(pet.request_window_interaction.call_count, 3)


@unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
class WindowInteractionPlanTest(unittest.TestCase):
    def test_speed_changes_duration_without_changing_the_throw_path(self):
        results = []
        for speed in (0.5, 1.0, 1.5, 3.0):
            runtime = PetRuntime(load_action_catalog(COLLECTION / "img/Neuron/conf/actions.xml"),
                                 RuntimeConfig(work_area=MONITOR.global_work_area, start_x=800, start_y=935))
            runtime.start_window_interaction(Rect(200, 200, 500, 400), throw=True)
            for frames in range(1000):
                runtime.advance(speed)
                if runtime.ready_for_idle:
                    break
            results.append((frames + 1, runtime.desired_active_window_rect))
            runtime.start_action("Walk", target_x=runtime.anchor_x + 100, look_right=True)
            before = runtime.anchor_x
            runtime.advance(speed)
            self.assertEqual(runtime.anchor_x - before, 2)
        self.assertTrue(all(result[1] == results[0][1] for result in results))
        self.assertTrue(all(a[0] > b[0] for a, b in zip(results, results[1:])))

    def test_real_materials_complete_carry_and_throw_in_both_directions(self):
        for path in sorted((COLLECTION / "img").glob("*/conf/actions.xml")):
            if path.parent.parent.name == "Tuteling":
                continue
            for throw in (False, True):
                for x in (200, 900):
                    with self.subTest(material=path.parent.parent.name, throw=throw, x=x):
                        runtime = PetRuntime(load_action_catalog(path), RuntimeConfig(work_area=MONITOR.global_work_area,
                                             start_x=800, start_y=935))
                        window = Rect(x, 200, 500, 400)
                        self.assertTrue(runtime.start_window_interaction(window, throw=throw))
                        seen = set()
                        for tick in range(500):
                            seen.add(runtime.action.params.get("Class", "").rsplit(".", 1)[-1])
                            runtime.tick()
                            if runtime.ready_for_idle:
                                break
                        self.assertLess(tick, 499)
                        self.assertTrue({"Jump", "FallWithIE", "WalkWithIE"} <= seen)
                        self.assertEqual("ThrowIE" in seen, throw)
                        moved = runtime.desired_active_window_rect
                        self.assertIsNotNone(moved)
                        self.assertGreater(moved.x, x) if x == 200 else self.assertLess(moved.x, x)

    def test_tutel_cursor_dismisses_after_explicit_throw(self):
        runtime = PetRuntime(load_action_catalog(COLLECTION / "img/Tuteling Cursor/conf/actions.xml"),
                             RuntimeConfig(work_area=MONITOR.global_work_area, start_x=800, start_y=935))
        self.assertTrue(runtime.start_window_interaction(Rect(200, 200, 500, 400), throw=True, transient=True))
        events = []
        for tick in range(500):
            runtime.tick()
            events.extend(runtime.pop_self_destruct_events())
            if events:
                break
        self.assertEqual(len(events), 1)


if __name__ == "__main__":
    unittest.main()
