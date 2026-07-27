"""ADB helpers for Android screenshot capture and input execution."""
from __future__ import annotations

import base64
import logging
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class ADBDeviceInfo:
    device_id: str
    state: str
    manufacturer: str = ""
    model: str = ""
    android_version: str = ""

    @property
    def display_name(self) -> str:
        """Human-readable label for UI dropdowns."""
        if self.state != "device":
            return f"{self.device_id}  [{self.state}]"
        name_parts: list[str] = []
        if self.manufacturer:
            name_parts.append(self.manufacturer)
        if self.model:
            name_parts.append(self.model)
        device_name = " ".join(name_parts) if name_parts else self.device_id
        if self.android_version:
            return f"{device_name}  (Android {self.android_version})  —  {self.device_id}"
        return f"{device_name}  —  {self.device_id}"


class ADBController:
    """Small wrapper around adb for screenshots and input events."""

    ADB_KEYBOARD_CANDIDATES = (
        "com.autopr.keyboardaudio/.AdbImeService",
        "com.android.adbkeyboard/.AdbIME",
        "com.github.uiautomator/.AdbKeyboard",
        "com.zhipu.autoglm/.AdbIME",
        "com.zhipu.autoglmphone/.AdbIME",
    )

    def __init__(self, adb_path: str = "adb", device_id: str = ""):
        self.adb_path = adb_path or "adb"
        self.device_id = device_id.strip()
        self._adb_keyboard_checked = False
        self._adb_keyboard_ime = ""

    def list_devices(self) -> list[ADBDeviceInfo]:
        result = self._run(["devices"], text=True)
        devices: list[ADBDeviceInfo] = []
        for line in result.stdout.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = re.split(r"\s+", line)
            if len(parts) >= 2:
                info = ADBDeviceInfo(device_id=parts[0], state=parts[1])
                if info.state == "device":
                    props = self._fetch_device_props(info.device_id)
                    info.manufacturer = props.get("manufacturer", "")
                    info.model = props.get("model", "")
                    info.android_version = props.get("android_version", "")
                devices.append(info)
        return devices

    def _fetch_device_props(self, device_id: str) -> dict[str, str]:
        """Query ro.product.* and ro.build.version.release for a ready device."""
        props: dict[str, str] = {}
        try:
            result = subprocess.run(
                [
                    self.adb_path, "-s", device_id, "shell",
                    "getprop ro.product.manufacturer"
                    " && getprop ro.product.model"
                    " && getprop ro.build.version.release",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
            if len(lines) >= 3:
                props["manufacturer"] = lines[0]
                props["model"] = lines[1]
                props["android_version"] = lines[2]
            elif len(lines) == 2:
                props["model"] = lines[0]
                props["android_version"] = lines[1]
            elif len(lines) == 1:
                props["model"] = lines[0]
        except Exception:
            logger.debug("Could not fetch props for device %s", device_id)
        return props

    def ensure_ready(self) -> None:
        devices = [device for device in self.list_devices() if device.state == "device"]
        if self.device_id:
            if not any(device.device_id == self.device_id for device in devices):
                raise RuntimeError(f"ADB device not ready: {self.device_id}")
            return
        if not devices:
            raise RuntimeError("No Android device is available through adb.")
        if len(devices) > 1:
            ids = ", ".join(device.device_id for device in devices)
            raise RuntimeError(f"Multiple adb devices found; specify one: {ids}")
        self.device_id = devices[0].device_id

    def screenshot_b64(self) -> str:
        self.ensure_ready()
        result = self._run(["exec-out", "screencap", "-p"], text=False)
        data = result.stdout
        if not data:
            raise RuntimeError("ADB screencap returned no data.")
        return base64.b64encode(data).decode("utf-8")

    def screen_size(self) -> tuple[int, int]:
        """Return (width, height) effective screen resolution via ``wm size``."""
        result = self._shell(["wm", "size"])
        # Prefer "Override size" when DPI scaling is active; fall back to Physical
        text = result.stdout
        override = re.search(r"Override size:\s*(\d+)x(\d+)", text)
        if override:
            return int(override.group(1)), int(override.group(2))
        physical = re.search(r"Physical size:\s*(\d+)x(\d+)", text)
        if physical:
            return int(physical.group(1)), int(physical.group(2))
        # Last-resort: any WxH pattern in the output
        m = re.search(r"(\d{3,4})x(\d{3,4})", text)
        if m:
            return int(m.group(1)), int(m.group(2))
        raise RuntimeError(f"Could not parse screen size from: {text!r}")

    def tap(self, x: int, y: int) -> None:
        self._shell(["input", "tap", str(int(x)), str(int(y))])

    def double_tap(self, x: int, y: int) -> None:
        self.tap(x, y)
        time.sleep(0.08)
        self.tap(x, y)

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int = 300,
    ) -> None:
        self._shell([
            "input", "swipe",
            str(int(x1)), str(int(y1)),
            str(int(x2)), str(int(y2)),
            str(int(duration_ms)),
        ])

    def text(self, value: str) -> None:
        if not value:
            return
        if self.input_text_with_adb_keyboard(value):
            return
        # adb input text has limited Unicode support; this covers simple text.
        encoded = (
            value.replace("%", r"\%")
            .replace(" ", "%s")
            .replace("&", r"\&")
            .replace("|", r"\|")
            .replace("<", r"\<")
            .replace(">", r"\>")
            .replace(";", r"\;")
        )
        self._shell(["input", "text", encoded])

    def input_text_with_adb_keyboard(self, value: str) -> bool:
        """Type text through ADB Keyboard if it is installed and enabled."""
        ime_id = self.ensure_adb_keyboard()
        if not ime_id:
            return False
        payload = base64.b64encode(value.encode("utf-8")).decode("ascii")
        try:
            self._shell(["am", "broadcast", "-a", "ADB_INPUT_B64", "--es", "msg", payload])
            logger.info("Text input sent through ADB Keyboard (%s)", ime_id)
            return True
        except RuntimeError:
            logger.debug("ADB_INPUT_B64 failed; retrying ADB_INPUT_TEXT", exc_info=True)
        try:
            self._shell(["am", "broadcast", "-a", "ADB_INPUT_TEXT", "--es", "msg", value])
            logger.info("Text input sent through ADB Keyboard (%s)", ime_id)
            return True
        except RuntimeError:
            logger.warning("ADB Keyboard broadcast failed; falling back to adb input text", exc_info=True)
            return False

    def ensure_adb_keyboard(self, preferred_ime: str = "") -> str:
        """Enable and switch to an installed ADB Keyboard IME when possible."""
        if self._adb_keyboard_checked:
            return self._adb_keyboard_ime
        self._adb_keyboard_checked = True
        ime_id = preferred_ime or self.find_adb_keyboard_ime()
        if not ime_id:
            logger.info("ADB Keyboard IME not found; using adb input text fallback")
            return ""
        try:
            self._shell(["ime", "enable", ime_id])
            self._shell(["ime", "set", ime_id])
            current = self.current_ime()
            if current and current != ime_id:
                logger.warning("ADB Keyboard requested but current IME is %s", current)
            self._adb_keyboard_ime = ime_id
            logger.info("ADB Keyboard enabled: %s", ime_id)
        except RuntimeError:
            logger.warning(
                "Could not enable ADB Keyboard %s. Enable it once in Android input settings, then retry.",
                ime_id,
                exc_info=True,
            )
            self._adb_keyboard_ime = ""
        return self._adb_keyboard_ime

    def find_adb_keyboard_ime(self) -> str:
        installed = self.list_imes()
        for candidate in self.ADB_KEYBOARD_CANDIDATES:
            if candidate in installed:
                return candidate
        for ime_id in installed:
            lower = ime_id.lower()
            if "adb" in lower and ("keyboard" in lower or "ime" in lower):
                return ime_id
        return ""

    def list_imes(self) -> list[str]:
        ids: list[str] = []
        try:
            result = self._shell(["ime", "list", "-s"])
            ids.extend(line.strip() for line in result.stdout.splitlines() if line.strip())
        except RuntimeError:
            logger.debug("Could not list enabled IMEs", exc_info=True)
        try:
            result = self._shell(["ime", "list", "-a"])
            for line in result.stdout.splitlines():
                line = line.strip()
                match = re.search(r"mId=([^\s}]+)", line)
                if match:
                    ids.append(match.group(1))
                elif "/" in line and not line.startswith(("mSettings", "mIs")):
                    ids.append(line.split()[0])
        except RuntimeError:
            logger.debug("Could not list all IMEs", exc_info=True)
        unique: list[str] = []
        for ime_id in ids:
            if ime_id and ime_id not in unique:
                unique.append(ime_id)
        return unique

    def current_ime(self) -> str:
        result = self._shell(["settings", "get", "secure", "default_input_method"])
        return result.stdout.strip()

    def keyevent(self, key: str | int) -> None:
        self._shell(["input", "keyevent", str(key)])

    def _shell(self, args: list[str]) -> subprocess.CompletedProcess:
        return self._run(["shell", *args], text=True)

    def _run(self, args: list[str], text: bool) -> subprocess.CompletedProcess:
        command = [self.adb_path]
        if self.device_id and args[:1] != ["devices"]:
            command.extend(["-s", self.device_id])
        command.extend(args)
        logger.debug("Running adb command: %s", command)
        try:
            return subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=text,
                timeout=30,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("adb was not found. Install Android platform-tools first.") from exc
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            detail = (stderr or stdout or str(exc)).strip()
            raise RuntimeError(f"adb command failed: {detail}") from exc


class ADBActionExecutor:
    """Execute normalized actions against an Android device via adb."""

    KEY_MAP = {
        "BACK": "KEYCODE_BACK",
        "ESC": "KEYCODE_BACK",
        "ESCAPE": "KEYCODE_BACK",
        "HOME": "KEYCODE_HOME",
        "ENTER": "KEYCODE_ENTER",
        "RETURN": "KEYCODE_ENTER",
        "TAB": "KEYCODE_TAB",
        "SPACE": "KEYCODE_SPACE",
        "BACKSPACE": "KEYCODE_DEL",
        "DELETE": "KEYCODE_FORWARD_DEL",
        "DEL": "KEYCODE_FORWARD_DEL",
        "UP": "KEYCODE_DPAD_UP",
        "DOWN": "KEYCODE_DPAD_DOWN",
        "LEFT": "KEYCODE_DPAD_LEFT",
        "RIGHT": "KEYCODE_DPAD_RIGHT",
        "POWER": "KEYCODE_POWER",
        "MENU": "KEYCODE_MENU",
        "APP_SWITCH": "KEYCODE_APP_SWITCH",
    }

    def __init__(
        self,
        controller: ADBController,
        confirm_before_execute: bool = True,
        coord_scale_x: float = 1.0,
        coord_scale_y: float = 1.0,
        forbidden_rects: list[dict] | None = None,
    ):
        self.controller = controller
        self.confirm_before_execute = confirm_before_execute
        self.coord_scale_x = coord_scale_x
        self.coord_scale_y = coord_scale_y
        self.forbidden_rects = forbidden_rects or []
        self._confirm_callback: Optional[Callable[[dict], bool]] = None

    def set_confirm_callback(self, callback: Callable[[dict], bool]) -> None:
        self._confirm_callback = callback

    def execute(self, action: dict) -> None:
        action = self._normalize_action(action)
        self._raise_if_forbidden(action)
        if self._confirm_callback and not self._confirm_callback(action):
            raise RuntimeError("Action rejected by confirmation callback.")

        action_type = action.get("type")
        logger.info("Executing adb action: %s", action)

        if action_type == "click":
            self.controller.tap(action["x"], action["y"])
        elif action_type == "double_click":
            self.controller.double_tap(action["x"], action["y"])
        elif action_type == "drag":
            self._execute_drag(action)
        elif action_type == "scroll":
            self._execute_scroll(action)
        elif action_type == "type":
            self.controller.text(str(action.get("text", "")))
        elif action_type in {"enable_keyboard", "enable_adb_keyboard"}:
            self.controller.ensure_adb_keyboard()
        elif action_type in {"key", "keypress"}:
            self._execute_key(action)
        elif action_type == "back":
            self.controller.keyevent("KEYCODE_BACK")
        elif action_type == "home":
            self.controller.keyevent("KEYCODE_HOME")
        elif action_type == "wait":
            time.sleep(float(action.get("seconds", 1.0)))
        elif action_type in {"move", "screenshot", "done"}:
            return
        else:
            raise ValueError(f"Unsupported adb action type: {action_type!r}")

    def _normalize_action(self, action: dict) -> dict:
        normalized = dict(action)
        aliases = {
            "tap": "click",
            "double_tap": "double_click",
            "doubleClick": "double_click",
            "keypress": "key",
            "swipe": "drag",
        }
        normalized["type"] = aliases.get(normalized.get("type"), normalized.get("type"))
        if "x" not in normalized or "y" not in normalized:
            self._fill_point_from_action(normalized)
        # Scale 1000-unit normalized coordinates to real screen pixels.
        x_scale = self.coord_scale_x
        y_scale = self.coord_scale_y
        for key in ("x", "x1", "x2", "to_x"):
            if key in normalized and normalized[key] is not None:
                normalized[key] = int(float(normalized[key]) * x_scale)
        for key in ("y", "y1", "y2", "to_y"):
            if key in normalized and normalized[key] is not None:
                normalized[key] = int(float(normalized[key]) * y_scale)
        return normalized

    def _raise_if_forbidden(self, action: dict) -> None:
        from auto_click.forbidden_zones import ForbiddenClickError, blocked_reason

        reason = blocked_reason(action, self.forbidden_rects)
        if reason:
            logger.warning("ADB action blocked by forbidden zone: %s", reason)
            raise ForbiddenClickError(reason)

    @staticmethod
    def _fill_point_from_action(action: dict) -> None:
        for field in ("element", "point", "position", "coordinate", "coordinates", "target"):
            value = action.get(field)
            if not isinstance(value, list) or not value:
                continue
            coords = value[0] if isinstance(value[0], list) else value
            if len(coords) == 2:
                action["x"] = int(float(coords[0]))
                action["y"] = int(float(coords[1]))
                return
            if len(coords) == 4:
                x1, y1, x2, y2 = coords
                action["x"] = (int(float(x1)) + int(float(x2))) // 2
                action["y"] = (int(float(y1)) + int(float(y2))) // 2
                return

    def _execute_drag(self, action: dict) -> None:
        path = action.get("path")
        if isinstance(path, list) and len(path) >= 2:
            start = self._point(path[0])
            end = self._point(path[-1])
            self.controller.swipe(*start, *end, int(action.get("duration_ms", 350)))
            return

        x1 = action.get("x1", action.get("x", 500))
        y1 = action.get("y1", action.get("y", 1500))
        x2 = action.get("x2", action.get("to_x", x1))
        y2 = action.get("y2", action.get("to_y", y1 - 600))
        self.controller.swipe(x1, y1, x2, y2, int(action.get("duration_ms", 350)))

    def _execute_scroll(self, action: dict) -> None:
        x = int(action.get("x", 500))
        y = int(action.get("y", 1200))
        amount = int(action.get("amount", 500) or 500)
        direction = str(action.get("direction", "")).lower()
        scroll_y = int(action.get("scroll_y", action.get("scrollY", 0)) or 0)
        if scroll_y:
            direction = "down" if scroll_y > 0 else "up"

        if direction in {"up"}:
            self.controller.swipe(x, y, x, y + abs(amount), 250)
        elif direction in {"left"}:
            self.controller.swipe(x, y, x + abs(amount), y, 250)
        elif direction in {"right"}:
            self.controller.swipe(x, y, x - abs(amount), y, 250)
        else:
            self.controller.swipe(x, y, x, y - abs(amount), 250)

    def _execute_key(self, action: dict) -> None:
        keys = action.get("keys")
        if keys is None:
            key = action.get("key")
            keys = [key] if key else []
        if isinstance(keys, str):
            keys = [keys]
        for key in keys:
            if key is None:
                continue
            mapped = self.KEY_MAP.get(str(key).upper(), key)
            self.controller.keyevent(mapped)

    @staticmethod
    def _point(value) -> tuple[int, int]:
        if isinstance(value, dict):
            return int(value["x"]), int(value["y"])
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            return int(value[0]), int(value[1])
        raise ValueError("Point must be {x, y} or [x, y].")
