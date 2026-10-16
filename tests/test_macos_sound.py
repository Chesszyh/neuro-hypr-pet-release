import math
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.sound import SoundEvent
if sys.platform == 'darwin':
    from src.macos import sound as subject


@unittest.skipUnless(sys.platform == 'darwin', 'Requires AVFoundation')
class NativeSoundTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_native_wav_decode(self):
        path = self.root / 'test.wav'
        with wave.open(str(path), 'wb') as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(16000)
            writer.writeframes(bytes(3200))
        player = subject.load_player(path)
        self.assertAlmostEqual(player.duration(), .1, places=3)

    def test_ogg_is_decoded_before_native_audio_loading(self):
        import numpy as np
        import soundfile as sf
        path = self.root / 'test.ogg'
        sf.write(path, np.zeros(1600, dtype='float32'), 16000, format='OGG', subtype='VORBIS')
        player = subject.load_player(path)
        self.assertAlmostEqual(player.duration(), .1, places=3)

    def test_db_volume_and_lifetime_use_shared_pool(self):
        folder = self.root / 'img' / 'Neuron'
        folder.mkdir(parents=True)
        sound = self.root / 'sound'
        sound.mkdir()
        (sound / 'test.wav').touch()
        players = []
        player = Mock()
        audio = subject.SoundPlayer(SimpleNamespace(image_set_dir=folder), players)
        with patch.object(subject, 'load_player', return_value=player):
            audio.play(SoundEvent('test.wav', -6.020599913))
        self.assertAlmostEqual(player.setVolume_.call_args.args[0], .5, places=8)
        self.assertEqual(players, [player])
