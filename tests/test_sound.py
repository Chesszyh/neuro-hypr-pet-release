import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from neuro_hypr_pet.sound import SoundEvent, SoundPlayer, resolve_sound_path


class SoundTest(unittest.TestCase):
    def test_resolve_sound_path_uses_original_search_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            collection = root / "collection"
            image_set_dir = collection / "img" / "Vedaling"
            root_sound = collection / "sound" / "knock.wav"
            set_sound = collection / "sound" / "Vedaling" / "knock.wav"
            image_sound = image_set_dir / "sound" / "knock.wav"
            for path in (root_sound, set_sound, image_sound):
                path.parent.mkdir(parents=True, exist_ok=True)

            image_sound.write_bytes(b"image")
            self.assertEqual(resolve_sound_path(collection, image_set_dir, "knock.wav"), image_sound)

            set_sound.write_bytes(b"set")
            self.assertEqual(resolve_sound_path(collection, image_set_dir, "knock.wav"), set_sound)

            root_sound.write_bytes(b"root")
            self.assertEqual(resolve_sound_path(collection, image_set_dir, "knock.wav"), root_sound)

    def test_sound_player_starts_external_player_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            collection = root / "collection"
            image_set_dir = collection / "img" / "Vedaling"
            sound = image_set_dir / "sound" / "knock.wav"
            sound.parent.mkdir(parents=True, exist_ok=True)
            sound.write_bytes(b"RIFF")
            player = SoundPlayer(collection, image_set_dir, player_command="/usr/bin/paplay")

            with patch("subprocess.Popen") as popen:
                played = player.play(SoundEvent("knock.wav", 1.0))

        self.assertTrue(played)
        popen.assert_called_once()
        command = popen.call_args.args[0]
        self.assertEqual(command[0], "/usr/bin/paplay")
        self.assertIn(str(sound), command)

    def test_sound_player_ignores_missing_sound_or_missing_player(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            collection = root / "collection"
            image_set_dir = collection / "img" / "Vedaling"
            player = SoundPlayer(collection, image_set_dir, player_command=None)

            with patch("subprocess.Popen") as popen:
                played = player.play(SoundEvent("missing.wav", 0.0))

        self.assertFalse(played)
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
