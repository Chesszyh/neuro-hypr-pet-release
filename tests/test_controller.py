import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from src.controller import (
    apply_pending_breeds, apply_pending_interactions, apply_pending_transforms,
    close_if_self_destructed, configure_runtime_from_breed, forget_window,
    load_image_set, make_runtime, remember_window,
)
from src.desktop import MonitorInfo
from src.manager import PetManager
from src.runtime import BreedEvent, InteractionEvent, SelfDestructEvent, TransformEvent


ACTIONS = '''<Mascot xmlns="http://www.group-finity.com/Mascot"><ActionList>
<Action Name="Stand" Type="Stay"><Animation><Pose Image="/shime1.png" ImageAnchor="10,20" Velocity="0,0" Duration="1"/></Animation></Action>
</ActionList></Mascot>'''
MONITOR = MonitorInfo("test", -800, -600, 800, 600, 2, (0, 30, 0, 0))


class ControllerTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in ("Parent", "Child"):
            conf = self.root / "img" / name / "conf"
            conf.mkdir(parents=True)
            (conf / "actions.xml").write_text(ACTIONS)
        catalog, behavior = load_image_set(self.root, "Parent")
        self.runtime = make_runtime(catalog, MONITOR, behavior)

    def test_shared_import_does_not_load_platform_ui(self):
        code = '''import sys
import src.controller
import src.manager
assert not any(name in sys.modules for name in ('gi', 'cairo', 'AppKit', 'src.hyprland'))
'''
        subprocess.run([sys.executable, "-c", code], check=True, cwd=Path(__file__).resolve().parents[1])

    def test_breed_is_consumed_once_and_keeps_parent_configuration(self):
        event = BreedEvent("Child", "Stand", -300, -50, True, True)
        self.runtime._breed_events.append(event)
        spawn = Mock()
        apply_pending_breeds(self.runtime, self.root, spawn)
        apply_pending_breeds(self.runtime, self.root, spawn)
        spawn.assert_called_once()
        received, catalog, behaviors = spawn.call_args.args
        self.assertIs(received, event)
        self.assertEqual(catalog.image_set_dir.name, "Child")
        child = make_runtime(catalog, MONITOR, behaviors)
        configure_runtime_from_breed(child, received)
        self.assertEqual((child.anchor_x, child.anchor_y, child.look_right), (-300, -50, True))

    def test_missing_breed_image_uses_current_material(self):
        self.runtime._breed_events.append(BreedEvent("Missing", "Stand", 0, 0, False, False))
        spawn = Mock()
        apply_pending_breeds(self.runtime, self.root, spawn)
        self.assertEqual(spawn.call_args.args[1].image_set_dir.name, "Parent")

    def test_transform_is_consumed_once_and_refreshes_runtime_before_view(self):
        self.runtime._transform_events.append(TransformEvent("Child", "Stand"))
        observed = []
        def changed(catalog):
            observed.append((catalog.image_set_dir.name, self.runtime.catalog.image_set_dir.name))
        apply_pending_transforms(self.runtime, self.root, changed)
        apply_pending_transforms(self.runtime, self.root, changed)
        self.assertEqual(observed, [("Child", "Child")])

    def test_interaction_only_changes_target_once(self):
        target = make_runtime(self.runtime.catalog, MONITOR)
        target.look_right = True
        self.runtime._interaction_events.append(InteractionEvent(target, "Stand", True, True))
        apply_pending_interactions(self.runtime)
        self.assertFalse(target.look_right)
        target.look_right = True
        apply_pending_interactions(self.runtime)
        self.assertTrue(target.look_right)

    def test_last_pet_removal_with_manager_stays_resident(self):
        application = SimpleNamespace(quit=Mock())
        manager = PetManager(application, self.root, Mock(), selection_path=self.root / "preferences.json", desktop=Mock())
        pet = SimpleNamespace(runtime=self.runtime, transient=False)
        remember_window(application, pet)
        forget_window(application, pet)
        forget_window(application, pet)
        self.assertEqual(manager.pets, [])
        application.quit.assert_not_called()

    def test_self_destruct_closes_once_and_unmanaged_last_pet_quits(self):
        application = SimpleNamespace(quit=Mock())
        pet = SimpleNamespace(close=Mock())
        remember_window(application, pet)
        self.runtime._self_destruct_events.append(SelfDestructEvent("SelfDestruct"))
        self.assertTrue(close_if_self_destructed(self.runtime, pet))
        self.assertFalse(close_if_self_destructed(self.runtime, pet))
        pet.close.assert_called_once()
        forget_window(application, pet)
        application.quit.assert_called_once()

    def test_explicit_preferences_path_and_injected_desktop_win(self):
        path = self.root / "isolated/preferences.json"
        backend = Mock()
        application = SimpleNamespace(quit=Mock())
        pet = SimpleNamespace(runtime=self.runtime, transient=False, start=Mock())
        manager = PetManager(application, self.root, Mock(return_value=pet), selection_path=path, desktop=backend)
        manager.spawn("Parent")
        backend.select_monitor.assert_called_once_with(None)
        manager.set_selection(["Parent"])
        self.assertTrue(path.is_file())
