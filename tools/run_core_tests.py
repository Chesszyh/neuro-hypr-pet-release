#!/usr/bin/env python3
"""Run the shared engine and adapter tests without GTK or a desktop session."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CORE_MODULES = (
    "assets", "hyprland", "neuroling_regressions", "neuroling_wpets", "pet_manager",
    "shimeji_model", "shimeji_runtime", "shimeji_service", "sound", "split_setting",
    "controller", "paths", "macos_coordinates", "macos_accessibility", "macos_controller", "macos_window_motion", "macos_sound", "macos_sprite", "macos_desktop", "macos_manager_ui",
)

if __name__ == "__main__":
    suite = unittest.TestSuite()
    for name in CORE_MODULES:
        suite.addTests(unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern=f"test_{name}.py"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
