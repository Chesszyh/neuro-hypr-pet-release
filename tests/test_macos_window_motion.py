import sys
import threading
import unittest
from unittest.mock import Mock, patch

from src.runtime import Rect

if sys.platform == 'darwin':
    from src.macos import window_motion as subject


@unittest.skipUnless(sys.platform == 'darwin', 'Requires macOS bindings')
class WindowQueueTest(unittest.TestCase):
    def setUp(self):
        self.backend = subject.WindowBackend()
        self.addCleanup(self.backend.close)
        self.owner = object()
        self.target = Mock(original=Rect(0, 0, 400, 300), minimized=False)
        self.backend.registry['a'] = self.target
        self.backend.owners['a'] = self.owner

    def test_slow_move_coalesces_pending_positions(self):
        entered, release = threading.Event(), threading.Event()
        requests = []
        def move(rect):
            requests.append(rect)
            if len(requests) == 1:
                entered.set()
                self.assertTrue(release.wait(2))
            return {'actual': vars(rect)}
        self.target.move.side_effect = move
        with patch.object(subject, 'geometry', return_value=Rect(0, 0, 400, 300)):
            self.backend.move(self.owner, 'a', Rect(1, 1, 400, 300))
            self.assertTrue(entered.wait(2))
            for index in range(2, 21):
                self.backend.move(self.owner, 'a', Rect(index, index, 400, 300))
            release.set()
            self.backend.executor.submit(lambda: None).result(timeout=2)
        self.assertEqual([rect.x for rect in requests], [1, 20])
        self.assertEqual(self.target.original, Rect(0, 0, 400, 300))

    def test_release_discards_moves_waiting_behind_another_request(self):
        gate = threading.Event()
        self.backend.executor.submit(gate.wait, 2)
        self.backend.move(self.owner, 'a', Rect(20, 20, 400, 300))
        self.backend.release(self.owner, 'a')
        gate.set()
        self.backend.executor.submit(lambda: None).result(timeout=2)
        self.target.move.assert_not_called()

    def test_another_pet_cannot_claim_owned_window(self):
        window = Mock(address='a')
        with self.assertRaisesRegex(subject.AccessibilityError, '另一只'):
            self.backend.begin(object(), window)

    def test_delayed_readback_does_not_rewind_next_motion(self):
        from src.desktop import MonitorInfo, WindowInfo
        motion = subject.WindowMotion(self.backend, {})
        window = WindowInfo('a', 'Test', 'Test', 100, 100, 400, 300, 0, 0)
        self.backend.owners['a'] = motion
        motion.target = window
        self.backend.results['a'] = {'requested': vars(Rect(110, 100, 400, 300)),
                                     'actual': vars(Rect(110, 100, 400, 300))}
        with patch.object(self.backend, 'move'):
            actual = motion.move(window, Rect(130, 100, 400, 300),
                                 [MonitorInfo('screen', 0, 0, 1200, 900, 2, (0, 0, 0, 0))])
        self.assertEqual(actual.x, 130)

    def test_normal_completion_submits_final_move_before_release(self):
        gate = threading.Event()
        self.backend.executor.submit(gate.wait, 2)
        self.target.move.return_value = {'actual': vars(Rect(20, 20, 400, 300))}
        motion = subject.WindowMotion(self.backend, {})
        self.backend.owners['a'] = motion
        motion.target = Mock(address='a')
        with patch.object(subject, 'geometry', return_value=Rect(0, 0, 400, 300)):
            self.backend.move(motion, 'a', Rect(20, 20, 400, 300))
            motion.finish()
            gate.set()
            self.backend.executor.submit(lambda: None).result(timeout=2)
        self.target.move.assert_called_once_with(Rect(20, 20, 400, 300))
        self.assertNotIn('a', self.backend.owners)

    def test_same_title_windows_keep_distinct_ax_identities_on_refresh(self):
        from types import SimpleNamespace
        first = SimpleNamespace(element=object(), pid=123, minimized=False)
        second = SimpleNamespace(element=object(), pid=123, minimized=False)
        first_rect, second_rect = Rect(10, 20, 400, 300), Rect(510, 20, 400, 300)
        rects = {id(first.element): first_rect, id(second.element): second_rect}
        cg = [{subject.Q.kCGWindowOwnerPID: 123, subject.Q.kCGWindowBounds:
               {'X': rect.x, 'Y': rect.y, 'Width': rect.width, 'Height': rect.height}}
              for rect in (first_rect, second_rect)]
        def attribute(element, name):
            return False if name == 'AXFullScreen' else 'same title'
        with patch.object(subject, 'is_trusted', return_value=True), patch.object(subject.AK, 'NSRunningApplication', Mock()), patch.object(subject.WindowTarget, 'for_process', return_value=[first, second]), patch.object(subject, 'geometry', side_effect=lambda element: rects[id(element)]), patch.object(subject, 'read', side_effect=attribute):
            self.backend._refresh(cg)
            original = {window.x: window.address for window in self.backend.snapshot}
            self.backend._refresh(cg)
            refreshed = {window.x: window.address for window in self.backend.snapshot}
        self.assertEqual(len(original), 2)
        self.assertEqual(original, refreshed)
        self.assertIsNot(self.backend.registry[original[10]].element, self.backend.registry[original[510]].element)

    def test_moving_target_survives_geometry_sampling_difference(self):
        from types import SimpleNamespace
        target = SimpleNamespace(element=object(), pid=123, minimized=False)
        cg = [{subject.Q.kCGWindowOwnerPID: 123, subject.Q.kCGWindowNumber: 42,
               subject.Q.kCGWindowBounds: {'X': 10, 'Y': 20, 'Width': 400, 'Height': 300}}]
        with patch.object(subject, 'is_trusted', return_value=True), patch.object(subject.AK, 'NSRunningApplication', Mock()), patch.object(subject.WindowTarget, 'for_process', return_value=[target]), patch.object(subject, 'read', return_value=False), patch.object(subject, 'geometry', return_value=Rect(10, 20, 400, 300)) as geometry:
            self.backend._refresh(cg)
            address = self.backend.snapshot[0].address
            geometry.return_value = Rect(70, 20, 400, 300)
            self.backend._refresh(cg)
        self.assertEqual([window.address for window in self.backend.snapshot], [address])
