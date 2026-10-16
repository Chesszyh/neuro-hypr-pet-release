#!/usr/bin/env python3
from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def diagnose() -> dict:
    import AppKit
    from src.macos.accessibility import is_trusted
    from src.macos.coordinates import Coordinates

    screens = list(AppKit.NSScreen.screens())
    coordinates = Coordinates(screens[0].frame().origin.y + screens[0].frame().size.height)
    def rectangle(frame):
        return vars(coordinates.rect_from_appkit(frame.origin.x, frame.origin.y, frame.size.width, frame.size.height))
    return {
        "system": platform.mac_ver()[0], "architecture": platform.machine(),
        "python": platform.python_version(), "accessibility_trusted": is_trusted(),
        "screens": [{"name": str(screen.localizedName()), "frame": rectangle(screen.frame()),
                     "work_area": rectangle(screen.visibleFrame()), "scale": screen.backingScaleFactor()}
                    for screen in screens],
    }


if __name__ == "__main__":
    print(json.dumps(diagnose(), ensure_ascii=False, indent=2))
