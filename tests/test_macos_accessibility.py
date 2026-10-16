import sys
import unittest
from unittest.mock import patch

from src.runtime import Rect

if sys.platform == "darwin":
    from src.macos import accessibility as subject


@unittest.skipUnless(sys.platform == "darwin", "Requires macOS framework bindings")
class AccessibilityTest(unittest.TestCase):
    def test_no_permission_does_not_enumerate_applications(self):
        with patch.object(subject, "is_trusted", return_value=False), patch.object(subject.AX, "AXUIElementCreateApplication") as create:
            with self.assertRaisesRegex(subject.AccessibilityError, "Accessibility"):
                subject.WindowTarget.for_process(123)
            create.assert_not_called()

    def test_move_uses_saved_element_and_reports_actual_geometry(self):
        element = object()
        original = Rect(100, 100, 400, 300)
        target = subject.WindowTarget(123, element, original, False)
        constrained = Rect(110, 110, 400, 300)
        with patch.object(subject, "settable", return_value=True), patch.object(subject, "write") as write, patch.object(subject, "geometry", return_value=constrained):
            result = target.move(Rect(110, 110, 200, 100), resize=True)
        self.assertEqual(result["actual"], vars(constrained))
        self.assertIs(write.call_args_list[0].args[0], element)
        self.assertIs(write.call_args_list[1].args[0], element)
        self.assertEqual(target.original, original)

    def test_closed_target_does_not_rebind_to_another_window(self):
        target = subject.WindowTarget(123, object(), Rect(0, 0, 400, 300), False)
        with patch.object(subject, "settable", return_value=True), patch.object(subject, "write", side_effect=subject.AccessibilityError("closed")), patch.object(subject.WindowTarget, "for_process") as enumerate_windows:
            with self.assertRaisesRegex(subject.AccessibilityError, "closed"):
                target.move(Rect(20, 20, 400, 300))
            enumerate_windows.assert_not_called()

    def test_position_not_writable_does_not_claim_movement(self):
        target = subject.WindowTarget(123, object(), Rect(0, 0, 400, 300), False)
        with patch.object(subject, "settable", return_value=False), patch.object(subject, "write") as write:
            with self.assertRaisesRegex(subject.AccessibilityError, "not writable"):
                target.move(Rect(20, 20, 400, 300))
            write.assert_not_called()

    def test_minimize_request_does_not_imply_minimized_state(self):
        target = subject.WindowTarget(123, object(), Rect(0, 0, 400, 300), False)
        with patch.object(subject, "settable", return_value=True), patch.object(subject, "write"), patch.object(subject, "read", return_value=False):
            target.minimize(True)
            self.assertFalse(target.minimized)

    def test_stage_shelf_counts_as_stashed_without_dock_minimized_flag(self):
        target = subject.WindowTarget(123, object(), Rect(100, 100, 400, 300), False, window_id=42)
        thumbnail = {subject.Q.kCGWindowNumber: 42, subject.Q.kCGWindowBounds:
                     {'X': 15, 'Y': 400, 'Width': 74, 'Height': 101}, subject.Q.kCGWindowIsOnscreen: True}
        with patch.object(subject, 'read', return_value=False), patch.object(subject, 'geometry', return_value=target.original), patch.object(subject.CF, 'CFPreferencesCopyAppValue', return_value=True), patch.object(subject.Q, 'CGWindowListCopyWindowInfo', return_value=[thumbnail]):
            self.assertTrue(target.stashed)
        with patch.object(subject, 'read', return_value=False), patch.object(subject.CF, 'CFPreferencesCopyAppValue', return_value=False):
            self.assertFalse(target.stashed)

    def test_dock_minimized_state_completes_without_stage_manager(self):
        target = subject.WindowTarget(123, object(), Rect(100, 100, 400, 300), False)
        with patch.object(subject, 'read', return_value=True), patch.object(subject.CF, 'CFPreferencesCopyAppValue') as preferences:
            self.assertTrue(target.stashed)
            preferences.assert_not_called()

    def test_unwritable_size_is_rejected_before_moving_window(self):
        target = subject.WindowTarget(123, object(), Rect(0, 0, 400, 300), False)
        with patch.object(subject, "settable", side_effect=[True, False]), patch.object(subject, "write") as write:
            with self.assertRaisesRegex(subject.AccessibilityError, "size is not writable"):
                target.move(Rect(20, 20, 500, 400), resize=True)
            write.assert_not_called()

    def test_enumeration_excludes_system_dialogs_with_window_role(self):
        standard, dialog = object(), object()
        application = object()
        def value(element, attribute):
            if element is application:
                return [standard, dialog]
            if attribute == subject.AX.kAXRoleAttribute:
                return subject.AX.kAXWindowRole
            if attribute == subject.AX.kAXSubroleAttribute:
                return subject.AX.kAXStandardWindowSubrole if element is standard else subject.AX.kAXDialogSubrole
            return False
        with patch.object(subject, 'is_trusted', return_value=True), patch.object(subject.AX, 'AXUIElementCreateApplication', return_value=application), patch.object(subject.AX, 'AXUIElementSetMessagingTimeout'), patch.object(subject, 'read', side_effect=value), patch.object(subject, 'geometry', return_value=Rect(0, 0, 400, 300)):
            targets = subject.WindowTarget.for_process(123)
        self.assertEqual(len(targets), 1)
        self.assertIs(targets[0].element, standard)
