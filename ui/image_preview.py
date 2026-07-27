"""Center panel: resizable screenshot preview canvas."""
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk


class ImagePreviewPanel(ttk.LabelFrame):
    def __init__(self, master, language: str = "zh-CN", **kwargs):
        from ui.i18n import t

        self._language = language
        super().__init__(master, text=t(language, "screenshot_preview"), **kwargs)
        self._photo = None
        self._image = None
        self._forbidden_rects: list[dict] = []
        self._forbidden_select_enabled = False
        self._forbidden_callback = None
        self._display_box = (0, 0, 0, 0)
        self._drag_start = None
        self._drag_item = None

        self.canvas = tk.Canvas(self, bg="#1e1e1e", cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self._placeholder_id = self.canvas.create_text(
            0, 0, text=t(self._language, "no_screenshot_yet"),
            fill="#555555", font=("Segoe UI", 14), anchor="center", justify="center"
        )
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<ButtonPress-1>", self._on_forbidden_press)
        self.canvas.bind("<B1-Motion>", self._on_forbidden_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_forbidden_release)

    # ------------------------------------------------------------------
    def fit_image(self, pil_image: Image.Image):
        self._image = pil_image
        self._render()

    def clear(self):
        self._image = None
        self._photo = None
        self.canvas.delete("img")
        self.canvas.delete("forbidden")
        self._show_placeholder()

    def set_forbidden_rects(self, rects: list[dict]) -> None:
        self._forbidden_rects = list(rects or [])
        self._render()

    def set_forbidden_selection_enabled(self, enabled: bool) -> None:
        self._forbidden_select_enabled = bool(enabled)
        self.canvas.configure(cursor="crosshair" if enabled else "")

    def set_forbidden_rect_callback(self, callback) -> None:
        self._forbidden_callback = callback

    # ------------------------------------------------------------------
    def _render(self):
        if self._image is None:
            return
        self.canvas.delete("img")
        self._hide_placeholder()

        cw = self.canvas.winfo_width() or 600
        ch = self.canvas.winfo_height() or 400
        img = self._image.copy()
        iw, ih = img.size
        img.thumbnail((cw, ch), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(img)
        dw, dh = img.size
        ox = (cw - dw) // 2
        oy = (ch - dh) // 2
        self._display_box = (ox, oy, dw, dh)
        self.canvas.create_image(ox, oy, anchor="nw", image=self._photo, tags="img")
        self._draw_forbidden_rects(iw, ih)

    def _on_resize(self, event):
        self._render()

    def _show_placeholder(self):
        cw = self.canvas.winfo_width() or 300
        ch = self.canvas.winfo_height() or 200
        self.canvas.coords(self._placeholder_id, cw // 2, ch // 2)
        self.canvas.itemconfigure(self._placeholder_id, state="normal")

    def _hide_placeholder(self):
        self.canvas.itemconfigure(self._placeholder_id, state="hidden")

    def set_language(self, language: str) -> None:
        from ui.i18n import t

        self._language = language
        self.configure(text=t(language, "screenshot_preview"))
        self.canvas.itemconfigure(self._placeholder_id, text=t(language, "no_screenshot_yet"))

    def _draw_forbidden_rects(self, iw: int, ih: int) -> None:
        self.canvas.delete("forbidden")
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
            self.canvas.create_rectangle(
                x1, y1, x2, y2,
                outline="#ff3b30", width=2, fill="#ff3b30", stipple="gray25",
                tags="forbidden",
            )
            self.canvas.create_text(
                x1 + 6, y1 + 6, text=str(idx), anchor="nw",
                fill="#ffffff", font=("Segoe UI", 9, "bold"), tags="forbidden",
            )

    def _canvas_to_image(self, cx: int, cy: int, clamp: bool = False) -> tuple[int, int] | None:
        if self._image is None:
            return None
        ox, oy, dw, dh = self._display_box
        if dw <= 0 or dh <= 0:
            return None
        if clamp:
            cx = max(ox, min(ox + dw, cx))
            cy = max(oy, min(oy + dh, cy))
        elif not (ox <= cx <= ox + dw and oy <= cy <= oy + dh):
            return None
        iw, ih = self._image.size
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
            self.canvas.delete(self._drag_item)
        self._drag_item = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="#ffcc00", width=2, dash=(4, 2), tags="forbidden",
        )

    def _on_forbidden_drag(self, event) -> None:
        if not self._forbidden_select_enabled or not self._drag_start or not self._drag_item:
            return
        ox, oy, dw, dh = self._display_box
        x = max(ox, min(ox + dw, event.x))
        y = max(oy, min(oy + dh, event.y))
        self.canvas.coords(self._drag_item, self._drag_start[0], self._drag_start[1], x, y)

    def _on_forbidden_release(self, event) -> None:
        if not self._forbidden_select_enabled or not self._drag_start:
            return
        start = self._drag_start[2]
        end = self._canvas_to_image(event.x, event.y, clamp=True)
        self._drag_start = None
        if self._drag_item:
            self.canvas.delete(self._drag_item)
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
