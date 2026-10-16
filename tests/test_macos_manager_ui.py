from __future__ import annotations

import unittest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

if sys.platform == 'darwin':
    import AppKit as AK
    from src.macos.manager_ui import ManagerUI


@unittest.skipUnless(sys.platform == 'darwin', 'Requires macOS framework bindings')
class MacosManagerUITest(unittest.TestCase):
    def setUp(self):
        self.app = AK.NSApplication.sharedApplication()
        self.mock_application = MagicMock()
        self.mock_manager = MagicMock()
        self.mock_application.manager = self.mock_manager
        self.mock_application.message = ''
        self.mock_manager.available = ('Neuron', 'Neuroling', 'Tuteling')
        self.mock_manager.selected = ('Neuron',)
        self.mock_manager.pets = []
        self.mock_manager.paused = False
        self.mock_manager.following = False
        self.mock_manager.allow_split = True
        self.mock_manager.split_probability = None
        self.mock_manager.fall_speed = 0.7
        self.mock_manager.message = ''
        self.mock_application.collection = Path('refs/The-Neuroling-Collection')

        self.ui = ManagerUI.alloc().init().configure(self.mock_application)
        self.ui.refresh()

    def tearDown(self):
        self.ui.close()

    def test_initial_ui_structure(self):
        self.assertEqual(self.ui.panel.title(), 'Neuro Pet')
        self.assertTrue(self.ui._built)
        self.assertEqual(len(self.ui.material_rows), 3)
        self.assertIn('Neuron', self.ui.material_rows)
        self.assertIn('Neuroling', self.ui.material_rows)
        self.assertIn('Tuteling', self.ui.material_rows)
        self.assertEqual(self.ui.btn_spawn_sel.title(), '➕ 召唤所选 (1)')

    def test_material_selection_toggle(self):
        self.ui.toggle_selection('Neuroling')
        self.mock_manager.set_selection.assert_called_with(['Neuron', 'Neuroling'])

        # Toggle already selected
        self.ui.toggle_selection('Neuron')
        self.mock_manager.set_selection.assert_called_with([])

    def test_quick_spawn_one(self):
        self.ui.spawn_one('Tuteling')
        self.mock_manager.spawn.assert_called_with('Tuteling')
        self.assertIn('Tuteling', self.ui.message.stringValue())

    def test_spawn_selected_empty_shows_status(self):
        self.mock_manager.selected = ()
        self.ui.spawn_selected()
        self.mock_manager.spawn_selected.assert_not_called()
        self.assertIn('请先勾选', self.ui.message.stringValue())

    def test_spawn_selected_calls_manager(self):
        self.mock_manager.selected = ('Neuron', 'Tuteling')
        self.ui.spawn_selected()
        self.mock_manager.spawn_selected.assert_called_once()
        self.assertIn('已召唤所选角色', self.ui.message.stringValue())

    def test_spawn_random(self):
        self.ui.spawn_random()
        self.mock_manager.spawn.assert_called_once()
        self.assertIn('随机召唤', self.ui.message.stringValue())

    def test_remove_all_when_empty_vs_has_pets(self):
        self.mock_manager.pets = []
        self.ui.remove_all()
        self.mock_manager.remove_all.assert_not_called()
        self.assertIn('没有活跃', self.ui.message.stringValue())

        pet_mock = MagicMock()
        self.mock_manager.pets = [pet_mock]
        self.ui.remove_all()
        self.mock_manager.remove_all.assert_called_once()
        self.assertIn('已移除全部桌面桌宠', self.ui.message.stringValue())

    def test_pause_and_follow_toggles(self):
        self.ui.toggle_pause()
        self.mock_manager.set_paused.assert_called_with(True)

        self.ui.toggle_follow()
        self.mock_manager.set_following.assert_called_with(True)

    def test_restore_windows(self):
        self.mock_manager.message = '已提交窗口还原请求'
        self.ui.restore_windows()
        self.mock_manager.restore_windows.assert_called_once()
        self.assertIn('已提交窗口还原请求', self.ui.message.stringValue())

    def test_refresh_preserves_rows_when_materials_unchanged(self):
        original_rows = self.ui.material_rows
        # Add a pet
        pet = MagicMock()
        pet.catalog.image_set_dir.name = 'Neuron'
        self.mock_manager.pets = [pet]
        self.ui.refresh()

        # Same row instances should be reused
        self.assertIs(self.ui.material_rows, original_rows)
        # Badge should update to show 1 active
        self.assertIn('1 只在桌面活动', self.ui.material_rows['Neuron']['badge'].stringValue())

    def test_speed_and_probability_selectors(self):
        sender = MagicMock()
        sender.indexOfSelectedItem.return_value = 2  # 0.7x
        self.ui.fallSpeed_(sender)
        self.mock_manager.set_fall_speed.assert_called_with(0.7)

        sender.indexOfSelectedItem.return_value = 3  # 25%
        self.ui.probability_(sender)
        self.mock_manager.set_split_defaults.assert_called_with(True, 25)


if __name__ == '__main__':
    unittest.main()
