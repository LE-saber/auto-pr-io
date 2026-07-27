"""Window enumeration and selection dialog for auto-pr-io."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

import psutil
import win32con
import win32gui
import win32process


def list_visible_windows() -> list[dict]:
    """Return visible top-level application windows.

    Each entry: ``{hwnd, title, process, pid}``
    Alias kept for backwards-compatibility; delegates to list_windows().
    """
    return list_windows()


def list_windows() -> list[dict]:
    """Return visible top-level application windows."""
    windows: list[dict] = []

    def enum_callback(hwnd: int, _extra: object) -> bool:
        if not _is_selectable_window(hwnd):
            return True

        title = win32gui.GetWindowText(hwnd).strip()
        _, pid = win32process.GetWindowThreadProcessId(hwnd)

        try:
            process = psutil.Process(pid).name()
        except (psutil.Error, OSError):
            process = ""

        windows.append({"hwnd": hwnd, "title": title, "process": process, "pid": pid})
        return True

    win32gui.EnumWindows(enum_callback, None)
    return windows


def _is_selectable_window(hwnd: int) -> bool:
    if not win32gui.IsWindowVisible(hwnd):
        return False
    if not win32gui.GetWindowText(hwnd).strip():
        return False
    ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    if ex_style & win32con.WS_EX_TOOLWINDOW:
        return False
    return True


class WindowSelector(tk.Toplevel):
    """Modal dialog for choosing a visible top-level window."""

    def __init__(self, master, callback: Callable[[int | None], None]):
        super().__init__(master)
        self.callback = callback
        self.selected_hwnd: int | None = None

        self.title("选择窗口 — Select Window")
        self.geometry("760x420")
        self.minsize(560, 320)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self._build_ui()
        self._refresh()

        self.grab_set()
        self.focus_set()
        self.wait_visibility()
        self._center_on_master(master)

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=10)
        container.pack(fill=tk.BOTH, expand=True)

        columns = ("title", "process", "hwnd")
        self.tree = ttk.Treeview(
            container, columns=columns, show="headings", selectmode="browse",
        )
        self.tree.heading("title",   text="窗口标题 Title")
        self.tree.heading("process", text="进程 Process")
        self.tree.heading("hwnd",    text="HWND")

        self.tree.column("title",   width=440, minwidth=180, stretch=True)
        self.tree.column("process", width=160, minwidth=100, stretch=False)
        self.tree.column("hwnd",    width=100, minwidth=80,  stretch=False, anchor=tk.E)

        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        button_frame = ttk.Frame(container)
        button_frame.grid(row=1, column=0, columnspan=2, sticky="e", pady=(10, 0))

        ttk.Button(button_frame, text="🔄 刷新", command=self._refresh).pack(
            side=tk.LEFT, padx=(0, 8))
        ttk.Button(button_frame, text="确认 OK", command=self._confirm).pack(
            side=tk.LEFT, padx=(0, 8))
        ttk.Button(button_frame, text="取消 Cancel", command=self._cancel).pack(
            side=tk.LEFT)

        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", lambda _: self._confirm())
        self.tree.bind("<Return>",   lambda _: self._confirm())
        self.bind("<Escape>",        lambda _: self._cancel())

    def _refresh(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for window in list_windows():
            hwnd = int(window["hwnd"])
            self.tree.insert("", tk.END, iid=str(hwnd),
                             values=(str(window["title"]),
                                     str(window["process"]),
                                     str(hwnd)))

    def _confirm(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        self.selected_hwnd = int(selection[0])
        self._finish(self.selected_hwnd)

    def _cancel(self) -> None:
        self._finish(None)

    def _finish(self, hwnd: int | None) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
        self.callback(hwnd)

    def _center_on_master(self, master) -> None:
        self.update_idletasks()
        width  = self.winfo_width()
        height = self.winfo_height()
        try:
            master.update_idletasks()
            x = master.winfo_rootx() + (master.winfo_width()  - width)  // 2
            y = master.winfo_rooty() + (master.winfo_height() - height) // 2
        except tk.TclError:
            x = (self.winfo_screenwidth()  - width)  // 2
            y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
