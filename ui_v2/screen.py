"""Live screen surface shared by Windows capture and Android preview."""
from __future__ import annotations

import base64
import io
import logging
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Callable, Optional

from PIL import Image, ImageDraw, ImageTk

from ui_v2.theme import COLORS, MONO_FONT

logger = logging.getLogger(__name__)

_SAVE_DIR = Path("screenshots") / "runs"


class ScreenSurface(ttk.Frame):
    def __init__(
        self,
        master,
        translate: Callable[..., str],
        on_zone: Callable[[dict], None],
    ) -> None:
        super().__init__(master, style="App.TFrame")
        self.t = translate
        self.on_zone = on_zone
        self.target = "android"
        self._adb_path = "adb"
        self._device_id = ""
        self._preview_running = False
        self._preview_thread: Optional[threading.Thread] = None
        self._capture_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._raw_image: Optional[Image.Image] = None
        self._target_images: dict[str, Optional[Image.Image]] = {
            "android": None,
            "desktop": None,
        }
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._display_box = (0, 0, 0, 0)
        self._marks: list[tuple[int, int, int]] = []
        self._zones: list[dict] = []
        self._draw_zones = False
        self._drag_start: Optional[tuple[int, int, tuple[int, int]]] = None
        self._drag_item: Optional[int] = None
        self._saved_paths: list[str] = []
        self._lock = threading.Lock()
        self._build()
        self.after(120, self._drain_capture_queue)

    def _build(self) -> None:
        toolbar = ttk.Frame(self, style="Header.TFrame", padding=(12, 8))
        toolbar.pack(fill=tk.X)
        self.title_label = ttk.Label(toolbar, text=self.t("live_screen"), style="Heading.TLabel")
        self.title_label.pack(side=tk.LEFT)
        self.status_var = tk.StringVar(value=self.t("preview_offline"))
        self.status_label = ttk.Label(toolbar, textvariable=self.status_var, style="Muted.TLabel")
        self.status_label.pack(side=tk.LEFT, padx=(12, 0))

        self.save_button = ttk.Button(toolbar, text=self.t("save_image"), style="Compact.TButton", command=self.save_image)
        self.save_button.pack(side=tk.RIGHT)
        self.clear_button = ttk.Button(toolbar, text=self.t("clear_marks"), style="Compact.TButton", command=self.clear_marks)
        self.clear_button.pack(side=tk.RIGHT, padx=(0, 6))
        self.preview_button = ttk.Button(toolbar, text=self.t("start_preview"), style="Compact.TButton", command=self.toggle_preview)
        self.preview_button.pack(side=tk.RIGHT, padx=(0, 6))

        self.canvas = tk.Canvas(
            self,
            background=COLORS["bg"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            relief="flat",
        )
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        self.canvas.bind("<Configure>", lambda _event: self._render())
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self._render_placeholder()

    def set_target(self, target: str) -> None:
        if target != self.target and self._preview_running:
            self.stop_preview()
        if target != self.target:
            with self._lock:
                self._target_images[self.target] = self._raw_image
                self._raw_image = self._target_images.get(target)
                self._marks.clear()
        self.target = target
        self.preview_button.configure(state="normal" if target == "android" else "disabled")
        if self._raw_image is None:
            self.status_var.set(self.t("preview_waiting"))
        else:
            self.status_var.set(f"{self._raw_image.width} x {self._raw_image.height} px")
        self._render()

    def configure_phone(self, adb_path: str, device_id: str) -> None:
        changed = (adb_path or "adb", device_id or "") != (self._adb_path, self._device_id)
        self._adb_path = adb_path or "adb"
        self._device_id = device_id or ""
        if changed and self._preview_running:
            self.stop_preview()
            self.start_preview()

    def start_preview(self) -> None:
        if self.target != "android" or self._preview_running or not self._device_id:
            return
        self._preview_running = True
        self.preview_button.configure(text=self.t("stop_preview"))
        self.status_var.set(self.t("scanning"))
        self._preview_thread = threading.Thread(target=self._preview_loop, name="UIV2PhonePreview", daemon=True)
        self._preview_thread.start()

    def stop_preview(self) -> None:
        self._preview_running = False
        self.preview_button.configure(text=self.t("start_preview"))
        self.status_var.set(self.t("stopped"))

    def toggle_preview(self) -> None:
        if self._preview_running:
            self.stop_preview()
        else:
            self.start_preview()

    def _preview_loop(self) -> None:
        from auto_click.adb import ADBController

        controller = ADBController(adb_path=self._adb_path, device_id=self._device_id)
        while self._preview_running:
            try:
                payload = base64.b64decode(controller.screenshot_b64())
                image = Image.open(io.BytesIO(payload)).convert("RGB")
                self._capture_queue.put(("image", image.copy()))
            except Exception as exc:
                self._capture_queue.put(("error", str(exc)))
            time.sleep(0.8)

    def _drain_capture_queue(self) -> None:
        latest: Optional[Image.Image] = None
        while True:
            try:
                kind, payload = self._capture_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "image" and isinstance(payload, Image.Image):
                latest = payload
            elif kind == "error":
                self.status_var.set(str(payload)[:90])
        if latest is not None:
            with self._lock:
                self._target_images["android"] = latest
                if self.target == "android":
                    self._raw_image = latest
            if self.target == "android":
                self.status_var.set(f"{latest.width} x {latest.height} px")
                self._render()
        self.after(120, self._drain_capture_queue)

    def set_desktop_image(self, image: Image.Image) -> None:
        converted = image.convert("RGB").copy()
        with self._lock:
            self._target_images["desktop"] = converted
            if self.target == "desktop":
                self._raw_image = converted
        if self.target == "desktop":
            self.status_var.set(f"{image.width} x {image.height} px")
            self._render()

    def screenshot_b64(self) -> Optional[str]:
        with self._lock:
            image = self._raw_image.copy() if self._raw_image is not None else None
        if image is None:
            return None
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")

    def save_image(self) -> Optional[str]:
        with self._lock:
            image = self._raw_image.copy() if self._raw_image is not None else None
        if image is None:
            return None
        path = filedialog.asksaveasfilename(
            parent=self.winfo_toplevel(),
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")],
        )
        if not path:
            return None
        image.save(path)
        return path

    def start_run(self) -> None:
        with self._lock:
            self._marks.clear()
            self._saved_paths.clear()
        self._render()

    def clear_marks(self) -> None:
        with self._lock:
            self._marks.clear()
        self._render()

    def mark_action(self, action: dict, step: int) -> None:
        if action.get("type") not in {"click", "double_click", "tap"}:
            return
        try:
            x, y = int(action["x"]), int(action["y"])
        except (KeyError, TypeError, ValueError):
            return
        with self._lock:
            self._marks.append((x, y, step))
        self._archive_annotated(step)
        self._render()

    def recent_screenshots(self, limit: int = 8) -> list[str]:
        with self._lock:
            return list(self._saved_paths[-limit:])

    def set_zones(self, zones: list[dict]) -> None:
        self._zones = list(zones or [])
        self._render()

    def set_zone_drawing(self, enabled: bool) -> None:
        self._draw_zones = bool(enabled)
        self.canvas.configure(cursor="crosshair" if enabled else "")

    def _render(self) -> None:
        if not self.winfo_exists():
            return
        with self._lock:
            image = self._raw_image.copy() if self._raw_image is not None else None
            marks = list(self._marks)
        if image is None:
            self._render_placeholder()
            return
        cw, ch = max(80, self.canvas.winfo_width()), max(80, self.canvas.winfo_height())
        scale = min((cw - 24) / image.width, (ch - 24) / image.height)
        width, height = max(1, int(image.width * scale)), max(1, int(image.height * scale))
        resized = image.resize((width, height), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(resized)
        ox, oy = (cw - width) // 2, (ch - height) // 2
        self._display_box = (ox, oy, width, height)
        self.canvas.delete("all")
        self.canvas.create_image(ox, oy, anchor="nw", image=self._photo)
        sx, sy = width / image.width, height / image.height
        for x, y, step in marks:
            px, py = ox + x * sx, oy + y * sy
            self.canvas.create_oval(px - 10, py - 10, px + 10, py + 10, outline=COLORS["error"], width=2)
            self.canvas.create_line(px - 15, py, px + 15, py, fill=COLORS["error"], width=1)
            self.canvas.create_line(px, py - 15, px, py + 15, fill=COLORS["error"], width=1)
            self.canvas.create_text(px + 15, py - 11, text=str(step), anchor="sw", fill=COLORS["warning"], font=(MONO_FONT, 9, "bold"))
        for index, rect in enumerate(self._zones, 1):
            x1, y1 = ox + int(rect.get("x1", 0)) * sx, oy + int(rect.get("y1", 0)) * sy
            x2, y2 = ox + int(rect.get("x2", 0)) * sx, oy + int(rect.get("y2", 0)) * sy
            self.canvas.create_rectangle(x1, y1, x2, y2, outline=COLORS["error"], width=2, fill="#401F24", stipple="gray50")
            self.canvas.create_text(x1 + 5, y1 + 4, text=str(index), anchor="nw", fill=COLORS["text"], font=(MONO_FONT, 9, "bold"))

    def _render_placeholder(self) -> None:
        self.canvas.delete("all")
        cw, ch = max(200, self.canvas.winfo_width()), max(200, self.canvas.winfo_height())
        self.canvas.create_text(cw // 2, ch // 2 - 8, text=self.t("preview_offline"), fill=COLORS["muted"], font=("Segoe UI", 12, "bold"))
        self.canvas.create_text(cw // 2, ch // 2 + 18, text=self.t("preview_waiting"), fill=COLORS["faint"], font=("Segoe UI", 9))

    def _canvas_to_image(self, x: int, y: int, clamp: bool = False) -> Optional[tuple[int, int]]:
        with self._lock:
            image = self._raw_image
        if image is None:
            return None
        ox, oy, width, height = self._display_box
        if width <= 0 or height <= 0:
            return None
        if clamp:
            x, y = max(ox, min(ox + width, x)), max(oy, min(oy + height, y))
        elif not (ox <= x <= ox + width and oy <= y <= oy + height):
            return None
        return (
            max(0, min(image.width - 1, int((x - ox) / width * image.width))),
            max(0, min(image.height - 1, int((y - oy) / height * image.height))),
        )

    def _on_press(self, event: tk.Event) -> None:
        if not self._draw_zones:
            return
        point = self._canvas_to_image(event.x, event.y)
        if point is None:
            return
        self._drag_start = (event.x, event.y, point)
        self._drag_item = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline=COLORS["warning"], width=2, dash=(5, 3))

    def _on_drag(self, event: tk.Event) -> None:
        if self._drag_start is None or self._drag_item is None:
            return
        ox, oy, width, height = self._display_box
        x, y = max(ox, min(ox + width, event.x)), max(oy, min(oy + height, event.y))
        self.canvas.coords(self._drag_item, self._drag_start[0], self._drag_start[1], x, y)

    def _on_release(self, event: tk.Event) -> None:
        if self._drag_start is None:
            return
        start = self._drag_start[2]
        end = self._canvas_to_image(event.x, event.y, clamp=True)
        self._drag_start = None
        if self._drag_item is not None:
            self.canvas.delete(self._drag_item)
            self._drag_item = None
        if end is None:
            return
        x1, x2 = sorted((start[0], end[0]))
        y1, y2 = sorted((start[1], end[1]))
        if x2 - x1 >= 5 and y2 - y1 >= 5:
            self.on_zone({"x1": x1, "y1": y1, "x2": x2, "y2": y2})

    def _archive_annotated(self, step: int) -> None:
        with self._lock:
            image = self._raw_image.copy() if self._raw_image is not None else None
            marks = list(self._marks)
        if image is None:
            return
        draw = ImageDraw.Draw(image)
        for x, y, mark_step in marks:
            draw.ellipse((x - 16, y - 16, x + 16, y + 16), outline=COLORS["error"], width=4)
            draw.line((x - 24, y, x + 24, y), fill=COLORS["error"], width=2)
            draw.line((x, y - 24, x, y + 24), fill=COLORS["error"], width=2)
            draw.text((x + 20, y - 16), str(mark_step), fill=COLORS["warning"])
        try:
            _SAVE_DIR.mkdir(parents=True, exist_ok=True)
            path = _SAVE_DIR / f"{time.strftime('%Y%m%d_%H%M%S')}_step{step:03d}.png"
            image.save(path)
            with self._lock:
                self._saved_paths.append(str(path))
            logger.info("Annotated screenshot saved: %s", path)
        except OSError:
            logger.debug("Unable to archive annotated screenshot", exc_info=True)

    def update_texts(self) -> None:
        self.title_label.configure(text=self.t("live_screen"))
        self.save_button.configure(text=self.t("save_image"))
        self.clear_button.configure(text=self.t("clear_marks"))
        self.preview_button.configure(text=self.t("stop_preview") if self._preview_running else self.t("start_preview"))
        if self._raw_image is None:
            self.status_var.set(self.t("preview_offline"))
        self._render()

    def close(self) -> None:
        self.stop_preview()
