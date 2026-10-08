import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from neuro_hypr_pet.manager import PetManager
from neuro_hypr_pet.runtime import PetRuntime, Rect, RuntimeConfig
from neuro_hypr_pet.shimeji_model import load_action_catalog, load_behavior_catalog


ACTIONS = '''<Mascot xmlns="http://www.group-finity.com/Mascot"><ActionList>
<Action Name="Stand" Type="Stay"><Animation><Pose Image="/shime1.png" ImageAnchor="0,0" Velocity="0,0" Duration="1"/></Animation></Action>
<Action Name="Divide" Type="Embedded" Class="com.group_finity.mascot.action.Breed" BornBehavior="Divided"><Animation><Pose Image="/shime1.png" ImageAnchor="0,0" Velocity="0,0" Duration="1"/></Animation></Action>
<Action Name="SplitIntoTwo" Type="Sequence"><ActionReference Name="Divide"/></Action>
<Action Name="Divided" Type="Sequence"><ActionReference Name="Stand"/></Action>
<Action Name="Companion" Type="Embedded" Class="com.group_finity.mascot.action.Breed" BornBehavior="Stand" BornMascot="Other"><Animation><Pose Image="/shime1.png" ImageAnchor="0,0" Velocity="0,0" Duration="1"/></Animation></Action>
</ActionList></Mascot>'''
BEHAVIORS = '''<Mascot xmlns="http://www.group-finity.com/Mascot"><BehaviorList>
<Behavior Name="Stand" Frequency="1"/><Behavior Name="SplitIntoTwo" Frequency="1"/>
</BehaviorList></Mascot>'''


class SplitSettingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.conf = self.root / "img/Test/conf"
        self.conf.mkdir(parents=True)
        (self.conf / "actions.xml").write_text(ACTIONS)
        (self.conf / "behaviors.xml").write_text(BEHAVIORS)
        self.runtime = self.make_runtime()

    def make_runtime(self):
        return PetRuntime(load_action_catalog(self.conf / "actions.xml"), RuntimeConfig(Rect(0, 0, 800, 600), 300, 600), load_behavior_catalog(self.conf / "behaviors.xml"))

    def breed(self, action):
        self.runtime.start_action(action)
        for _ in range(10):
            self.runtime.tick()
        return self.runtime.pop_breed_events()

    def test_disable_blocks_manual_automatic_and_direct_split(self):
        self.runtime.allow_split = False
        self.assertNotIn("SplitIntoTwo", self.runtime.available_manual_behaviors())
        self.assertNotIn("SplitIntoTwo", self.runtime.available_idle_actions())
        self.assertFalse(self.runtime.start_manual_behavior("SplitIntoTwo"))
        self.assertEqual(self.breed("SplitIntoTwo"), [])
        self.assertEqual(self.breed("Divide"), [])
        self.runtime.allow_split = True
        self.assertEqual(len(self.breed("SplitIntoTwo")), 1)

    def test_original_archive_glitch_name_is_also_blocked(self):
        (self.conf / "actions.xml").write_text(ACTIONS.replace("SplitIntoTwo", "Glitch"))
        (self.conf / "behaviors.xml").write_text(BEHAVIORS.replace("SplitIntoTwo", "Glitch"))
        self.runtime = self.make_runtime()
        self.runtime.allow_split = False
        self.assertNotIn("Glitch", self.runtime.available_manual_behaviors())
        self.assertNotIn("Glitch", self.runtime.available_idle_actions())
        self.assertEqual(self.breed("Glitch"), [])
        self.runtime.allow_split = True
        self.assertEqual(len(self.breed("Glitch")), 1)

    def test_disable_filters_already_queued_split_but_keeps_companions(self):
        self.runtime.start_action("SplitIntoTwo")
        for _ in range(10):
            self.runtime.tick()
        self.assertTrue(self.runtime._breed_events)
        self.runtime.allow_split = False
        self.assertEqual(self.runtime.pop_breed_events(), [])
        self.assertEqual(self.breed("Companion")[0].image_set, "Other")

    def test_manager_applies_and_remembers_setting_for_existing_and_new_pets(self):
        path = self.root / "preferences.json"
        manager = PetManager(SimpleNamespace(), self.root, lambda *_: None, selection_path=path)
        pet = SimpleNamespace(runtime=self.runtime, transient=False)
        manager.register(pet)
        manager.set_allow_split(False)
        self.assertFalse(pet.runtime.allow_split)
        reloaded = PetManager(SimpleNamespace(), self.root, lambda *_: None, selection_path=path)
        second = SimpleNamespace(runtime=self.make_runtime(), transient=False)
        reloaded.register(second)
        self.assertFalse(second.runtime.allow_split)
        reloaded.set_allow_split(True)
        self.assertTrue(second.runtime.allow_split)
