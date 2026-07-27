"""Execute normalized computer-use actions on the local desktop."""
from __future__ import annotations

import ctypes
import logging
import time
from contextlib import contextmanager
from typing import Callable, Optional

import pyautogui

logger = logging.getLogger(__name__)


class ActionExecutor:
    """Small adapter from model action dictionaries to pyautogui calls."""

    def __init__(
        self,
        confirm_before_execute: bool = True,
        bounds_check: bool = True,
        forbidden_rects: list[dict] | None = None,
    ):
        self.confirm_before_execute = confirm_before_execute
        self.bounds_check = bounds_check
        self.forbidden_rects = forbidden_rects or []
        self._confirm_callback: Optional[Callable[[dict], bool]] = None
        self._coordinate_frame: dict[str, int | str] | None = None

    def set_confirm_callback(self, callback: Callable[[dict], bool]) -> None:
        self._confirm_callback = callback

    def set_coordinate_frame(self, frame: dict) -> None:
        """Set the absolute desktop frame represented by the model screenshot."""
        width = int(frame.get("width", 0))
        height = int(frame.get("height", 0))
        source_width = int(frame.get("source_width", width))
        source_height = int(frame.get("source_height", height))
        if min(width, height, source_width, source_height) <= 0:
            raise ValueError(f"Invalid desktop coordinate frame: {frame!r}")
        self._coordinate_frame = {
            "mode": str(frame.get("mode", "desktop")),
            "left": int(frame.get("left", 0)),
            "top": int(frame.get("top", 0)),
            "width": width,
            "height": height,
            "source_width": source_width,
            "source_height": source_height,
        }
        logger.debug("Desktop coordinate frame updated: %s", self._coordinate_frame)

    def execute(self, action: dict) -> None:
        local_action = self._normalize_action(action)
        self._validate_local_coordinates(local_action)
        self._raise_if_forbidden(local_action)
        if self._confirm_callback and not self._confirm_callback(local_action):
            raise RuntimeError("Action rejected by confirmation callback.")

        screen_action = self._to_screen_action(local_action)
        self._validate_screen_coordinates(screen_action)
        action_type = screen_action.get("type")
        if screen_action == local_action:
            logger.info("Executing action: %s", local_action)
        else:
            logger.info(
                "Executing desktop action: screenshot=%s absolute=%s",
                local_action,
                screen_action,
            )

        if action_type == "click":
            with self._held_modifiers(screen_action):
                self._move_if_present(screen_action)
                pyautogui.click(
                    int(screen_action["x"]),
                    int(screen_action["y"]),
                    button=screen_action.get("button", "left"),
                )
        elif action_type == "double_click":
            with self._held_modifiers(screen_action):
                self._move_if_present(screen_action)
                pyautogui.doubleClick(
                    int(screen_action["x"]),
                    int(screen_action["y"]),
                    button=screen_action.get("button", "left"),
                )
        elif action_type == "move":
            with self._held_modifiers(screen_action):
                pyautogui.moveTo(
                    int(screen_action["x"]),
                    int(screen_action["y"]),
                    duration=float(screen_action.get("duration", 0.0)),
                )
        elif action_type == "drag":
            with self._held_modifiers(screen_action):
                self._execute_drag(screen_action)
        elif action_type == "scroll":
            with self._held_modifiers(screen_action):
                self._execute_scroll(screen_action)
        elif action_type == "type":
            self._type_text(str(screen_action.get("text", "")))
        elif action_type in {"key", "keypress"}:
            self._execute_key(screen_action)
        elif action_type == "wait":
            time.sleep(float(screen_action.get("seconds", 1.0)))
        elif action_type in {"screenshot", "done"}:
            return
        else:
            raise ValueError(f"Unsupported action type: {action_type!r}")

    def _normalize_action(self, action: dict) -> dict:
        normalized = dict(action)
        action_type = normalized.get("type")
        aliases = {
            "doubleClick": "double_click",
            "keypress": "key",
            "dragTo": "drag",
            "tap": "click",
        }
        normalized["type"] = aliases.get(action_type, action_type)

        field_aliases = {
            "fromX": "from_x",
            "fromY": "from_y",
            "toX": "to_x",
            "toY": "to_y",
        }
        for old_name, new_name in field_aliases.items():
            if old_name in normalized and new_name not in normalized:
                normalized[new_name] = normalized.pop(old_name)

        coordinate_fields = {
            "x", "y", "x1", "y1", "x2", "y2",
            "from_x", "from_y", "to_x", "to_y",
        }
        for field in coordinate_fields:
            if field in normalized and normalized[field] is not None:
                normalized[field] = int(float(normalized[field]))

        path = normalized.get("path")
        if isinstance(path, list):
            normalized["path"] = [
                {
                    **point,
                    "x": int(float(point["x"])),
                    "y": int(float(point["y"])),
                }
                for point in path
                if isinstance(point, dict) and "x" in point and "y" in point
            ]
        return normalized

    def _to_screen_action(self, action: dict) -> dict:
        if self._coordinate_frame is None:
            return dict(action)

        transformed = dict(action)
        for x_field, y_field in self._coordinate_pairs(action):
            x, y = self._translate_point(
                int(action[x_field]),
                int(action[y_field]),
            )
            transformed[x_field] = x
            transformed[y_field] = y

        path = action.get("path")
        if isinstance(path, list):
            transformed["path"] = []
            for point in path:
                x, y = self._translate_point(int(point["x"]), int(point["y"]))
                transformed["path"].append({**point, "x": x, "y": y})
        return transformed

    def _translate_point(self, x: int, y: int) -> tuple[int, int]:
        frame = self._coordinate_frame
        if frame is None:
            return x, y
        scale_x = int(frame["width"]) / int(frame["source_width"])
        scale_y = int(frame["height"]) / int(frame["source_height"])
        return (
            int(frame["left"]) + round(x * scale_x),
            int(frame["top"]) + round(y * scale_y),
        )

    @staticmethod
    def _coordinate_pairs(action: dict) -> list[tuple[str, str]]:
        pairs = [
            ("x", "y"),
            ("x1", "y1"),
            ("x2", "y2"),
            ("from_x", "from_y"),
            ("to_x", "to_y"),
        ]
        return [
            (x_field, y_field)
            for x_field, y_field in pairs
            if x_field in action and y_field in action
        ]

    def _validate_local_coordinates(self, action: dict) -> None:
        frame = self._coordinate_frame
        if frame is None or not self.bounds_check:
            return
        width = int(frame["source_width"])
        height = int(frame["source_height"])
        points = [
            (int(action[x_field]), int(action[y_field]))
            for x_field, y_field in self._coordinate_pairs(action)
        ]
        path = action.get("path")
        if isinstance(path, list):
            points.extend((int(point["x"]), int(point["y"])) for point in path)
        for x, y in points:
            if x < 0 or y < 0 or x >= width or y >= height:
                raise ValueError(
                    f"Action coordinates out of screenshot bounds: ({x}, {y}); "
                    f"screenshot={width}x{height}"
                )

    def _validate_screen_coordinates(self, action: dict) -> None:
        if not self.bounds_check:
            return
        points = [
            (int(action[x_field]), int(action[y_field]))
            for x_field, y_field in self._coordinate_pairs(action)
        ]
        path = action.get("path")
        if isinstance(path, list):
            points.extend((int(point["x"]), int(point["y"])) for point in path)
        for x, y in points:
            self._check_bounds(x, y)

    def _raise_if_forbidden(self, action: dict) -> None:
        from auto_click.forbidden_zones import ForbiddenClickError, blocked_reason

        reason = blocked_reason(action, self.forbidden_rects)
        if reason:
            logger.warning("Desktop action blocked by forbidden zone: %s", reason)
            raise ForbiddenClickError(reason)

    def _check_bounds(self, x: int, y: int) -> None:
        left, top, width, height = self._virtual_screen_bounds()
        if x < left or y < top or x >= left + width or y >= top + height:
            raise ValueError(
                f"Action coordinates out of desktop bounds: ({x}, {y}); "
                f"desktop=({left},{top},{width},{height})"
            )

    @staticmethod
    def _virtual_screen_bounds() -> tuple[int, int, int, int]:
        try:
            user32 = ctypes.windll.user32
            return (
                int(user32.GetSystemMetrics(76)),
                int(user32.GetSystemMetrics(77)),
                int(user32.GetSystemMetrics(78)),
                int(user32.GetSystemMetrics(79)),
            )
        except Exception:
            width, height = pyautogui.size()
            return 0, 0, int(width), int(height)

    def _move_if_present(self, action: dict) -> None:
        if "x" in action and "y" in action:
            pyautogui.moveTo(int(action["x"]), int(action["y"]))

    def _execute_scroll(self, action: dict) -> None:
        self._move_if_present(action)
        amount = int(action.get("amount", 0))
        if not amount:
            amount = int(action.get("scroll_y", action.get("scrollY", 0)))
        direction = str(action.get("direction", "")).lower()
        if direction == "right":
            pyautogui.hscroll(abs(amount or 5))
        elif direction == "left":
            pyautogui.hscroll(-abs(amount or 5))
        else:
            if direction == "down":
                amount = -abs(amount or 5)
            elif direction == "up":
                amount = abs(amount or 5)
            pyautogui.scroll(amount)

    def _execute_drag(self, action: dict) -> None:
        path = action.get("path")
        if isinstance(path, list) and path:
            first = path[0]
            pyautogui.moveTo(int(first["x"]), int(first["y"]))
            button = action.get("button", "left")
            pyautogui.mouseDown(button=button)
            try:
                for point in path[1:]:
                    pyautogui.moveTo(
                        int(point["x"]),
                        int(point["y"]),
                        duration=float(action.get("point_duration", 0.05)),
                    )
            finally:
                pyautogui.mouseUp(button=button)
            return

        start_x = action.get("x1", action.get("from_x"))
        start_y = action.get("y1", action.get("from_y"))
        end_x = action.get("x2", action.get("to_x", action.get("x")))
        end_y = action.get("y2", action.get("to_y", action.get("y")))
        if end_x is None or end_y is None:
            raise ValueError("Drag action requires a destination point.")
        if start_x is not None and start_y is not None:
            pyautogui.moveTo(int(start_x), int(start_y))
        pyautogui.dragTo(
            int(end_x),
            int(end_y),
            duration=float(action.get("duration", 0.3)),
            button=action.get("button", "left"),
        )

    @staticmethod
    def _type_text(text: str) -> None:
        if not text:
            return
        if text.isascii():
            pyautogui.write(text, interval=0.01)
            return
        try:
            import pyperclip
        except ImportError as exc:
            raise RuntimeError(
                "Unicode desktop input requires the pyperclip package."
            ) from exc

        previous = None
        restore_clipboard = False
        try:
            previous = pyperclip.paste()
            restore_clipboard = True
        except Exception:
            logger.debug("Unable to read clipboard before Unicode input", exc_info=True)
        try:
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.05)
        finally:
            if restore_clipboard:
                try:
                    pyperclip.copy(previous)
                except Exception:
                    logger.debug("Unable to restore clipboard after Unicode input", exc_info=True)

    def _execute_key(self, action: dict) -> None:
        keys = action.get("keys")
        if keys is None:
            key = action.get("key")
            keys = [key] if key else []
        if isinstance(keys, str):
            keys = [keys]
        keys = [self._normalize_key(str(key)) for key in keys if key]
        if not keys:
            raise ValueError("Key action requires at least one key.")
        if len(keys) == 1:
            pyautogui.press(keys[0])
        else:
            pyautogui.hotkey(*keys)

    @staticmethod
    def _normalize_key(key: str) -> str:
        mapping = {
            "CTRL": "ctrl",
            "CONTROL": "ctrl",
            "CMD": "win",
            "COMMAND": "win",
            "META": "win",
            "RETURN": "enter",
            "ESC": "esc",
            "SPACEBAR": "space",
        }
        upper = key.upper()
        return mapping.get(upper, key.lower())

    @contextmanager
    def _held_modifiers(self, action: dict):
        keys = action.get("keys") or []
        if isinstance(keys, str):
            keys = [keys]
        modifiers = [self._normalize_key(str(key)) for key in keys if key]
        for key in modifiers:
            pyautogui.keyDown(key)
        try:
            yield
        finally:
            for key in reversed(modifiers):
                pyautogui.keyUp(key)
