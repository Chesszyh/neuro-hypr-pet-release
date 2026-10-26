from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

_ORIGINAL_MODULES: dict[str, object] = {}


def _install_mock_gi():
    gi = ModuleType("gi")
    gi.require_version = lambda namespace, version: None
    gi_repo = ModuleType("gi.repository")

    class FakeWidget:
        def __init__(self, *args, **kwargs):
            self.children = []
            self.css_classes = []
            self.signals = {}
            self.active = False
            self.label = kwargs.get("label", "")
            self.sensitive = True
            self.value = 0.0
            self.selected = 0
            self.tooltip = ""
            self.child = None
            self.model = None

        def append(self, child):
            self.children.append(child)

        def remove(self, child):
            if child in self.children:
                self.children.remove(child)

        def get_first_child(self):
            return self.children[0] if self.children else None

        def add_css_class(self, cls):
            if cls not in self.css_classes:
                self.css_classes.append(cls)

        def remove_css_class(self, cls):
            if cls in self.css_classes:
                self.css_classes.remove(cls)

        def connect(self, signal, handler, *args):
            self.signals.setdefault(signal, []).append((handler, args))

        def emit(self, signal, *event_args):
            for handler, args in self.signals.get(signal, []):
                handler(self, *(event_args + args))

        def set_label(self, text):
            self.label = text

        def get_label(self):
            return self.label

        def set_active(self, val):
            self.active = bool(val)

        def get_active(self):
            return self.active

        def set_sensitive(self, val):
            self.sensitive = bool(val)

        def set_value(self, val):
            self.value = val

        def get_value(self):
            return self.value

        def set_selected(self, idx):
            self.selected = idx

        def get_selected(self):
            return self.selected

        def set_tooltip_text(self, text):
            self.tooltip = text

        def set_hexpand(self, val):
            pass

        def set_vexpand(self, val):
            pass

        def set_halign(self, val):
            pass

        def set_valign(self, val):
            pass

        def set_margin_top(self, val):
            pass

        def set_margin_bottom(self, val):
            pass

        def set_margin_start(self, val):
            pass

        def set_margin_end(self, val):
            pass

        def set_size_request(self, w, h):
            pass

        def set_pixel_size(self, size):
            self.pixel_size = size

        def set_can_shrink(self, val):
            pass

        def set_child(self, child):
            self.child = child

        def add_titled(self, child, name, title):
            self.append(child)

        def set_model(self, model):
            self.model = model

        def set_factory(self, factory):
            pass

        def set_list_factory(self, factory):
            pass

        def set_enable_search(self, val):
            pass

        def set_policy(self, h, v):
            self.policy = (h, v)

        def set_digits(self, d):
            pass

        def set_title(self, title):
            self.title = title

        def set_default_size(self, w, h):
            pass

        def set_decorated(self, val):
            pass

        def add_controller(self, controller):
            pass

        def present(self):
            pass

        def get_width(self):
            return 520

        def get_height(self):
            return 640

    class FakeGtk:
        Orientation = SimpleNamespace(VERTICAL=1, HORIZONTAL=2)
        PolicyType = SimpleNamespace(NEVER=0, AUTOMATIC=1)
        Align = SimpleNamespace(FILL=0, CENTER=1, END=2)
        FileChooserAction = SimpleNamespace(OPEN=0)
        ResponseType = SimpleNamespace(ACCEPT=1)

        Box = FakeWidget
        Label = FakeWidget
        Button = FakeWidget
        ToggleButton = FakeWidget
        CheckButton = FakeWidget
        ScrolledWindow = FakeWidget
        Stack = FakeWidget
        StackSwitcher = FakeWidget
        ApplicationWindow = FakeWidget
        Application = FakeWidget
        EventControllerKey = FakeWidget
        SignalListItemFactory = FakeWidget

        Picture = SimpleNamespace(new_for_filename=staticmethod(lambda path: FakeWidget()))
        Image = SimpleNamespace(new_from_icon_name=staticmethod(lambda name: FakeWidget()))

        class SpinButton(FakeWidget):
            @classmethod
            def new_with_range(cls, min_val, max_val, step):
                widget = cls()
                widget.min_val = min_val
                widget.max_val = max_val
                widget.step = step
                return widget

        class DropDown(FakeWidget):
            @classmethod
            def new_from_strings(cls, strings):
                w = cls()
                w.strings = list(strings)
                return w

        class StringList:
            @classmethod
            def new(cls, strings):
                sl = SimpleNamespace()
                sl.strings = list(strings)
                return sl

        class FileChooserNative(FakeWidget):
            @classmethod
            def new(cls, title, parent, action, accept, cancel):
                return cls()

            def destroy(self):
                pass

            def show(self):
                pass

        class FileFilter:
            def set_name(self, name):
                pass

            def add_pattern(self, pat):
                pass

    class FakeGdk:
        KEY_Escape = 65307

        class Display:
            @classmethod
            def get_default(cls):
                d = SimpleNamespace()
                d.get_monitors = lambda: SimpleNamespace(get_n_items=lambda: 0)
                return d

    class FakeGtk4LayerShell:
        Layer = SimpleNamespace(OVERLAY=0)
        KeyboardMode = SimpleNamespace(ON_DEMAND=0, NONE=1)
        Edge = SimpleNamespace(LEFT=0, TOP=1, RIGHT=2, BOTTOM=3)

        @staticmethod
        def init_for_window(win):
            pass

        @staticmethod
        def set_namespace(win, ns):
            pass

        @staticmethod
        def set_layer(win, layer):
            pass

        @staticmethod
        def set_exclusive_zone(win, zone):
            pass

        @staticmethod
        def set_keyboard_mode(win, mode):
            pass

        @staticmethod
        def set_anchor(win, edge, val):
            pass

        @staticmethod
        def set_margin(win, edge, val):
            pass

        @staticmethod
        def set_monitor(win, mon):
            pass

    class FakePango:
        EllipsizeMode = SimpleNamespace(END=0)

    try:
        import gi.repository.GLib as real_glib
        gi_repo.GLib = real_glib
    except Exception:
        fake_glib = ModuleType("GLib")
        fake_glib.timeout_add = lambda *args, **kwargs: 42
        fake_glib.source_remove = lambda *args, **kwargs: None
        fake_glib.Variant = lambda *args, **kwargs: None
        gi_repo.GLib = fake_glib

    try:
        import gi.repository.Gio as real_gio
        gi_repo.Gio = real_gio
    except Exception:
        gi_repo.Gio = ModuleType("Gio")

    gi_repo.Gtk = FakeGtk
    gi_repo.Gdk = FakeGdk
    gi_repo.Gtk4LayerShell = FakeGtk4LayerShell
    gi_repo.Pango = FakePango

    sys.modules["gi"] = gi
    sys.modules["gi.repository"] = gi_repo
    sys.modules["gi.repository.Gtk"] = FakeGtk
    sys.modules["gi.repository.Gdk"] = FakeGdk
    sys.modules["gi.repository.Gtk4LayerShell"] = FakeGtk4LayerShell
    sys.modules["gi.repository.Pango"] = FakePango
    sys.modules["gi.repository.Gio"] = gi_repo.Gio
    sys.modules["gi.repository.GLib"] = gi_repo.GLib


def setUpModule():
    for name in [
        "gi", "gi.repository", "gi.repository.Gtk", "gi.repository.Gdk",
        "gi.repository.Gtk4LayerShell", "gi.repository.Pango",
        "gi.repository.Gio", "gi.repository.GLib", "src.manager_ui"
    ]:
        _ORIGINAL_MODULES[name] = sys.modules.get(name)
    _install_mock_gi()
    import src.manager_ui
    importlib.reload(src.manager_ui)


def tearDownModule():
    for name, mod in _ORIGINAL_MODULES.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod
    if "src.manager_ui" in sys.modules:
        import src.manager_ui
        importlib.reload(src.manager_ui)


_install_mock_gi()
import src.manager_ui
ManagerPopup = src.manager_ui.ManagerPopup
SplitControls = src.manager_ui.SplitControls


class ManagerPopupTest(unittest.TestCase):
    def setUp(self):
        self.mock_application = MagicMock()
        self.mock_manager = MagicMock()
        self.mock_manager.application = self.mock_application
        self.mock_manager.listeners = []
        self.mock_manager.available = ("Neuron", "Neuroling", "Tuteling")
        self.mock_manager.selected = ("Neuron",)
        self.mock_manager.pets = []
        self.mock_manager.paused = False
        self.mock_manager.following = False
        self.mock_manager.allow_split = True
        self.mock_manager.split_probability = None
        self.mock_manager.fall_speed = 0.7
        self.mock_manager.window_speed = 1.5
        self.mock_manager.message = ""
        self.mock_manager.collection = Path("refs/The-Neuroling-Collection")
        self.mock_manager.interactive_windows.return_value = []

        self.popup = ManagerPopup(self.mock_manager)

    def test_initial_ui_structure(self):
        self.assertEqual(len(self.popup.material_rows), 3)
        self.assertIn("Neuron", self.popup.material_rows)
        self.assertIn("Neuroling", self.popup.material_rows)
        self.assertIn("Tuteling", self.popup.material_rows)
        self.assertEqual(self.popup.status_badge.label, "○ 桌面暂无桌宠")
        self.assertIn("neuro-badge-inactive", self.popup.status_badge.css_classes)
        self.assertEqual(self.popup.summon.label, "➕ 召唤所选 (1)")

    def test_material_selection_toggle(self):
        self.popup._toggle_selection("Neuroling")
        self.mock_manager.set_selection.assert_called_with(["Neuron", "Neuroling"])

        # Toggle already selected item
        self.popup._toggle_selection("Neuron")
        self.mock_manager.set_selection.assert_called_with([])

    def test_spawn_one(self):
        self.popup.spawn_one("Tuteling")
        self.mock_manager.spawn.assert_called_with("Tuteling")
        self.assertIn("Tuteling", self.popup.message.label)

    def test_spawn_selected_empty_shows_status(self):
        self.mock_manager.selected = ()
        self.popup.spawn_selected()
        self.mock_manager.spawn_selected.assert_not_called()
        self.assertIn("请先勾选", self.popup.message.label)

    def test_spawn_selected_calls_manager(self):
        self.mock_manager.selected = ("Neuron", "Tuteling")
        self.popup.spawn_selected()
        self.mock_manager.spawn_selected.assert_called_once()
        self.assertIn("已召唤所选角色", self.popup.message.label)

    def test_spawn_random(self):
        self.popup.spawn_random()
        self.mock_manager.spawn.assert_called_once()
        self.assertIn("随机召唤", self.popup.message.label)

    def test_remove_all_when_empty_vs_has_pets(self):
        self.mock_manager.pets = []
        self.popup.remove_all()
        self.mock_manager.remove_all.assert_not_called()
        self.assertIn("没有活跃", self.popup.message.label)

        pet_mock = MagicMock()
        self.mock_manager.pets = [pet_mock]
        self.popup.remove_all()
        self.mock_manager.remove_all.assert_called_once()
        self.assertIn("已移除全部桌面桌宠", self.popup.message.label)

    def test_fall_speed_selection(self):
        dropdown = self.popup.fall_speed_dropdown
        dropdown.selected = 0  # 0.25x
        self.popup._fall_speed_selected(dropdown, None)
        self.mock_manager.set_fall_speed.assert_called_with(0.25)
        self.assertIn("0.25×", self.popup.message.label)

    def test_refresh_updates_status_badge_and_counts(self):
        pet1 = MagicMock()
        pet1.catalog.image_set_dir.name = "Neuron"
        pet1.monitor.name = "DP-1"
        self.mock_manager.pets = [pet1]

        self.popup.refresh()
        self.assertEqual(self.popup.status_badge.label, "● 桌面活动：1 只桌宠")
        self.assertIn("neuro-badge-active", self.popup.status_badge.css_classes)
        self.assertEqual(self.popup.material_rows["Neuron"]["badge"].label, "● 1 只在桌面活动")
        self.assertEqual(self.popup.material_rows["Tuteling"]["badge"].label, "未召唤")

        # Test paused state
        self.mock_manager.paused = True
        self.popup.refresh()
        self.assertEqual(self.popup.status_badge.label, "⏸️ 已暂停：1 只桌宠")
        self.assertIn("neuro-badge-paused", self.popup.status_badge.css_classes)


if __name__ == "__main__":
    unittest.main()
