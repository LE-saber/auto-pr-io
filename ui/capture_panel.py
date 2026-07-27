"""Left panel: screenshot capture controls."""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional
from PIL import Image, ImageTk
import logging

logger = logging.getLogger(__name__)


class CapturePanel(ttk.LabelFrame):
    def __init__(self, master, on_capture: Callable[[Image.Image], None], **kwargs):
        super().__init__(master, text="Capture", **kwargs)
        self._on_capture = on_capture
        self._thumb_photo = None
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        btn_opts = {"padding": (6, 7)}

        ttk.Button(self, text="Fullscreen", command=self._capture_fullscreen,
                   **btn_opts).pack(pady=(10, 3), padx=10, fill=tk.X)
        ttk.Button(self, text="Select Region", command=self._capture_region,
                   **btn_opts).pack(pady=3, padx=10, fill=tk.X)
        ttk.Button(self, text="Select Window", command=self._capture_window,
                   **btn_opts).pack(pady=3, padx=10, fill=tk.X)

        ttk.Separator(self, orient="horizontal").pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(self, text="Preview", font=("Segoe UI", 8, "bold")).pack(padx=10, anchor="w")
        self._thumb_label = ttk.Label(self, relief="sunken", width=18, anchor="center")
        self._thumb_label.pack(padx=10, pady=(4, 8))
        self._clear_thumb()

    # ------------------------------------------------------------------
    def _capture_fullscreen(self):
        try:
            from windows.capture import capture_fullscreen
            img = capture_fullscreen()
            self._notify(img)
        except Exception as e:
            logger.exception("Fullscreen capture failed")
            messagebox.showerror("Capture failed", str(e))

    def _capture_region(self):
        try:
            from windows.capture import RegionCaptureOverlay
            root = self.winfo_toplevel()
            root.withdraw()

            def _on_region(x1, y1, x2, y2):
                root.deiconify()
                if x1 is None:
                    return
                from windows.capture import capture_region
                try:
                    img = capture_region(x1, y1, x2, y2)
                    self._notify(img)
                except Exception as e:
                    logger.exception("Region capture failed")
                    messagebox.showerror("Capture failed", str(e))

            RegionCaptureOverlay(root, callback=_on_region)
        except Exception as e:
            logger.exception("Region overlay failed")
            self.winfo_toplevel().deiconify()
            messagebox.showerror("Capture failed", str(e))

    def _capture_window(self):
        try:
            from windows.window_selector import WindowSelector
            root = self.winfo_toplevel()

            def _on_hwnd(hwnd: Optional[int]):
                if hwnd is None:
                    return
                from windows.capture import capture_window
                try:
                    img = capture_window(hwnd)
                    self._notify(img)
                except Exception as e:
                    logger.exception("Window capture failed")
                    messagebox.showerror("Capture failed", str(e))

            WindowSelector(root, callback=_on_hwnd)
        except Exception as e:
            logger.exception("Window selector failed")
            messagebox.showerror("Capture failed", str(e))

    # ------------------------------------------------------------------
    def _notify(self, img: Image.Image):
        self._update_thumb(img)
        self._on_capture(img)

    def _update_thumb(self, img: Image.Image):
        thumb = img.copy()
        thumb.thumbnail((140, 90), Image.LANCZOS)
        self._thumb_photo = ImageTk.PhotoImage(thumb)
        self._thumb_label.configure(image=self._thumb_photo, text="")

    def _clear_thumb(self):
        self._thumb_label.configure(image="", text="— empty —")
