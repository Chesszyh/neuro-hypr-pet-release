import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from src.assets import default_collection, import_collection


ACTIONS = '''<Mascot xmlns="http://www.group-finity.com/Mascot"><ActionList>
<Action Name="Stand" Type="Stay"><Animation>
<Pose Image="/shime1.png" ImageAnchor="0,0" Velocity="0,0" Duration="1"/>
</Animation></Action></ActionList></Mascot>'''
BEHAVIORS = '''<Mascot xmlns="http://www.group-finity.com/Mascot"><BehaviorList>
<Behavior Name="Stand" Frequency="1"/></BehaviorList></Mascot>'''


class ImportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / "Neurolings v1.zip"
        self.destination = self.root / "imported"

    def archive_with(self, extra=None):
        files = {
            "Neuro Shimeji-ee (Neuroling)/conf/actions.xml": ACTIONS,
            "Neuro Shimeji-ee (Neuroling)/conf/behaviors.xml": BEHAVIORS,
            "Neuro Shimeji-ee (Neuroling)/img/Neuroling/shime1.png": b"test image",
            "Neuro Shimeji-ee (Neuroling)/img/Evil Neuroling/shime1.png": b"test image",
            "Neuro Shimeji-ee (Neuroling)/licence.txt": "Original notice",
            "Neuro Shimeji-ee (Neuroling)/Shimeji-ee.jar": b"not used",
            "Neuro Shimeji-ee (Neuroling)/error.log": "not used",
        }
        files.update(extra or {})
        with ZipFile(self.archive, "w") as archive:
            for name, contents in files.items():
                archive.writestr(name, contents)

    def test_shared_xml_imports_both_sets_and_retains_notice(self):
        self.archive_with()
        self.assertEqual(import_collection(self.archive, self.destination), ("Evil Neuroling", "Neuroling"))
        self.assertEqual((self.destination / "img/Neuroling/conf/actions.xml").read_text(), ACTIONS)
        self.assertEqual((self.destination / "licence.txt").read_text(), "Original notice")
        self.assertFalse((self.destination / "Shimeji-ee.jar").exists())
        self.assertFalse((self.destination / "error.log").exists())

    def test_per_set_xml_takes_precedence(self):
        self.archive_with({"Neuro Shimeji-ee (Neuroling)/img/Neuroling/conf/actions.xml": ACTIONS.replace('Name="Stand"', 'Name="Falling"')})
        import_collection(self.archive, self.destination)
        self.assertIn('Name="Falling"', (self.destination / "img/Neuroling/conf/actions.xml").read_text())

    def test_existing_import_is_not_overwritten(self):
        self.archive_with()
        import_collection(self.archive, self.destination)
        with self.assertRaisesRegex(ValueError, "已存在"):
            import_collection(self.archive, self.destination)
        self.assertTrue((self.destination / "licence.txt").is_file())

    def test_missing_frame_leaves_no_partial_import(self):
        self.archive_with({"Neuro Shimeji-ee (Neuroling)/conf/actions.xml": ACTIONS.replace('/shime1.png', '/missing.png')})
        with self.assertRaisesRegex(ValueError, "missing.png"):
            import_collection(self.archive, self.destination)
        self.assertFalse(self.destination.exists())

    def test_archive_cannot_write_outside_destination(self):
        self.archive_with({"../escape.txt": "outside"})
        with self.assertRaisesRegex(ValueError, "ZIP"):
            import_collection(self.archive, self.destination)
        self.assertFalse((self.root / "escape.txt").exists())
        self.assertFalse(self.destination.exists())

    def test_default_uses_xdg_data_home(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(self.root)}):
            self.assertEqual(default_collection(), self.root / "neuro-hypr-pet/collection")
