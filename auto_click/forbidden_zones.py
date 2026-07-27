"""Forbidden click-zone presets and runtime checks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ForbiddenClickError(RuntimeError):
    """Raised when an action would click inside a forbidden rectangle."""


@dataclass(frozen=True)
class Rect:
    x1: int
    y1: int
    x2: int
    y2: int

    @classmethod
    def from_any(cls, value: dict[str, Any]) -> "Rect":
        x1 = int(float(value.get("x1", 0)))
        y1 = int(float(value.get("y1", 0)))
        x2 = int(float(value.get("x2", 0)))
        y2 = int(float(value.get("y2", 0)))
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        return cls(left, top, right, bottom)

    def contains(self, x: int, y: int) -> bool:
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2

    def as_dict(self) -> dict[str, int]:
        return {"x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2}


def normalize_rects(rects: list[dict[str, Any]] | None) -> list[dict[str, int]]:
    normalized: list[dict[str, int]] = []
    for value in rects or []:
        try:
            rect = Rect.from_any(value)
        except Exception:
            continue
        if rect.x2 - rect.x1 >= 2 and rect.y2 - rect.y1 >= 2:
            normalized.append(rect.as_dict())
    return normalized


def blocked_reason(action: dict[str, Any], rects: list[dict[str, Any]] | None) -> str:
    """Return a human-readable reason if the action point is inside a forbidden rect."""
    atype = str(action.get("type", "")).lower()
    if atype not in {"click", "double_click", "tap", "move"}:
        return ""
    if "x" not in action or "y" not in action:
        return ""
    try:
        x = int(float(action["x"]))
        y = int(float(action["y"]))
    except (TypeError, ValueError):
        return ""
    for idx, value in enumerate(rects or [], start=1):
        rect = Rect.from_any(value)
        if rect.contains(x, y):
            return (
                f"point ({x},{y}) is inside forbidden zone #{idx} "
                f"[{rect.x1},{rect.y1},{rect.x2},{rect.y2}]"
            )
    return ""
