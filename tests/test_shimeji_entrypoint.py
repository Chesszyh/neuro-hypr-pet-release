import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from neuro_hypr_pet.hyprland import monitor_from_hyprctl, window_from_hyprctl
from neuro_hypr_pet.runtime import PetRuntime, Rect, RuntimeConfig
from neuro_hypr_pet.shimeji_model import load_action_catalog


class ShimejiEntrypointTest(unittest.TestCase):
    def setUp(self):
        self.preferences = tempfile.TemporaryDirectory()
        self.addCleanup(self.preferences.cleanup)
        path = Path(self.preferences.name) / "preferences.json"
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import tools.neuro_hypr_shimeji as entrypoint
        for target in ("neuro_hypr_pet.manager.preferences_path", "tools.neuro_hypr_shimeji.preferences_path"):
            patched = patch(target, return_value=path)
            patched.start()
            self.addCleanup(patched.stop)

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_carry_move_waits_for_sprite_frame_and_keeps_anchor_when_clamped(self):
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import tools.neuro_hypr_shimeji as entrypoint
        monitor = monitor_from_hyprctl({"name": "test", "width": 1600, "height": 935})
        window = window_from_hyprctl({"address": "0xabc", "at": [1500, 500], "size": [500, 400], "floating": True})
        catalog = load_action_catalog(Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml")
        runtime = PetRuntime(catalog, RuntimeConfig(work_area=monitor.work_area, start_x=1499, start_y=965))
        runtime.start_action("FallWithIe", look_right=True)
        runtime.update_active_window_rect(window.rect)
        runtime.desired_active_window_rect = window.rect
        motion = SimpleNamespace(target=window, move=Mock())
        pet = SimpleNamespace(runtime=runtime, monitors=[monitor], move_active_window=True,
                              active_window_info=window, window_motion=motion, _pending_window_move=None)
        entrypoint.SpriteLayerWindow._move_active_window_if_needed(pet)
        motion.move.assert_not_called()
        self.assertEqual(runtime.active_window_rect, Rect(1100, 500, 500, 400))
        self.assertTrue(runtime._active_window_is_attached_to_anchor())
        entrypoint.SpriteLayerWindow._after_paint(pet, None)
        motion.move.assert_called_once_with(window, runtime.active_window_rect, [monitor])
        self.assertIsNone(pet._pending_window_move)
        motion.move.reset_mock()
        pet._pending_window_move = (window, window.rect)
        runtime.start_action("Stand")
        entrypoint.SpriteLayerWindow._after_paint(pet, None)
        motion.move.assert_not_called()

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_environment_sync_keeps_nearby_unfocused_floating_window(self) -> None:
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import tools.neuro_hypr_shimeji as entrypoint

        monitor = monitor_from_hyprctl({
            "name": "eDP-1", "x": 0, "y": 0, "width": 500, "height": 300,
            "activeWorkspace": {"id": 1},
        })
        def client(address, x, width, *, floating):
            return window_from_hyprctl({
                "address": address, "at": [x, 80], "size": [width, 140],
                "workspace": {"id": 1}, "floating": floating,
            })
        floating_a = client("a", 40, 120, floating=True)
        floating_b = client("b", 300, 120, floating=True)
        focused_tiled = client("focused", 0, 500, floating=False)
        actions_xml = Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml"
        runtime = PetRuntime(
            load_action_catalog(actions_xml),
            RuntimeConfig(work_area=monitor.work_area, start_x=350, start_y=80),
        )

        with (
            patch.object(entrypoint, "load_monitors", return_value=[monitor]),
            patch.object(entrypoint, "load_windows", return_value=[floating_a, floating_b, focused_tiled]),
            patch.object(entrypoint, "active_window", return_value=focused_tiled),
        ):
            selected_active = entrypoint.sync_active_window(runtime, monitor)

        self.assertEqual(selected_active, floating_b)
        self.assertEqual(runtime.active_window_rect, Rect(300, 80, 120, 140))
        self.assertEqual(len(runtime.window_rects), 3)

    def test_default_startup_plan_uses_sprite_bounded_layer(self) -> None:
        result = subprocess.run(
            [sys.executable, "tools/neuro_hypr_shimeji.py", "--dry-run"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("mode=sprite-layer", result.stdout)
        self.assertIn("fps=25", result.stdout)
        self.assertIn("move-active-window=off", result.stdout)

    def test_dry_run_reports_explicit_active_window_move_mode(self) -> None:
        result = subprocess.run(
            [sys.executable, "tools/neuro_hypr_shimeji.py", "--dry-run", "--move-active-window"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("mode=sprite-layer", result.stdout)
        self.assertIn("move-active-window=on", result.stdout)

    def test_dry_run_reports_debug_state_mode(self) -> None:
        result = subprocess.run(
            [sys.executable, "tools/neuro_hypr_shimeji.py", "--dry-run", "--debug-state"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("debug-state=on", result.stdout)

    def test_environment_sync_due_uses_bounded_five_hz_default(self) -> None:
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import tools.neuro_hypr_shimeji as entrypoint

        synced_ticks = [tick for tick in range(1, 16) if entrypoint.environment_sync_due(tick, fps=25)]

        self.assertEqual(synced_ticks, [1, 6, 11])

    def test_screen_cover_prototype_refuses_to_start_without_explicit_ack(self) -> None:
        result = subprocess.run(
            [sys.executable, "tools/neuro_hypr_shimeji.py", "--screen-cover", "--duration", "1"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("--allow-screen-cover", result.stderr)

    def test_activate_passes_collection_to_sprite_window(self) -> None:
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import tools.neuro_hypr_shimeji as entrypoint

        created: dict[str, object] = {}

        class FakeApplication:
            def __init__(self, **_kwargs: object) -> None:
                self._callbacks = {}

            def connect(self, name: str, callback: object) -> None:
                self._callbacks[name] = callback

            def add_action(self, _action) -> None:
                pass

            def quit(self) -> None:
                pass

            def hold(self) -> None:
                pass

            def run(self, _argv: list[str]) -> int:
                self._callbacks["activate"](self)
                return 0

        class FakeWindow:
            def __init__(self, *args: object, **kwargs: object) -> None:
                self.runtime = type("Runtime", (), {})()
                created["args"] = args
                created["kwargs"] = kwargs
                created.setdefault("windows", []).append((args, kwargs))

            def start(self) -> None:
                pass

        collection = Path("/tmp/neuro-test-collection")
        catalog = object()
        monitor = object()

        with (
            patch.object(entrypoint.Gtk, "Application", FakeApplication),
            patch.object(entrypoint, "install_css"),
            patch.object(entrypoint, "load_action_catalog", return_value=catalog),
            patch.object(entrypoint, "load_behavior_catalog", return_value=None),
            patch.object(entrypoint, "select_monitor", return_value=monitor),
            patch.object(entrypoint, "load_monitors", return_value=[monitor, object()]),
            patch.object(entrypoint, "SpriteLayerWindow", FakeWindow),
            patch.object(entrypoint, "PetTray"),
            patch("neuro_hypr_pet.manager.available_image_sets", return_value=("Neuron",)),
            patch("neuro_hypr_pet.manager.load_selection", return_value=("Neuron",)),
            patch("neuro_hypr_pet.manager.select_monitor", return_value=monitor),
            patch("neuro_hypr_pet.manager.load_monitors", return_value=[monitor, object()]),
        ):
            result = entrypoint.main(["--collection", str(collection), "--duration", "0"])
            self.assertEqual(len(created["windows"]), 1)
            created["windows"].clear()
            result_all = entrypoint.main(["--collection", str(collection), "--monitor", "all"])

        self.assertEqual(result, 0)
        args = created["args"]
        self.assertEqual(args[1], collection)
        self.assertEqual(result_all, 0)
        windows = created["windows"]
        self.assertEqual(len(windows), 2)
        self.assertIs(windows[0][1]["world"], windows[1][1]["world"])

    def test_close_if_self_destructed_closes_window_only_when_event_exists(self) -> None:
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import tools.neuro_hypr_shimeji as entrypoint

        class FakeRuntime:
            def __init__(self) -> None:
                self.events = []

            def pop_self_destruct_events(self) -> list[object]:
                events = self.events
                self.events = []
                return events

        class FakeWindow:
            def __init__(self) -> None:
                self.close_count = 0

            def close(self) -> None:
                self.close_count += 1

        runtime = FakeRuntime()
        window = FakeWindow()

        self.assertFalse(entrypoint.close_if_self_destructed(runtime, window))
        runtime.events = [object()]
        self.assertTrue(entrypoint.close_if_self_destructed(runtime, window))
        self.assertFalse(entrypoint.close_if_self_destructed(runtime, window))
        self.assertEqual(window.close_count, 1)

    def test_configure_runtime_from_breed_applies_child_anchor_and_behavior(self) -> None:
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import tools.neuro_hypr_shimeji as entrypoint

        class FakeRuntime:
            def __init__(self) -> None:
                self.anchor_x = 0
                self.anchor_y = 0
                self.look_right = False
                self.catalog = SimpleNamespace(actions={"BornAction": object(), "Stand": object()})
                self.started = None

            def start_action(self, name: str) -> None:
                self.started = name

        runtime = FakeRuntime()
        event = SimpleNamespace(anchor_x=144, anchor_y=252, look_right=True, behavior="BornAction")

        entrypoint.configure_runtime_from_breed(runtime, event)

        self.assertEqual((runtime.anchor_x, runtime.anchor_y), (144, 252))
        self.assertTrue(runtime.look_right)
        self.assertEqual(runtime.started, "BornAction")

    def test_apply_interaction_event_applies_target_behavior_and_look(self) -> None:
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import tools.neuro_hypr_shimeji as entrypoint

        class FakeRuntime:
            def __init__(self) -> None:
                self.look_right = True
                self.catalog = SimpleNamespace(actions={"TargetAction": object(), "Stand": object()})
                self.started = None

            def start_action(self, name: str) -> None:
                self.started = name

        target = FakeRuntime()
        event = SimpleNamespace(
            target=target,
            target_behavior="TargetAction",
            target_look=True,
            source_look_right=True,
        )

        entrypoint.apply_interaction_event(event)

        self.assertFalse(target.look_right)
        self.assertEqual(target.started, "TargetAction")

    def test_pet_world_for_application_reuses_one_world(self) -> None:
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import tools.neuro_hypr_shimeji as entrypoint

        application = SimpleNamespace()

        first = entrypoint.pet_world_for_application(application)
        second = entrypoint.pet_world_for_application(application)

        self.assertIs(first, second)

    def test_surface_cache_uses_transparent_surface_for_pose_without_image(self) -> None:
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import tools.neuro_hypr_shimeji as entrypoint
            from neuro_hypr_pet.shimeji_model import PoseFrame

        with tempfile.TemporaryDirectory() as tmp:
            cache = entrypoint.SurfaceCache(Path(tmp))
            frame = PoseFrame(image="", anchor_x=0, anchor_y=0, velocity_x=0, velocity_y=0, duration=15)

            surface = cache.get(frame)

        self.assertEqual(surface.get_width(), 1)
        self.assertEqual(surface.get_height(), 1)

    def test_remember_window_keeps_multiple_window_references(self) -> None:
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import tools.neuro_hypr_shimeji as entrypoint

        application = SimpleNamespace()
        first = object()
        second = object()

        entrypoint.remember_window(application, first)
        entrypoint.remember_window(application, second)

        self.assertEqual(application._neuro_hypr_shimeji_windows, [first, second])

    def test_forget_window_removes_only_selected_pet_and_quits_after_last_one(self) -> None:
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import tools.neuro_hypr_shimeji as entrypoint

        class FakeApplication:
            def __init__(self) -> None:
                self.quit_count = 0

            def quit(self) -> None:
                self.quit_count += 1

        application = FakeApplication()
        first = object()
        second = object()
        entrypoint.remember_window(application, first)
        entrypoint.remember_window(application, second)
        application._neuro_hypr_shimeji_window = first

        entrypoint.forget_window(application, second)
        self.assertEqual(application._neuro_hypr_shimeji_windows, [first])
        self.assertEqual(application.quit_count, 0)
        entrypoint.forget_window(application, first)
        self.assertEqual(application._neuro_hypr_shimeji_windows, [])
        self.assertIsNone(application._neuro_hypr_shimeji_window)
        self.assertEqual(application.quit_count, 1)

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection/img/Neuron/conf/actions.xml").is_file(), "Requires the optional extended collection")
    def test_summon_companion_creates_one_pet_beside_current_pet(self) -> None:
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import tools.neuro_hypr_shimeji as entrypoint

        class FakeChild:
            def __init__(self, application, collection, catalog, monitor, fps, behaviors, **kwargs) -> None:
                self.runtime = SimpleNamespace(catalog=catalog, anchor_x=0, anchor_y=0, start_action=lambda name: None)
                kwargs["world"].register(self.runtime)
                self.started = False

            def _apply_geometry(self) -> None:
                pass

            def start(self) -> None:
                self.started = True

        class FakeParent:
            def __init__(self) -> None:
                self.collection = Path(__file__).resolve().parents[1] / "refs/The-Neuroling-Collection"
                self.monitor = monitor_from_hyprctl({"name": "test", "width": 800, "height": 600})
                self.runtime = SimpleNamespace(anchor_x=400)
                self.world = entrypoint.PetWorld()
                self.application = SimpleNamespace()
                self.menu_popover = SimpleNamespace(popdown=lambda: None)
                self.fps = 25
                self.move_active_window = False
                self.debug_state = False

            def get_application(self):
                return self.application

            def _image_set_exists(self, image_set: str) -> bool:
                return (self.collection / "img" / image_set / "conf" / "actions.xml").is_file()

        parent = FakeParent()
        summon = entrypoint.SpriteLayerWindow._on_summon_companion
        with patch.object(entrypoint, "SpriteLayerWindow", FakeChild):
            summon(parent, None, "Eviling")
            summon(parent, None, "Eviling")

        self.assertEqual(parent.world.total_count(), 1)
        child = parent.application._neuro_hypr_shimeji_windows[0]
        self.assertEqual((child.runtime.anchor_x, child.runtime.anchor_y), (560, 600))
        self.assertTrue(child.started)

    def test_sync_drag_cursor_polls_global_cursor_only_while_dragging(self) -> None:
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import tools.neuro_hypr_shimeji as entrypoint

        class FakeRuntime:
            def __init__(self) -> None:
                self.dragging = False
                self.calls: list[tuple[str, int, int]] = []

            def update_cursor_pos(self, x: int, y: int) -> None:
                self.calls.append(("update", x, y))

            def pointer_motion(self, x: int, y: int) -> bool:
                self.calls.append(("motion", x, y))
                return True

        runtime = FakeRuntime()
        monitor = object()

        with (
            patch.object(entrypoint, "cursor_pos", return_value=SimpleNamespace(x=210, y=180)) as raw_cursor,
        ):
            self.assertFalse(entrypoint.sync_drag_cursor(runtime, monitor))
            runtime.dragging = True
            self.assertTrue(entrypoint.sync_drag_cursor(runtime, monitor))

        self.assertEqual(raw_cursor.call_count, 1)
        self.assertEqual(runtime.calls, [("update", 210, 180), ("motion", 210, 180)])

    def test_drag_motion_uses_global_cursor_to_avoid_window_relative_feedback(self) -> None:
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import tools.neuro_hypr_shimeji as entrypoint

        class FakeRuntime:
            dragging = True
            pointer_active = True

            def __init__(self) -> None:
                self.calls: list[tuple[str, int, int]] = []

            def update_cursor_pos(self, x: int, y: int) -> None:
                self.calls.append(("update", x, y))

            def pointer_motion(self, x: int, y: int) -> bool:
                self.calls.append(("motion", x, y))
                return True

        class FakeArea:
            def __init__(self) -> None:
                self.queued = 0

            def queue_draw(self) -> None:
                self.queued += 1

        class FakeWindow:
            def __init__(self) -> None:
                self.runtime = FakeRuntime()
                self.area = FakeArea()
                self.monitor = object()
                self._last_geometry = SimpleNamespace(window_rect=Rect(100, 200, 128, 128))
                self.geometry_applied = 0

            def _apply_geometry(self) -> None:
                self.geometry_applied += 1

            def _refresh_sprite(self) -> None:
                self._apply_geometry()
                self.area.queue_draw()

            def _cursor_screen_pos(self, fallback_x: float, fallback_y: float) -> tuple[int, int]:
                return entrypoint.SpriteLayerWindow._cursor_screen_pos(self, fallback_x, fallback_y)

            def _screen_pos(self, x: float, y: float) -> tuple[int, int]:
                return entrypoint.SpriteLayerWindow._screen_pos(self, x, y)

        window = FakeWindow()
        with (
            patch.object(entrypoint, "cursor_pos", return_value=SimpleNamespace(x=210, y=180)) as raw_cursor,
        ):
            entrypoint.SpriteLayerWindow._on_motion(window, None, 12.8, 34.2)
            window._last_geometry = SimpleNamespace(window_rect=Rect(500, 600, 128, 128))
            entrypoint.SpriteLayerWindow._on_motion(window, None, 12.8, 34.2)

        self.assertEqual(raw_cursor.call_count, 2)
        self.assertEqual(
            window.runtime.calls,
            [("update", 210, 180), ("motion", 210, 180), ("update", 210, 180), ("motion", 210, 180)],
        )
        self.assertEqual(window.geometry_applied, 2)
        self.assertEqual(window.area.queued, 2)

    def test_format_runtime_state_includes_motion_and_layer_rect(self) -> None:
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import tools.neuro_hypr_shimeji as entrypoint

        runtime = SimpleNamespace(
            action_name="Run",
            anchor_x=966,
            anchor_y=1080,
            target_x=1824,
            target_y=None,
            velocity_x=0.0,
            velocity_y=0.0,
            look_right=True,
            dragging=False,
            frame=SimpleNamespace(image="run1.png"),
        )

        state = entrypoint.format_runtime_state(runtime, Rect(902, 952, 128, 128), ticks=25)

        self.assertIn("tick=25", state)
        self.assertIn("action=Run", state)
        self.assertIn("anchor=966,1080", state)
        self.assertIn("target=1824,None", state)
        self.assertIn("look=right", state)
        self.assertIn("frame=run1.png", state)
        self.assertIn("rect=902,952,128,128", state)

    def test_sprite_layer_geometry_clips_partially_offscreen_sprite_to_visible_window(self) -> None:
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import tools.neuro_hypr_shimeji as entrypoint

        output = Rect(0, 0, 2560, 1600)

        left_edge = entrypoint.clip_sprite_layer_geometry(Rect(-64, 1472, 128, 128), output)
        right_edge = entrypoint.clip_sprite_layer_geometry(Rect(2496, 1472, 128, 128), output)

        self.assertEqual(left_edge.window_rect, Rect(0, 1472, 64, 128))
        self.assertEqual((left_edge.draw_x, left_edge.draw_y), (-64, 0))
        self.assertEqual(right_edge.window_rect, Rect(2496, 1472, 64, 128))
        self.assertEqual((right_edge.draw_x, right_edge.draw_y), (0, 0))

    def test_sprite_layer_geometry_commits_position_change_when_surface_size_is_unchanged(self) -> None:
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import tools.neuro_hypr_shimeji as entrypoint

        class FakeSurface:
            def get_width(self) -> int:
                return 128

            def get_height(self) -> int:
                return 128

        class FakeRuntime:
            frame = object()
            look_right = False

            def __init__(self) -> None:
                self.rect = Rect(10, 20, 128, 128)

            def sprite_rect(self, _width: int, _height: int) -> Rect:
                return self.rect

        class FakeArea:
            def __init__(self) -> None:
                self.content_sizes: list[tuple[int, int]] = []

            def set_content_width(self, width: int) -> None:
                self.content_sizes.append((width, self.content_sizes[-1][1] if self.content_sizes else 0))

            def set_content_height(self, height: int) -> None:
                width = self.content_sizes[-1][0] if self.content_sizes else 0
                self.content_sizes.append((width, height))

        class FakeWindow:
            def __init__(self) -> None:
                self.runtime = FakeRuntime()
                self.area = FakeArea()
                self.monitor = monitor_from_hyprctl({"name": "test", "width": 800, "height": 600})
                self.default_sizes: list[tuple[int, int]] = []
                self.resize_count = 0

            def _sprite_local_rect(self, surface):
                return entrypoint.SpriteLayerWindow._sprite_local_rect(self, surface)

            def _current_surface(self) -> FakeSurface:
                return FakeSurface()

            def set_default_size(self, width: int, height: int) -> None:
                self.default_sizes.append((width, height))

            def _apply_input_region(self, _surface: object, _geometry: object) -> None:
                pass

            def queue_resize(self) -> None:
                self.resize_count += 1

        window = FakeWindow()
        margins: list[tuple[object, int]] = []
        with patch.object(entrypoint.Gtk4LayerShell, "set_margin", side_effect=lambda _window, edge, value: margins.append((edge, value))):
            entrypoint.SpriteLayerWindow._apply_geometry(window)
            window.resize_count = 0
            margins.clear()

            window.runtime.rect = Rect(16, 20, 128, 128)
            entrypoint.SpriteLayerWindow._apply_geometry(window)

        self.assertEqual(window.resize_count, 1)
        self.assertIn((entrypoint.Gtk4LayerShell.Edge.LEFT, 16), margins)
        self.assertIn((entrypoint.Gtk4LayerShell.Edge.TOP, 20), margins)

    def test_sprite_input_region_uses_only_visible_alpha_pixels(self) -> None:
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import cairo
            import tools.neuro_hypr_shimeji as entrypoint

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 4, 3)
        cr = cairo.Context(surface)
        cr.set_source_rgba(1, 1, 1, 1)
        cr.rectangle(0, 1, 4, 1)
        cr.fill()
        surface.flush()
        geometry = entrypoint.clip_sprite_layer_geometry(Rect(-2, 0, 4, 3), Rect(0, 0, 10, 10))

        region = entrypoint.sprite_input_region(surface, geometry)

        self.assertEqual(region.num_rectangles(), 1)
        self.assertEqual(region.get_rectangle(0), cairo.RectangleInt(0, 1, 2, 1))

    def test_sprite_input_region_mirrors_alpha_pixels_for_flipped_frames(self) -> None:
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import cairo
            import tools.neuro_hypr_shimeji as entrypoint

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 4, 1)
        cr = cairo.Context(surface)
        cr.set_source_rgba(1, 1, 1, 1)
        cr.rectangle(0, 0, 1, 1)
        cr.fill()
        surface.flush()
        geometry = entrypoint.clip_sprite_layer_geometry(Rect(0, 0, 4, 1), Rect(0, 0, 10, 10))

        region = entrypoint.sprite_input_region(surface, geometry, mirror=True)

        self.assertEqual(region.num_rectangles(), 1)
        self.assertEqual(region.get_rectangle(0), cairo.RectangleInt(3, 0, 1, 1))

    def test_sprite_layer_geometry_updates_surface_input_region(self) -> None:
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import tools.neuro_hypr_shimeji as entrypoint

        class FakeSurface:
            def get_width(self) -> int:
                return 128

            def get_height(self) -> int:
                return 128

        class FakeFrame:
            def needs_horizontal_flip(self, *, look_right: bool) -> bool:
                return look_right

        class FakeRuntime:
            frame = FakeFrame()
            look_right = False

            def sprite_rect(self, _width: int, _height: int) -> Rect:
                return Rect(10, 20, 128, 128)

        class FakeArea:
            def set_content_width(self, _width: int) -> None:
                pass

            def set_content_height(self, _height: int) -> None:
                pass

        class FakeGdkSurface:
            def __init__(self) -> None:
                self.regions: list[object] = []

            def set_input_region(self, region: object) -> None:
                self.regions.append(region)

        class FakeWindow:
            def __init__(self) -> None:
                self.runtime = FakeRuntime()
                self.area = FakeArea()
                self.monitor = monitor_from_hyprctl({"name": "test", "width": 800, "height": 600})
                self.gdk_surface = FakeGdkSurface()

            def _sprite_local_rect(self, surface):
                return entrypoint.SpriteLayerWindow._sprite_local_rect(self, surface)

            def _current_surface(self) -> FakeSurface:
                return FakeSurface()

            def get_surface(self) -> FakeGdkSurface:
                return self.gdk_surface

            def _apply_input_region(self, surface: object, geometry: object) -> None:
                entrypoint.SpriteLayerWindow._apply_input_region(self, surface, geometry)

            def set_default_size(self, _width: int, _height: int) -> None:
                pass

            def queue_resize(self) -> None:
                pass

        sentinel_region = object()
        window = FakeWindow()
        with (
            patch.object(entrypoint.Gtk4LayerShell, "set_margin"),
            patch.object(entrypoint, "sprite_input_region", return_value=sentinel_region),
        ):
            entrypoint.SpriteLayerWindow._apply_geometry(window)

        self.assertEqual(window.gdk_surface.regions, [sentinel_region])

    def test_sprite_layer_geometry_reuses_unchanged_input_region(self) -> None:
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import tools.neuro_hypr_shimeji as entrypoint

        class FakeFrame:
            def needs_horizontal_flip(self, *, look_right: bool) -> bool:
                return look_right

        class FakeSurface:
            def get_width(self) -> int:
                return 128

            def get_height(self) -> int:
                return 128

        class FakeRuntime:
            frame = FakeFrame()
            look_right = False

            def sprite_rect(self, _width: int, _height: int) -> Rect:
                return Rect(10, 20, 128, 128)

        class FakeArea:
            def set_content_width(self, _width: int) -> None:
                pass

            def set_content_height(self, _height: int) -> None:
                pass

        class FakeGdkSurface:
            def __init__(self) -> None:
                self.regions: list[object] = []

            def set_input_region(self, region: object) -> None:
                self.regions.append(region)

        class FakeWindow:
            def __init__(self) -> None:
                self.runtime = FakeRuntime()
                self.area = FakeArea()
                self.monitor = monitor_from_hyprctl({"name": "test", "width": 800, "height": 600})
                self.gdk_surface = FakeGdkSurface()

            def _sprite_local_rect(self, surface):
                return entrypoint.SpriteLayerWindow._sprite_local_rect(self, surface)

            def _current_surface(self) -> FakeSurface:
                return self.surface

            def get_surface(self) -> FakeGdkSurface:
                return self.gdk_surface

            def _apply_input_region(self, surface: object, geometry: object) -> None:
                entrypoint.SpriteLayerWindow._apply_input_region(self, surface, geometry)

            def set_default_size(self, _width: int, _height: int) -> None:
                pass

            def queue_resize(self) -> None:
                pass

        sentinel_region = object()
        window = FakeWindow()
        window.surface = FakeSurface()
        with (
            patch.object(entrypoint.Gtk4LayerShell, "set_margin"),
            patch.object(entrypoint, "sprite_input_region", return_value=sentinel_region) as build_region,
        ):
            entrypoint.SpriteLayerWindow._apply_geometry(window)
            entrypoint.SpriteLayerWindow._apply_geometry(window)

        self.assertEqual(build_region.call_count, 1)
        self.assertEqual(window.gdk_surface.regions, [sentinel_region])

    def test_sprite_tick_skips_static_draw_and_draws_changed_pose(self) -> None:
        with patch.dict(os.environ, {"NEURO_HYPR_SHIMEJI_PRELOADED": "1"}):
            import tools.neuro_hypr_shimeji as entrypoint

        class FakeRuntime:
            dragging = False
            pointer_active = False
            action_name = "Stand"
            window_action_active = False
            ready_for_idle = True
            action = SimpleNamespace(params={})

            def __init__(self) -> None:
                self.visual = "stand"
                self.tick_count = 0

            def tick(self) -> None:
                self.tick_count += 1
                if self.tick_count == 3:
                    self.visual = "wink"

            def advance(self, _speed) -> None:
                self.tick()

        class FakeArea:
            def __init__(self) -> None:
                self.draw_count = 0

            def queue_draw(self) -> None:
                self.draw_count += 1

        class FakeWindow:
            def __init__(self) -> None:
                self._closed = False
                self.paused = False
                self.following_cursor = False
                self.ticks = 0
                self.fps = 25
                self.runtime = FakeRuntime()
                self.window_motion = SimpleNamespace(release=lambda: None, target=None)
                self.minimize_after_throw = False
                self.monitor = object()
                self.sound_player = object()
                self.area = FakeArea()
                self.debug_state = False
                self._last_geometry = SimpleNamespace(window_rect=Rect(0, 0, 128, 128))
                self._last_visual_key = "stand"
                self.geometry_count = 0

            def _visual_key(self) -> str:
                return self.runtime.visual

            def get_application(self):
                return SimpleNamespace()

            def _apply_geometry(self) -> None:
                self.geometry_count += 1

            def _refresh_sprite(self) -> None:
                entrypoint.SpriteLayerWindow._refresh_sprite(self)

            def _apply_pending_transforms(self) -> None:
                pass

            def _apply_pending_interactions(self) -> None:
                pass

            def _apply_pending_breeds(self) -> None:
                pass

            def _sync_output(self) -> None:
                pass

            def _move_active_window_if_needed(self) -> None:
                pass

        window = FakeWindow()
        with (
            patch.object(entrypoint, "environment_sync_due", return_value=False),
            patch.object(entrypoint, "sync_drag_cursor", return_value=False),
            patch.object(entrypoint, "play_pending_sounds"),
            patch.object(entrypoint, "close_if_self_destructed", return_value=False),
            patch.object(entrypoint, "maybe_print_runtime_state"),
        ):
            self.assertTrue(entrypoint.SpriteLayerWindow._tick(window))
            self.assertTrue(entrypoint.SpriteLayerWindow._tick(window))
            self.assertEqual(window.area.draw_count, 0)
            self.assertEqual(window.geometry_count, 0)
            self.assertTrue(entrypoint.SpriteLayerWindow._tick(window))

        self.assertEqual(window.runtime.tick_count, 3)
        self.assertEqual(window.area.draw_count, 1)
        self.assertEqual(window.geometry_count, 1)


if __name__ == "__main__":
    unittest.main()
