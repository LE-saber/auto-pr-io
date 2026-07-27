"""Real-time phone screen preview panel with action overlays."""
from __future__ import annotations

import base64
import io
import logging
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageTk

logger = logging.getLogger(__name__)

_CAPTURE_INTERVAL = 0.7      # seconds between live captures (~1.4 fps)
_RECENT_GLOW_SEC  = 2.0      # seconds a mark glows "bright" after being added
_SAVE_DIR         = Path("screenshots") / "phone_live"


class PhoneScreenPanel(ttk.Frame):
    """Streams ADB screenshots and overlays persistent click / action markers.

    Marks stay visible until explicitly cleared (or a new run starts), so
    they are visible across multiple VLM steps regardless of step duration.
    Each frame that contains marks is auto-saved to screenshots/phone_live/.
    """

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._adb_path  = "adb"
        self._device_id = ""
        self._running   = False
        self._thread: Optional[threading.Thread] = None

        # Persistent marks: (rx, ry, step, timestamp_added)
        # Cleared by clear_marks() or start_run() — NOT time-based expiry
        self._marks: list[tuple[float, float, int, float]] = []
        self._marks_lock = threading.Lock()
        self._step_counter = 0

        self._last_img_size: tuple[int, int] = (1080, 2400)
        self._last_raw: Optional[Image.Image] = None   # most recent capture
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._saved_paths: list[str] = []
        self._forbidden_rects: list[dict] = []
        self._forbidden_select_enabled = False
        self._forbidden_callback = None
        self._display_box = (0, 0, 0, 0)
        self._drag_start = None
        self._drag_item = None

        self._build_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def configure_device(self, adb_path: str, device_id: str) -> None:
        self._adb_path  = adb_path  or "adb"
        self._device_id = device_id or ""

    def start(self, adb_path: str = "", device_id: str = "") -> None:
        if adb_path:
            self._adb_path = adb_path
        if device_id:
            self._device_id = device_id
        if self._running:
            return
        self._running = True
        self._toggle_btn.configure(text="Stop preview")
        self._status_var.set("Connecting…")
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info("Phone screen preview started (device=%s)", self._device_id or "auto")

    def stop(self) -> None:
        self._running = False
        self._toggle_btn.configure(text="Start preview")
        self._status_var.set("— stopped —")
        logger.info("Phone screen preview stopped")

    def start_run(self) -> None:
        """Called when a new automation run begins — resets step counter and marks."""
        self._step_counter = 0
        self._saved_paths.clear()
        self.clear_marks()

    def clear_marks(self) -> None:
        with self._marks_lock:
            self._marks.clear()
        self._rerender_now()

    def mark_action(self, action: dict, step: int = 0) -> None:
        """Overlay a persistent marker for a click / double_click action."""
        atype = action.get("type", "")
        if atype not in {"click", "double_click", "tap"}:
            return
        x = action.get("x")
        y = action.get("y")
        if x is None or y is None:
            return
        iw, ih = self._last_img_size
        if iw <= 0 or ih <= 0:
            return
        self._step_counter += 1
        with self._marks_lock:
            self._marks.append((x / iw, y / ih, self._step_counter, time.time()))
        # Immediately re-render the current frame so the mark appears at once
        self._rerender_now()

    def get_recent_screenshots(self, limit: int = 8) -> list[str]:
        return self._saved_paths[-limit:]

    def set_forbidden_rects(self, rects: list[dict]) -> None:
        self._forbidden_rects = list(rects or [])
        self._rerender_now()

    def set_forbidden_selection_enabled(self, enabled: bool) -> None:
        self._forbidden_select_enabled = bool(enabled)
        self._canvas.configure(cursor="crosshair" if enabled else "")

    def set_forbidden_rect_callback(self, callback) -> None:
        self._forbidden_callback = callback

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        ctrl = ttk.Frame(self)
        ctrl.pack(fill=tk.X, padx=6, pady=(6, 2))

        self._status_var = tk.StringVar(value="— stopped —")
        ttk.Label(ctrl, textvariable=self._status_var,
                  font=("Segoe UI", 8)).pack(side=tk.LEFT)

        ttk.Button(ctrl, text="Clear marks",
                   command=self.clear_marks).pack(side=tk.RIGHT, padx=(4, 0))
        self._toggle_btn = ttk.Button(ctrl, text="Start preview",
                                      command=self._toggle)
        self._toggle_btn.pack(side=tk.RIGHT)

        self._canvas = tk.Canvas(self, bg="#111111", cursor="crosshair")
        self._canvas.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
        self._canvas.bind("<ButtonPress-1>", self._on_forbidden_press)
        self._canvas.bind("<B1-Motion>", self._on_forbidden_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_forbidden_release)
        self._canvas.create_text(
            150, 200,
            text="Press 'Start preview'\nto stream the phone screen",
            fill="#555555", font=("Segoe UI", 10), justify="center",
            tags="placeholder",
        )

    def _toggle(self) -> None:
        if self._running:
            self.stop()
        else:
            self.start()

    def _rerender_now(self) -> None:
        """Re-render the most recent captured frame on the main thread."""
        raw = self._last_raw
        if raw is not None:
            self.after(0, lambda img=raw: self._render(img))

    # ------------------------------------------------------------------
    # Capture loop (background thread)
    # ------------------------------------------------------------------

    def _capture_loop(self) -> None:
        from auto_click.adb import ADBController
        controller = ADBController(adb_path=self._adb_path,
                                   device_id=self._device_id)
        while self._running:
            try:
                b64  = controller.screenshot_b64()
                raw  = base64.b64decode(b64)
                img  = Image.open(io.BytesIO(raw)).copy()
                self._last_img_size = img.size
                self._last_raw      = img
                self.after(0, lambda i=img: self._render(i))
                w, h = img.size
                self.after(0, lambda: self._status_var.set(
                    f"Live  {w}×{h} px  |  {len(self._marks)} mark(s)"))
            except Exception as exc:
                logger.debug("Phone screen capture error: %s", exc)
                self.after(0, lambda e=str(exc):
                           self._status_var.set(f"Capture error: {e[:60]}"))
            time.sleep(_CAPTURE_INTERVAL)

    # ------------------------------------------------------------------
    # Rendering (must run on main thread)
    # ------------------------------------------------------------------

    def _render(self, img: Image.Image) -> None:
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw < 20 or ch < 20:
            cw, ch = 300, 500

        # Scale to fit canvas keeping aspect ratio
        iw, ih = img.size
        scale = min(cw / iw, ch / ih)
        dw    = int(iw * scale)
        dh    = int(ih * scale)
        frame = img.resize((dw, dh), Image.LANCZOS).convert("RGBA")

        with self._marks_lock:
            active = list(self._marks)

        has_marks = bool(active)
        if has_marks:
            self._draw_marks(frame, active, dw, dh)

        photo = ImageTk.PhotoImage(frame)
        self._photo = photo           # keep GC reference
        ox = (cw - dw) // 2
        oy = (ch - dh) // 2
        self._display_box = (ox, oy, dw, dh)
        self._canvas.delete("all")
        self._canvas.create_image(ox, oy, anchor="nw", image=photo)
        self._draw_forbidden_rects(iw, ih)

        if has_marks:
            self._autosave(frame)

    def _draw_forbidden_rects(self, iw: int, ih: int) -> None:
        ox, oy, dw, dh = self._display_box
        if dw <= 0 or dh <= 0:
            return
        sx = dw / iw
        sy = dh / ih
        for idx, rect in enumerate(self._forbidden_rects, start=1):
            x1 = ox + int(rect.get("x1", 0) * sx)
            y1 = oy + int(rect.get("y1", 0) * sy)
            x2 = ox + int(rect.get("x2", 0) * sx)
            y2 = oy + int(rect.get("y2", 0) * sy)
            self._canvas.create_rectangle(
                x1, y1, x2, y2,
                outline="#ff3b30", width=2, fill="#ff3b30", stipple="gray25",
            )
            self._canvas.create_text(
                x1 + 6, y1 + 6, text=str(idx), anchor="nw",
                fill="#ffffff", font=("Segoe UI", 9, "bold"),
            )

    def _canvas_to_image(self, cx: int, cy: int, clamp: bool = False) -> tuple[int, int] | None:
        raw = self._last_raw
        if raw is None:
            return None
        ox, oy, dw, dh = self._display_box
        if dw <= 0 or dh <= 0:
            return None
        if clamp:
            cx = max(ox, min(ox + dw, cx))
            cy = max(oy, min(oy + dh, cy))
        elif not (ox <= cx <= ox + dw and oy <= cy <= oy + dh):
            return None
        iw, ih = raw.size
        x = int((cx - ox) / dw * iw)
        y = int((cy - oy) / dh * ih)
        return max(0, min(iw - 1, x)), max(0, min(ih - 1, y))

    def _on_forbidden_press(self, event) -> None:
        if not self._forbidden_select_enabled:
            return
        point = self._canvas_to_image(event.x, event.y)
        if point is None:
            return
        self._drag_start = (event.x, event.y, point)
        if self._drag_item:
            self._canvas.delete(self._drag_item)
        self._drag_item = self._canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="#ffcc00", width=2, dash=(4, 2),
        )

    def _on_forbidden_drag(self, event) -> None:
        if not self._forbidden_select_enabled or not self._drag_start or not self._drag_item:
            return
        ox, oy, dw, dh = self._display_box
        x = max(ox, min(ox + dw, event.x))
        y = max(oy, min(oy + dh, event.y))
        self._canvas.coords(self._drag_item, self._drag_start[0], self._drag_start[1], x, y)

    def _on_forbidden_release(self, event) -> None:
        if not self._forbidden_select_enabled or not self._drag_start:
            return
        start = self._drag_start[2]
        end = self._canvas_to_image(event.x, event.y, clamp=True)
        self._drag_start = None
        if self._drag_item:
            self._canvas.delete(self._drag_item)
            self._drag_item = None
        if end is None:
            return
        x1, x2 = sorted((start[0], end[0]))
        y1, y2 = sorted((start[1], end[1]))
        if x2 - x1 < 5 or y2 - y1 < 5:
            return
        rect = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
        if self._forbidden_callback:
            self._forbidden_callback(rect)

    @staticmethod
    def _draw_marks(
        frame: Image.Image,
        marks: list[tuple[float, float, int, float]],
        dw: int,
        dh: int,
    ) -> None:
        draw = ImageDraw.Draw(frame, "RGBA")
        now  = time.time()

        # Try to load a small font for step labels; fall back to default
        try:
            font = ImageFont.truetype("arial.ttf", 14)
        except Exception:
            font = ImageFont.load_default()

        for rx, ry, step, ts in marks:
            age    = now - ts
            # Full brightness for first 2 s, then stays at 60 % opacity
            fade   = 1.0 if age < _RECENT_GLOW_SEC else 0.60
            alpha  = int(255 * fade)
            r      = 18 if age < _RECENT_GLOW_SEC else 14
            px     = int(rx * dw)
            py     = int(ry * dh)

            # Outer glow ring (bright, recent only)
            if age < _RECENT_GLOW_SEC:
                glow_a = int(180 * (1.0 - age / _RECENT_GLOW_SEC))
                draw.ellipse([px - r - 6, py - r - 6, px + r + 6, py + r + 6],
                             outline=(255, 255, 100, glow_a), width=2)

            # Cross-hair arms
            arm   = r + 10
            color = (255, 60, 60, alpha)
            draw.line([px - arm, py, px + arm, py], fill=color, width=2)
            draw.line([px, py - arm, px, py + arm], fill=color, width=2)

            # Circle
            draw.ellipse([px - r, py - r, px + r, py + r],
                         outline=color, width=2)

            # Centre dot
            draw.ellipse([px - 3, py - 3, px + 3, py + 3],
                         fill=(255, 60, 60, alpha))

            # Step number label
            label = str(step)
            draw.text((px + r + 3, py - 8), label,
                      fill=(255, 220, 80, alpha), font=font)

    # ------------------------------------------------------------------
    # Auto-save annotated frame
    # ------------------------------------------------------------------

    _last_saved_step: int = -1   # avoid saving duplicate frames for the same mark

    def _autosave(self, frame: Image.Image) -> None:
        with self._marks_lock:
            if not self._marks:
                return
            latest_step = self._marks[-1][2]
        if latest_step == self._last_saved_step:
            return   # already saved a frame for this mark
        self._last_saved_step = latest_step
        try:
            _SAVE_DIR.mkdir(parents=True, exist_ok=True)
            ts   = time.strftime("%Y%m%d_%H%M%S")
            path = _SAVE_DIR / f"{ts}_step{latest_step:03d}.png"
            frame.convert("RGB").save(str(path))
            self._saved_paths.append(str(path))
            logger.info("Annotated screenshot saved: %s", path)
        except Exception as exc:
            logger.debug("Failed to auto-save annotated screenshot: %s", exc)
