import os
import unittest
from pathlib import Path
from unittest.mock import patch

from src.paths import default_collection, preferences_path


class PathsTest(unittest.TestCase):
    @patch("src.paths.sys.platform", "darwin")
    @patch("src.paths.Path.home", return_value=Path("/test/home"))
    def test_macos_paths_do_not_use_linux_environment(self, home):
        with patch.dict(os.environ, {"XDG_DATA_HOME": "/linux/data", "XDG_CONFIG_HOME": "/linux/config"}):
            root = Path("/test/home/Library/Application Support/neuro-hypr-pet")
            self.assertEqual(default_collection(), root / "collection")
            self.assertEqual(preferences_path(), root / "preferences.json")

    @patch("src.paths.sys.platform", "linux")
    def test_linux_keeps_xdg_paths(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": "/linux/data", "XDG_CONFIG_HOME": "/linux/config"}):
            self.assertEqual(default_collection(), Path("/linux/data/neuro-hypr-pet/collection"))
            self.assertEqual(preferences_path(), Path("/linux/config/neuro-hypr-pet/preferences.json"))
