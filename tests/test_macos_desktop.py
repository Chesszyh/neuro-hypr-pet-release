import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.desktop import WindowInfo

if sys.platform == 'darwin':
    from src.macos import desktop as subject


@unittest.skipUnless(sys.platform == 'darwin', 'Requires macOS bindings')
class LiveGeometryTest(unittest.TestCase):
    def setUp(self):
        self.desktop = subject.Desktop.__new__(subject.Desktop)
        self.window = WindowInfo('ax:1', 'Test', 'Test', 100, 200, 400, 300, 0, 0)
        self.desktop.backend = SimpleNamespace(mutex=threading.Lock(), snapshot=[self.window],
                                               window_ids={'ax:1': 42})

    def entry(self, x, y, width=400, height=300):
        return {subject.Q.kCGWindowNumber: 42, subject.Q.kCGWindowBounds:
                {'X': x, 'Y': y, 'Width': width, 'Height': height}}

    def test_platform_geometry_changes_without_waiting_for_ax_refresh(self):
        with patch('src.macos.accessibility.is_trusted', return_value=True):
            first = self.desktop.load_windows([self.entry(100, 200)])[0]
            second = self.desktop.load_windows([self.entry(600, 500)])[0]
            removed = self.desktop.load_windows([])
        self.assertEqual(first.address, second.address)
        self.assertEqual((second.x, second.y), (600, 500))
        self.assertEqual(removed, [])

    def test_stage_thumbnail_is_not_a_platform(self):
        with patch('src.macos.accessibility.is_trusted', return_value=True):
            self.assertEqual(self.desktop.load_windows([self.entry(15, 500, 74, 101)]), [])
