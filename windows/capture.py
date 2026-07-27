"""Screenshot capture utilities for auto-pr-io."""
from __future__ import annotations

import tkinter as tk
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

import mss
from PIL import Image


SCREENSHOTS_DIR = Path(__file__).parent.parent / "Screenshots"
logger = logging.getLogger(__name__)


def timestamp() -> str:
    """Return a timestamp string suitable for screenshot filenames."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _save_image(image: Image.Image) -> None:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    image.save(SCREENSHOTS_DIR / f"screenshot_{timestamp()}.png")


def _mss_capture_region(left: int, top: int, width: int, height: int) -> Image.Image:
    if width <= 0 or height <= 0:
        raise ValueError("Capture region must have positive width and height.")

    with mss.mss() as screenshotter:
        shot = screenshotter.grab(
            {"left": left, "top": top, "width": width, "height": height}
        )
        return Image.frombytes("RGB", shot.size, shot.rgb)


def _capture_screen_region(left: int, top: int, width: int, height: int) -> Image.Image:
    try:
        return _mss_capture_region(left, top, width, height)
    except Exception:
        logger.warning("MSS capture failed; retrying with Pillow ImageGrab", exc_info=True)
        from PIL import ImageGrab

        return ImageGrab.grab(
            bbox=(left, top, left + width, top + height),
            all_screens=True,
        ).convert("RGB")


def fullscreen_capture_spec(monitor: int = 1) -> dict[str, Any]:
    return {"mode": "fullscreen", "monitor": max(1, int(monitor))}


def region_capture_spec(x1: int, y1: int, x2: int, y2: int) -> dict[str, Any]:
    left, right = sorted((int(x1), int(x2)))
    top, bottom = sorted((int(y1), int(y2)))
    if right <= left or bottom <= top:
        raise ValueError("Capture region must have positive width and height.")
    return {
        "mode": "region",
        "left": left,
        "top": top,
        "width": right - left,
        "height": bottom - top,
    }


def window_capture_spec(hwnd: int) -> dict[str, Any]:
    return {"mode": "window", "hwnd": int(hwnd)}


def capture_desktop(
    spec: Mapping[str, Any] | None = None,
    *,
    save: bool = False,
) -> tuple[Image.Image, dict[str, int | str]]:
    """Capture one stable desktop target and return its screen-coordinate frame."""
    capture_spec = dict(spec or fullscreen_capture_spec())
    mode = str(capture_spec.get("mode", "fullscreen"))

    if mode == "fullscreen":
        monitor_index = max(1, int(capture_spec.get("monitor", 1)))
        with mss.mss() as screenshotter:
            if monitor_index >= len(screenshotter.monitors):
                raise ValueError(f"Monitor {monitor_index} is unavailable.")
            monitor = screenshotter.monitors[monitor_index]
            frame = {
                "mode": mode,
                "left": int(monitor["left"]),
                "top": int(monitor["top"]),
                "width": int(monitor["width"]),
                "height": int(monitor["height"]),
            }
            image = _capture_screen_region(
                int(frame["left"]),
                int(frame["top"]),
                int(frame["width"]),
                int(frame["height"]),
            )
    elif mode == "region":
        frame = {
            "mode": mode,
            "left": int(capture_spec["left"]),
            "top": int(capture_spec["top"]),
            "width": int(capture_spec["width"]),
            "height": int(capture_spec["height"]),
        }
        image = _capture_screen_region(
            int(frame["left"]),
            int(frame["top"]),
            int(frame["width"]),
            int(frame["height"]),
        )
    elif mode == "window":
        hwnd = int(capture_spec["hwnd"])
        frame = _window_client_frame(hwnd)
        try:
            image = _capture_window_client_blt(hwnd)
        except Exception:
            image = _capture_screen_region(
                int(frame["left"]),
                int(frame["top"]),
                int(frame["width"]),
                int(frame["height"]),
            )
    else:
        raise ValueError(f"Unsupported desktop capture mode: {mode!r}")

    frame["source_width"] = image.width
    frame["source_height"] = image.height
    if save:
        _save_image(image)
    return image, frame


def capture_fullscreen() -> Image.Image:
    """Capture the primary monitor, save it, and return it as a PIL RGB image."""
    image, _frame = capture_desktop(fullscreen_capture_spec(), save=True)
    return image


def capture_region(x1: int, y1: int, x2: int, y2: int) -> Image.Image:
    """Capture a screen region using absolute coordinates."""
    image, _frame = capture_desktop(
        region_capture_spec(x1, y1, x2, y2),
        save=True,
    )
    return image


def capture_window(hwnd: int) -> Image.Image:
    """Capture a window client area by HWND, falling back to an mss window rect grab."""
    image, _frame = capture_desktop(window_capture_spec(hwnd), save=True)
    return image


def _window_client_frame(hwnd: int) -> dict[str, int | str]:
    import win32gui

    if not win32gui.IsWindow(hwnd):
        raise ValueError(f"Invalid window handle: {hwnd}")
    client_left, client_top, client_right, client_bottom = win32gui.GetClientRect(hwnd)
    width = int(client_right - client_left)
    height = int(client_bottom - client_top)
    if width <= 0 or height <= 0:
        raise ValueError("Window client area is empty.")
    left, top = win32gui.ClientToScreen(hwnd, (0, 0))
    return {
        "mode": "window",
        "left": int(left),
        "top": int(top),
        "width": width,
        "height": height,
    }


def _capture_window_client_blt(hwnd: int) -> Image.Image:
    import win32con
    import win32gui
    import win32ui

    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        raise ValueError("Window client area is empty.")

    hwnd_dc = None
    source_dc = None
    memory_dc = None
    bitmap = None
    old_bitmap = None

    try:
        hwnd_dc = win32gui.GetDC(hwnd)
        source_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        memory_dc = source_dc.CreateCompatibleDC()

        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(source_dc, width, height)
        old_bitmap = memory_dc.SelectObject(bitmap)

        if not memory_dc.BitBlt(
            (0, 0), (width, height), source_dc, (0, 0), win32con.SRCCOPY
        ):
            raise RuntimeError("BitBlt failed.")

        bmp_bytes = bitmap.GetBitmapBits(True)
        return Image.frombuffer(
            "RGB",
            (width, height),
            bmp_bytes,
            "raw",
            "BGRX",
            0,
            1,
        ).copy()
    finally:
        if memory_dc is not None and old_bitmap is not None:
            memory_dc.SelectObject(old_bitmap)
        if bitmap is not None:
            win32gui.DeleteObject(bitmap.GetHandle())
        if memory_dc is not None:
            memory_dc.DeleteDC()
        if source_dc is not None:
            source_dc.DeleteDC()
        if hwnd_dc is not None:
            win32gui.ReleaseDC(hwnd, hwnd_dc)


class RegionCaptureOverlay(tk.Toplevel):
    """Transparent fullscreen overlay for drag-selecting a capture rectangle."""

    def __init__(
        self,
        master,
        callback: Callable[[int | None, int | None, int | None, int | None], None],
    ):
        super().__init__(master)
        self.callback = callback
        self.start_x: int | None = None
        self.start_y: int | None = None
        self.rect_id: int | None = None

        self._left, self._top, self._width, self._height = self._get_virtual_screen()
        self.geometry(f"{self._width}x{self._height}+{self._left}+{self._top}")
        self.overrideredirect(True)
        self.attributes("-alpha", 0.3)
        self.attributes("-topmost", True)
        self.configure(cursor="crosshair", bg="black")

        self.canvas = tk.Canvas(
            self,
            highlightthickness=0,
            bg="black",
            cursor="crosshair",
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.bind("<Escape>", self._cancel)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        self.focus_force()
        self.grab_set()

    def _get_virtual_screen(self) -> tuple[int, int, int, int]:
        try:
            with mss.mss() as screenshotter:
                monitor = screenshotter.monitors[0]  # 0 = virtual screen (all monitors)
                return (
                    int(monitor["left"]),
                    int(monitor["top"]),
                    int(monitor["width"]),
                    int(monitor["height"]),
                )
        except Exception:
            return (0, 0, self.winfo_screenwidth(), self.winfo_screenheight())

    def _on_press(self, event: tk.Event) -> None:
        self.start_x = int(event.x)
        self.start_y = int(event.y)
        if self.rect_id is not None:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y,
            self.start_x, self.start_y,
            outline="red", width=2, dash=(6, 4),
        )

    def _on_drag(self, event: tk.Event) -> None:
        if self.start_x is None or self.start_y is None or self.rect_id is None:
            return
        self.canvas.coords(
            self.rect_id,
            self.start_x, self.start_y,
            int(event.x), int(event.y),
        )

    def _on_release(self, event: tk.Event) -> None:
        if self.start_x is None or self.start_y is None:
            self._cancel()
            return
        x1 = self._left + self.start_x
        y1 = self._top + self.start_y
        x2 = self._left + int(event.x)
        y2 = self._top + int(event.y)
        self._finish(x1, y1, x2, y2)

    def _cancel(self, event: tk.Event | None = None) -> None:
        self._finish(None, None, None, None)

    def _finish(
        self,
        x1: int | None,
        y1: int | None,
        x2: int | None,
        y2: int | None,
    ) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
        self.callback(x1, y1, x2, y2)
