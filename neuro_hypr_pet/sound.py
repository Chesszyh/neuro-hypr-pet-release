from __future__ import annotations

import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final


PLAYER_CANDIDATES: Final = ("paplay", "pw-play", "aplay")
_DEFAULT_PLAYER = object()


@dataclass(frozen=True)
class SoundEvent:
    name: str
    volume: float = 0.0


def resolve_sound_path(collection_root: Path, image_set_dir: Path, sound_name: str) -> Path | None:
    image_set_name = image_set_dir.name
    candidates = (
        collection_root / "sound" / sound_name,
        collection_root / "sound" / image_set_name / sound_name,
        image_set_dir / "sound" / sound_name,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def find_player_command() -> str | None:
    for candidate in PLAYER_CANDIDATES:
        command = shutil.which(candidate)
        if command:
            return command
    return None


def _paplay_volume_from_db(volume_db: float) -> int:
    linear = 65536 * math.pow(10, volume_db / 20)
    return max(0, min(65536, int(round(linear))))


class SoundPlayer:
    def __init__(
        self,
        collection_root: Path,
        image_set_dir: Path,
        *,
        player_command: str | None | object = _DEFAULT_PLAYER,
    ) -> None:
        self.collection_root = collection_root
        self.image_set_dir = image_set_dir
        self.player_command = find_player_command() if player_command is _DEFAULT_PLAYER else player_command

    def play(self, event: SoundEvent) -> bool:
        if not self.player_command:
            return False
        path = resolve_sound_path(self.collection_root, self.image_set_dir, event.name)
        if path is None:
            return False
        command = self._command(path, event)
        try:
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            return False
        return True

    def _command(self, path: Path, event: SoundEvent) -> list[str]:
        if Path(str(self.player_command)).name == "paplay":
            return [str(self.player_command), f"--volume={_paplay_volume_from_db(event.volume)}", str(path)]
        return [str(self.player_command), str(path)]
