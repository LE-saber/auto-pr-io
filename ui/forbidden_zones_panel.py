"""Forbidden click-zone preset management."""
from __future__ import annotations

import tkinter as tk
from tkinter import simpledialog, ttk

from auto_click.forbidden_zones import normalize_rects
from settings_store import load_settings, save_settings


class ForbiddenZonesPanel(ttk.LabelFrame):
    def __init__(self, master, on_change=None, language: str = "zh-CN", **kwargs):
        from ui.i18n import t

        self._language = language
        super().__init__(master, text=t(self._language, "forbidden_zones"), **kwargs)
        self._on_change = on_change
        self._presets: dict[str, dict] = {}
        self._selected = tk.StringVar(value="")
        self._draw_var = tk.BooleanVar(value=False)
        self._rects: list[dict] = []
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        from ui.i18n import t

        self.columnconfigure(1, weight=1)
        self._preset_label = ttk.Label(self, text=t(self._language, "preset"))
        self._preset_label.grid(row=0, column=0, sticky="w", padx=(8, 4), pady=(8, 2))
        self._preset_cb = ttk.Combobox(self, textvariable=self._selected, state="readonly", width=18)
        self._preset_cb.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(8, 2))
        self._preset_cb.bind("<<ComboboxSelected>>", lambda _e: self._select_preset(self._selected.get()))

        btns = ttk.Frame(self)
        btns.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=2)
        self._new_btn = ttk.Button(btns, text=t(self._language, "new"), command=self._new_preset)
        self._new_btn.pack(side=tk.LEFT)
        self._save_btn = ttk.Button(btns, text=t(self._language, "save"), command=self._save_current)
        self._save_btn.pack(side=tk.LEFT, padx=(4, 0))
        self._delete_btn = ttk.Button(btns, text=t(self._language, "delete"), command=self._delete_preset)
        self._delete_btn.pack(side=tk.LEFT, padx=(4, 0))
        self._clear_btn = ttk.Button(btns, text=t(self._language, "clear_rects"), command=self._clear_rects)
        self._clear_btn.pack(side=tk.LEFT, padx=(4, 0))

        self._draw_check = ttk.Checkbutton(
            self,
            text=t(self._language, "draw_forbidden"),
            variable=self._draw_var,
            command=self._emit_change,
        )
        self._draw_check.grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(2, 4))

        self._info = tk.StringVar(value=t(self._language, "no_preset"))
        ttk.Label(self, textvariable=self._info, font=("Segoe UI", 8), foreground="#666666").grid(
            row=3, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 8)
        )

    def reload(self) -> None:
        data = load_settings().get("forbidden_zones", {})
        presets = data.get("presets", {}) if isinstance(data, dict) else {}
        self._presets = presets if isinstance(presets, dict) else {}
        names = sorted(self._presets)
        self._preset_cb.configure(values=names)
        selected = data.get("selected", "") if isinstance(data, dict) else ""
        if selected not in self._presets:
            selected = names[0] if names else ""
        self._selected.set(selected)
        self._load_selected_rects()
        self._emit_change()

    def current_rects(self) -> list[dict]:
        return normalize_rects(self._rects)

    def draw_enabled(self) -> bool:
        return bool(self._draw_var.get())

    def add_rect(self, rect: dict) -> None:
        if not self._selected.get():
            self._new_preset(default_name="Default")
        self._rects = normalize_rects([*self._rects, rect])
        self._save_current()

    def _new_preset(self, default_name: str = "") -> None:
        from ui.i18n import t

        name = simpledialog.askstring(
            t(self._language, "new_forbidden_preset"),
            t(self._language, "preset_name"),
            initialvalue=default_name,
            parent=self,
        )
        if not name:
            return
        name = name.strip()
        if not name:
            return
        self._presets.setdefault(name, {"rects": []})
        self._selected.set(name)
        self._rects = normalize_rects(self._presets[name].get("rects", []))
        self._save_all()
        self._emit_change()

    def _select_preset(self, name: str) -> None:
        if name:
            self._save_selected_name(name)
        self._load_selected_rects()
        self._emit_change()

    def _load_selected_rects(self) -> None:
        preset = self._presets.get(self._selected.get(), {})
        self._rects = normalize_rects(preset.get("rects", []) if isinstance(preset, dict) else [])
        self._update_info()

    def _save_current(self) -> None:
        name = self._selected.get()
        if not name:
            self._new_preset(default_name="Default")
            return
        self._presets[name] = {"rects": normalize_rects(self._rects)}
        self._save_all()
        self._emit_change()

    def _delete_preset(self) -> None:
        name = self._selected.get()
        if not name:
            return
        self._presets.pop(name, None)
        names = sorted(self._presets)
        self._preset_cb.configure(values=names)
        self._selected.set(names[0] if names else "")
        self._load_selected_rects()
        self._save_all()
        self._emit_change()

    def _clear_rects(self) -> None:
        self._rects = []
        self._save_current()

    def _save_selected_name(self, name: str) -> None:
        settings = load_settings()
        settings.setdefault("forbidden_zones", {})["selected"] = name
        save_settings(settings)

    def _save_all(self) -> None:
        settings = load_settings()
        settings["forbidden_zones"] = {
            "selected": self._selected.get(),
            "presets": self._presets,
        }
        save_settings(settings)
        self._preset_cb.configure(values=sorted(self._presets))
        self._update_info()

    def _update_info(self) -> None:
        from ui.i18n import t

        name = self._selected.get() or t(self._language, "no_preset")
        self._info.set(t(self._language, "rect_count").format(name=name, count=len(self._rects)))

    def _emit_change(self) -> None:
        self._update_info()
        if self._on_change:
            self._on_change()

    def set_language(self, language: str) -> None:
        from ui.i18n import t

        self._language = language
        self.configure(text=t(language, "forbidden_zones"))
        self._preset_label.configure(text=t(language, "preset"))
        self._new_btn.configure(text=t(language, "new"))
        self._save_btn.configure(text=t(language, "save"))
        self._delete_btn.configure(text=t(language, "delete"))
        self._clear_btn.configure(text=t(language, "clear_rects"))
        self._draw_check.configure(text=t(language, "draw_forbidden"))
        self._update_info()
