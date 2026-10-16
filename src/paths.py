from __future__ import annotations

import os
import sys
from pathlib import Path


def application_support() -> Path:
    return Path.home() / "Library/Application Support/neuro-hypr-pet"


def default_collection() -> Path:
    if sys.platform == "darwin":
        return application_support() / "collection"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "neuro-hypr-pet/collection"


def preferences_path() -> Path:
    if sys.platform == "darwin":
        return application_support() / "preferences.json"
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "neuro-hypr-pet" / "preferences.json"
