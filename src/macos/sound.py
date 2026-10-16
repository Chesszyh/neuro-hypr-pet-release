from __future__ import annotations

import io
import math
import wave

import AVFoundation as AV
import Foundation as F

from src.sound import resolve_sound_path


class SoundPlayer:
    def __init__(self, catalog, active_players):
        self.image_set_dir = catalog.image_set_dir
        self.collection_root = catalog.image_set_dir.parent.parent
        self.active_players = active_players

    def play(self, event):
        path = resolve_sound_path(self.collection_root, self.image_set_dir, event.name)
        if path is None:
            raise ValueError(f'Sound file not found: {event.name}')
        player = load_player(path)
        player.setVolume_(max(0.0, min(1.0, math.pow(10, event.volume / 20))))
        if not player.play():
            raise ValueError(f'Cannot play sound: {path}')
        self.active_players.append(player)
        return True


def load_player(path):
    if path.suffix.lower() == '.ogg':
        import soundfile
        samples, rate = soundfile.read(path, dtype='int16', always_2d=True)
        output = io.BytesIO()
        with wave.open(output, 'wb') as writer:
            writer.setnchannels(samples.shape[1])
            writer.setsampwidth(2)
            writer.setframerate(rate)
            writer.writeframes(samples.astype('<i2').tobytes())
        data = output.getvalue()
        player, error = AV.AVAudioPlayer.alloc().initWithData_error_(F.NSData.dataWithBytes_length_(data, len(data)), None)
    else:
        player, error = AV.AVAudioPlayer.alloc().initWithContentsOfURL_error_(F.NSURL.fileURLWithPath_(str(path)), None)
    if player is None:
        raise ValueError(f'Cannot decode sound {path}: {error}')
    return player
