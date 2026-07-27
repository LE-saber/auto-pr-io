"""Tkinter log viewer and logging handler."""
from __future__ import annotations

import logging
import queue
import re
import tkinter as tk
from tkinter import ttk


class TkLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: queue.Queue[str] = queue.Queue()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.put(self.format(record))
        except Exception:
            self.handleError(record)


class LogPanel(ttk.LabelFrame):
    def __init__(self, master, handler: TkLogHandler, **kwargs):
        super().__init__(master, text="Run log", **kwargs)
        self.handler = handler
        self._lines: list[str] = []
        self._level_var = tk.StringVar(value="ALL")
        self._filter_var = tk.StringVar(value="")
        self._preset_var = tk.StringVar(value="All")
        self._build_ui()
        self.after(200, self._drain)

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=4, pady=(4, 0))
        ttk.Button(toolbar, text="Clear", command=self.clear, width=8).pack(side=tk.LEFT)
        ttk.Label(toolbar, text="Level").pack(side=tk.LEFT, padx=(8, 3))
        level = ttk.Combobox(
            toolbar,
            textvariable=self._level_var,
            values=["ALL", "DEBUG", "INFO", "WARNING", "ERROR"],
            state="readonly",
            width=9,
        )
        level.pack(side=tk.LEFT)
        level.bind("<<ComboboxSelected>>", lambda _event: self._render())

        ttk.Label(toolbar, text="Filter").pack(side=tk.LEFT, padx=(8, 3))
        filter_entry = ttk.Entry(toolbar, textvariable=self._filter_var, width=22)
        filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._filter_var.trace_add("write", lambda *_: self._render())

        preset = ttk.Combobox(
            toolbar,
            textvariable=self._preset_var,
            values=["All", "SenseVoice", "Click coords", "VLM responses", "ADB actions"],
            state="readonly",
            width=13,
        )
        preset.pack(side=tk.LEFT, padx=(8, 0))
        preset.bind("<<ComboboxSelected>>", lambda _event: self._apply_preset())

        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._text = tk.Text(
            frame,
            height=9,
            wrap="word",
            state="disabled",
            font=("Consolas", 9),
            bg="#0d1117",
            fg="#c9d1d9",
            relief="flat",
        )
        scrollbar = ttk.Scrollbar(frame, command=self._text.yview)
        self._text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def clear(self) -> None:
        self._lines.clear()
        self._text.configure(state="normal")
        self._text.delete("1.0", tk.END)
        self._text.configure(state="disabled")

    _MAX_LINES = 5000

    def append(self, line: str) -> None:
        self._lines.append(line)
        if len(self._lines) > self._MAX_LINES:
            self._lines = self._lines[-self._MAX_LINES:]
            self._render()
            return
        if not self._matches(line):
            return
        self._text.configure(state="normal")
        self._text.insert(tk.END, line + "\n")
        self._text.see(tk.END)
        self._text.configure(state="disabled")

    def _apply_preset(self) -> None:
        preset = self._preset_var.get()
        values = {
            "All": "",
            "SenseVoice": "(realtime sensevoice):",
            "Click coords": "click",
            "VLM responses": "VLM response",
            "ADB actions": "Executing adb action",
        }
        self._filter_var.set(values.get(preset, ""))
        self._render()

    def _render(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", tk.END)
        for line in self._lines:
            if self._matches(line):
                self._text.insert(tk.END, line + "\n")
        self._text.see(tk.END)
        self._text.configure(state="disabled")

    def _matches(self, line: str) -> bool:
        level = self._level_var.get()
        if level != "ALL" and f"[{level}]" not in line:
            return False
        needle = self._filter_var.get().strip()
        if not needle:
            return True
        if needle.lower() in line.lower():
            return True
        if needle.lower() == "click":
            return bool(re.search(r"\bclick\b|Executing adb action: .*'type': 'click'|\(\d+,\d+\)", line, re.I))
        return False

    def _drain(self) -> None:
        while True:
            try:
                line = self.handler.records.get_nowait()
            except queue.Empty:
                break
            self.append(line)
        self.after(200, self._drain)
