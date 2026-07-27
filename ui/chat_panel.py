"""Chat/observe-mode response panel."""
from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import ttk


class ChatPanel(ttk.Frame):
    """Dedicated read-only output area for Chat mode model replies."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 2))
        ttk.Button(toolbar, text="Clear", command=self.clear).pack(side=tk.RIGHT)
        ttk.Button(toolbar, text="Copy", command=self.copy_all).pack(side=tk.RIGHT, padx=(0, 6))

        inner = ttk.Frame(self)
        inner.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        inner.rowconfigure(0, weight=1)
        inner.columnconfigure(0, weight=1)

        scrollbar = ttk.Scrollbar(inner, orient="vertical")
        self._text = tk.Text(
            inner,
            wrap="word",
            state="disabled",
            height=10,
            bg="#0d1117",
            fg="#d6e2ff",
            insertbackground="white",
            relief="flat",
            font=("Segoe UI", 9, "bold"),
            yscrollcommand=scrollbar.set,
        )
        scrollbar.configure(command=self._text.yview)
        self._text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

    def append_message(self, text: str, title: str = "Chat") -> None:
        text = (text or "").strip()
        if not text:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._text.configure(state="normal")
        if self._text.index("end-1c") != "1.0":
            self._text.insert(tk.END, "\n\n")
        self._text.insert(tk.END, f"[{timestamp}] {title}\n", ("header",))
        self._text.insert(tk.END, text)
        self._text.tag_configure("header", foreground="#7ee787")
        self._text.see(tk.END)
        self._text.configure(state="disabled")

    def clear(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", tk.END)
        self._text.configure(state="disabled")

    def copy_all(self) -> None:
        text = self._text.get("1.0", tk.END).strip()
        self.clipboard_clear()
        self.clipboard_append(text)
