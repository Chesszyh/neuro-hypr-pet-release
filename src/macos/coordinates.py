from __future__ import annotations

from dataclasses import dataclass

from src.runtime import Rect


@dataclass(frozen=True)
class Coordinates:
    primary_top: float

    def point_from_appkit(self, x: float, y: float) -> tuple[float, float]:
        return x, self.primary_top - y

    def rect_from_appkit(self, x: float, y: float, width: float, height: float) -> Rect:
        return Rect(round(x), round(self.primary_top - y - height), round(width), round(height))

    def rect_to_appkit(self, rect: Rect) -> tuple[tuple[float, float], tuple[float, float]]:
        return (rect.x, self.primary_top - rect.y - rect.height), (rect.width, rect.height)
