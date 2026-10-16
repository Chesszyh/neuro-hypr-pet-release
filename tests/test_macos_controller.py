import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from src.controller import PetController, load_image_set
from src.desktop import CursorPos, MonitorInfo, WindowInfo
from src.manager import PetManager
from src.runtime import PetWorld, TransformEvent, BreedEvent

XML = '''<Mascot xmlns="http://www.group-finity.com/Mascot"><ActionList>
<Action Name="Stand" Type="Stay"><Animation><Pose Image="/shime1.png" ImageAnchor="10,20" Velocity="0,0" Duration="1"/></Animation></Action>
<Action Name="Falling" Type="Embedded" Class="com.group_finity.mascot.action.Fall"><Animation><Pose Image="/shime1.png" ImageAnchor="10,20" Velocity="0,0" Duration="1"/></Animation></Action>
</ActionList></Mascot>'''
MONITOR = MonitorInfo('screen', 0, 0, 800, 600, 2, (0, 30, 0, 0))


class NativeControllerTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = self.root = Path(temp.name)
        for name in ('Neuron', 'Child'):
            folder = root / 'img' / name / 'conf'
            folder.mkdir(parents=True)
            (folder / 'actions.xml').write_text(XML)
        self.world = PetWorld()
        self.desktop = Mock()
        self.app = SimpleNamespace(_neuro_hypr_window_originals={}, quit=Mock())
        self.app.create_pet = self.create_pet
        self.manager = PetManager(self.app, root, self.create_pet, desktop=self.desktop, selection_path=root / 'preferences.json')

    def create_pet(self, name, monitor):
        catalog, behaviors = load_image_set(self.root, name)
        return PetController(self.app, self.root, catalog, monitor, behaviors, desktop=self.desktop,
                             view_factory=lambda pet: Mock(), sound_factory=lambda catalog: Mock(), world=self.world)

    def test_frames_and_pointer_preserve_shared_runtime_lifecycle(self):
        pet = self.manager.spawn('Neuron', MONITOR)
        pet.sync_environment([MONITOR], [])
        for _ in range(30):
            pet.step(CursorPos(200, 400))
        self.assertEqual(pet.ticks, 30)
        self.manager.set_paused(True)
        pet.step(CursorPos(300, 400))
        self.assertEqual(pet.ticks, 30)
        self.manager.remove_all()
        self.assertEqual(self.world.total_count(), 0)
        self.assertEqual(self.manager.pets, [])
        self.app.quit.assert_not_called()

    def test_breed_inherits_split_and_does_not_follow_transient(self):
        parent = self.manager.spawn('Neuron', MONITOR)
        parent.runtime.allow_split = False
        self.manager.set_following(True)
        parent.runtime._breed_events.append(BreedEvent('Child', 'Stand', 200, 600, True, True))
        parent.step(CursorPos(200, 400))
        child = self.manager.pets[1]
        self.assertTrue(child.transient)
        self.assertFalse(child.following_cursor)
        self.assertFalse(child.runtime.allow_split)
        self.assertEqual(child.runtime.anchor_x, 200)
        parent.step(CursorPos(200, 400))
        self.assertEqual(len(self.manager.pets), 2)

    def test_transform_keeps_world_identity_and_reloads_view(self):
        pet = self.manager.spawn('Neuron', MONITOR)
        runtime = pet.runtime
        runtime._transform_events.append(TransformEvent('Child', 'Stand'))
        pet.step(CursorPos(200, 400))
        self.assertIs(pet.runtime, runtime)
        self.assertEqual(self.world.total_count(), 1)
        self.assertEqual(pet.catalog.image_set_dir.name, 'Child')
        pet.view.clear_images.assert_called_once()

    def test_removed_monitor_recovers_pointer_and_anchor(self):
        pet = self.manager.spawn('Neuron', MONITOR)
        pet.runtime.pointer_down(400, 20, image_width=20, image_height=20)
        replacement = MonitorInfo('new', -800, -600, 800, 600, 1, (0, 30, 0, 0))
        pet.sync_environment([replacement], [])
        self.assertFalse(pet.runtime.pointer_active)
        self.assertTrue(-800 <= pet.runtime.anchor_x < 0)
        self.assertTrue(-570 <= pet.runtime.anchor_y <= 0)

    def test_render_rate_does_not_change_physics_rate(self):
        self.manager.set_fall_speed(1)
        pet = self.manager.spawn('Neuron', MONITOR)
        pet.runtime.advance = Mock()
        for _ in range(60):
            pet.step(CursorPos(200, 400), elapsed=1/60)
        self.assertEqual(pet.runtime.advance.call_count, 25)

    def test_fall_speed_can_be_saved_and_slows_falling_ticks(self):
        self.manager.set_fall_speed(.5)
        pet = self.manager.spawn('Neuron', MONITOR)
        pet.runtime.start_action('Falling')
        pet.runtime.advance = Mock()
        for _ in range(60):
            pet.step(CursorPos(200, 400), elapsed=1/60)
        self.assertEqual(pet.runtime.advance.call_count, 12)
        self.assertEqual(__import__('json').loads(self.manager.selection_path.read_text())['fall_speed'], .5)
        reloaded = PetManager(SimpleNamespace(), self.root, Mock(), desktop=self.desktop,
                              selection_path=self.manager.selection_path)
        self.assertEqual(reloaded.fall_speed, .5)

    def test_lost_window_support_starts_falling_on_next_physics_tick(self):
        pet = self.manager.spawn('Neuron', MONITOR)
        pet.window_motion.target = None
        window = WindowInfo('a', 'Test', 'Test', 100, 200, 400, 300, 0, 0)
        pet.runtime.anchor_x, pet.runtime.anchor_y = 250, 200
        pet.runtime.start_action('Stand')
        pet.sync_environment([MONITOR], [window])
        pet.sync_environment([MONITOR], [])
        pet.step(CursorPos(200, 400), elapsed=.04)
        self.assertEqual(pet.runtime.action_name, 'Falling')
        self.assertGreater(pet.runtime.anchor_y, 200)

    def test_intermediate_render_positions_move_between_physics_ticks(self):
        self.manager.set_fall_speed(1)
        pet = self.manager.spawn('Neuron', MONITOR)
        pet.window_motion.target = None
        pet.runtime.anchor_y = 100
        pet.runtime.start_action('Falling')
        pet.reset_display()
        positions = []
        for _ in range(6):
            pet.step(CursorPos(200, 400), elapsed=1/60)
            positions.append(pet.display_anchor[1])
        self.assertGreater(len(set(positions)), 3)
        self.assertEqual(positions, sorted(positions))

    def test_carried_window_stays_selected_near_another_window(self):
        from dataclasses import replace
        pet = self.manager.spawn('Neuron', MONITOR)
        pet.catalog.actions['Carry'] = replace(pet.catalog.actions['Stand'], name='Carry',
                                               params={'Class': 'test.WalkWithIE'})
        pet.runtime.start_action('Carry')
        pet.runtime.anchor_x, pet.runtime.anchor_y = 500, 500
        carried = WindowInfo('a', 'Test', 'Carried', 100, 100, 400, 300, 0, 0)
        other = WindowInfo('b', 'Test', 'Other', 400, 500, 400, 300, 0, 0)
        pet.window_motion.target = carried
        pet.runtime.active_window_rect = carried.rect
        pet.sync_environment([MONITOR], [carried, other])
        self.assertEqual(pet.runtime.active_window_rect, carried.rect)
