"""Desktop capture selectors for the redesigned interface."""
from __future__ import annotations

import ctypes
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from ui_v2.theme import COLORS


def list_visible_windows() -> list[dict]:
    """Enumerate captureable top-level windows without legacy GUI code."""
    import psutil
    import win32con
    import win32gui
    import win32process

    windows: list[dict] = []

    def collect(hwnd: int, _extra: object) -> bool:
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd).strip()
        if not title:
            return True
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        if ex_style & win32con.WS_EX_TOOLWINDOW:
            return True
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            process = psutil.Process(pid).name()
        except (psutil.Error, OSError):
            process = ""
        windows.append({"hwnd": hwnd, "title": title, "process": process, "pid": pid})
        return True

    win32gui.EnumWindows(collect, None)
    return windows


class RegionPicker(tk.Toplevel):
    def __init__(self, master, translate: Callable[..., str], callback: Callable[[tuple[int, int, int, int] | None], None]) -> None:
        super().__init__(master)
        self.t = translate
        self.callback = callback
        self.start: tuple[int, int] | None = None
        self.rect = None
        user32 = ctypes.windll.user32
        left = user32.GetSystemMetrics(76)
        top = user32.GetSystemMetrics(77)
        width = user32.GetSystemMetrics(78)
        height = user32.GetSystemMetrics(79)
        self._origin = (left, top)
        self.overrideredirect(True)
        self.geometry(f"{width}x{height}{left:+d}{top:+d}")
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.30)
        self.configure(background=COLORS["bg"])
        self.canvas = tk.Canvas(self, background=COLORS["bg"], cursor="crosshair", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.create_text(width // 2, 40, text=self.t("drag_capture"), fill=COLORS["text"], font=("Segoe UI", 12, "bold"))
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.bind("<Escape>", lambda _event: self._finish(None))
        self.focus_force()

    def _press(self, event: tk.Event) -> None:
        self.start = (event.x, event.y)
        self.rect = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline=COLORS["accent"], width=3, fill=COLORS["surface_2"])

    def _drag(self, event: tk.Event) -> None:
        if self.start and self.rect:
            self.canvas.coords(self.rect, self.start[0], self.start[1], event.x, event.y)

    def _release(self, event: tk.Event) -> None:
        if not self.start:
            self._finish(None)
            return
        x1, x2 = sorted((self.start[0], event.x))
        y1, y2 = sorted((self.start[1], event.y))
        if x2 - x1 < 8 or y2 - y1 < 8:
            self._finish(None)
            return
        ox, oy = self._origin
        self._finish((x1 + ox, y1 + oy, x2 + ox, y2 + oy))

    def _finish(self, value: tuple[int, int, int, int] | None) -> None:
        self.destroy()
        self.callback(value)


class WindowPicker(tk.Toplevel):
    def __init__(self, master, translate: Callable[..., str], callback: Callable[[int | None], None]) -> None:
        super().__init__(master)
        self.t = translate
        self.callback = callback
        self.title(self.t("select_window"))
        self.geometry("760x460")
        self.minsize(600, 360)
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: self._finish(None))
        frame = ttk.Frame(self, style="App.TFrame", padding=14)
        frame.pack(fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(frame, columns=("title", "process", "pid"), show="headings", selectmode="browse")
        self.tree.heading("title", text=self.t("window_title"))
        self.tree.heading("process", text=self.t("process"))
        self.tree.heading("pid", text="PID")
        self.tree.column("title", width=430)
        self.tree.column("process", width=170, stretch=False)
        self.tree.column("pid", width=90, stretch=False, anchor="e")
        scroll = ttk.Scrollbar(frame, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(fill=tk.BOTH, expand=True)
        buttons = ttk.Frame(self, style="Header.TFrame", padding=(14, 10))
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text=self.t("choose"), style="Accent.TButton", command=self._confirm).pack(side=tk.RIGHT)
        ttk.Button(buttons, text=self.t("cancel"), command=lambda: self._finish(None)).pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(buttons, text=self.t("refresh"), command=self._refresh).pack(side=tk.LEFT)
        self.tree.bind("<Double-1>", lambda _event: self._confirm())
        self.tree.bind("<Return>", lambda _event: self._confirm())
        self.bind("<Escape>", lambda _event: self._finish(None))
        self._refresh()

    def _refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        try:
            windows = list_visible_windows()
        except (ImportError, OSError) as exc:
            messagebox.showerror(
                self.t("select_window"),
                self.t("window_list_failed", error=str(exc)),
                parent=self,
            )
            return
        for window in windows:
            hwnd = int(window["hwnd"])
            self.tree.insert("", tk.END, iid=str(hwnd), values=(window["title"], window["process"], window["pid"]))

    def _confirm(self) -> None:
        selected = self.tree.selection()
        if selected:
            self._finish(int(selected[0]))

    def _finish(self, hwnd: int | None) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
        self.callback(hwnd)
