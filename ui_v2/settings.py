"""Settings window for the redesigned interface."""
from __future__ import annotations

import tkinter as tk
from copy import deepcopy
from tkinter import messagebox, ttk
from typing import Callable

from settings_store import load_settings, save_settings
from ui_v2.theme import COLORS, text_widget_options


PROVIDERS = [
    ("zhipu", "Zhipu / GLM"),
    ("volcengine", "ByteDance / Volcengine Ark"),
    ("qwen_vl", "Qwen VL / DashScope"),
    ("openai", "OpenAI"),
    ("anthropic", "Anthropic"),
    ("deepseek_vision", "DeepSeek Vision"),
    ("vlm_coords", "Generic VLM coordinates"),
    ("custom", "Custom OpenAI-compatible"),
    ("autoglm_phone", "AutoGLM-Phone"),
]


class SettingsWindow(tk.Toplevel):
    def __init__(self, master, translate: Callable[..., str], on_save: Callable[[], None]) -> None:
        super().__init__(master)
        self.t = translate
        self.on_save = on_save
        self.settings = deepcopy(load_settings())
        self.title(self.t("settings"))
        self.geometry("820x610")
        self.minsize(720, 520)
        self.transient(master)
        self.grab_set()
        self.configure(background=COLORS["bg"])
        self._provider_by_label = {label: key for key, label in PROVIDERS}
        self._provider_label_by_key = dict(PROVIDERS)
        self._active_provider = "zhipu"
        self._pages: dict[str, ttk.Frame] = {}
        self._nav_buttons: dict[str, ttk.Button] = {}
        self._build()
        self._show_page("models")

    def _build(self) -> None:
        shell = ttk.Frame(self, style="App.TFrame")
        shell.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(shell, style="Header.TFrame", padding=(18, 14))
        header.pack(fill=tk.X)
        ttk.Label(header, text=self.t("settings"), style="Heading.TLabel").pack(side=tk.LEFT)

        body = ttk.Frame(shell, style="App.TFrame")
        body.pack(fill=tk.BOTH, expand=True)
        nav = ttk.Frame(body, style="Nav.TFrame", width=190)
        nav.pack(side=tk.LEFT, fill=tk.Y)
        nav.pack_propagate(False)
        content = ttk.Frame(body, style="App.TFrame", padding=18)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        pages = [
            ("models", "settings_models"),
            ("adb", "settings_adb"),
            ("audio", "settings_audio"),
            ("oracle", "settings_oracle"),
        ]
        for key, label_key in pages:
            button = ttk.Button(nav, text=self.t(label_key), style="Nav.TButton", command=lambda name=key: self._show_page(name))
            button.pack(fill=tk.X, padx=8, pady=(8 if key == "models" else 0, 2))
            self._nav_buttons[key] = button
            page = ttk.Frame(content, style="App.TFrame")
            page.grid(row=0, column=0, sticky="nsew")
            self._pages[key] = page
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)

        self._build_models(self._pages["models"])
        self._build_adb(self._pages["adb"])
        self._build_audio(self._pages["audio"])
        self._build_oracle(self._pages["oracle"])

        footer = ttk.Frame(shell, style="Header.TFrame", padding=(18, 12))
        footer.pack(fill=tk.X)
        ttk.Button(footer, text=self.t("save"), style="Accent.TButton", command=self._save).pack(side=tk.RIGHT)
        ttk.Button(footer, text=self.t("cancel"), command=self.destroy).pack(side=tk.RIGHT, padx=(0, 8))

    def _page_title(self, page: ttk.Frame, key: str) -> None:
        ttk.Label(page, text=self.t(key), style="Heading.TLabel").pack(anchor="w", pady=(0, 18))

    def _row(self, parent, label: str, variable: tk.Variable, secret: bool = False) -> ttk.Entry:
        row = ttk.Frame(parent, style="App.TFrame")
        row.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(row, text=label, width=20).pack(side=tk.LEFT, anchor="n", pady=7)
        entry = ttk.Entry(row, textvariable=variable, show="*" if secret else "")
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        return entry

    def _build_models(self, page: ttk.Frame) -> None:
        self._page_title(page, "settings_models")
        row = ttk.Frame(page, style="App.TFrame")
        row.pack(fill=tk.X, pady=(0, 16))
        ttk.Label(row, text=self.t("provider"), width=20).pack(side=tk.LEFT)
        self.provider_var = tk.StringVar(value=self._provider_label_by_key[self._active_provider])
        provider = ttk.Combobox(row, textvariable=self.provider_var, values=[label for _, label in PROVIDERS], state="readonly")
        provider.pack(side=tk.LEFT, fill=tk.X, expand=True)
        provider.bind("<<ComboboxSelected>>", self._change_provider)

        self.api_key_var = tk.StringVar()
        self.api_base_var = tk.StringVar()
        self.provider_model_var = tk.StringVar()
        self._row(page, self.t("api_key"), self.api_key_var, secret=True)
        self._row(page, self.t("api_base"), self.api_base_var)
        self._row(page, self.t("default_model"), self.provider_model_var)
        self._load_provider("zhipu")

    def _build_adb(self, page: ttk.Frame) -> None:
        self._page_title(page, "settings_adb")
        data = self.settings.setdefault("adb", {})
        self.adb_path_var = tk.StringVar(value=data.get("path", "adb"))
        self.last_device_var = tk.StringVar(value=data.get("last_device_id", ""))
        self._row(page, self.t("adb_path"), self.adb_path_var)
        self._row(page, self.t("last_device"), self.last_device_var)

    def _build_audio(self, page: ttk.Frame) -> None:
        self._page_title(page, "settings_audio")
        data = self.settings.setdefault("audio", {})
        self.sensevoice_var = tk.StringVar(value=data.get("sensevoice_model", "iic/SenseVoiceSmall"))
        self._row(page, self.t("sensevoice_model"), self.sensevoice_var)
        info = tk.Text(page, height=5, wrap="word", **text_widget_options(10))
        info.insert("1.0", self.t("audio_settings_hint"))
        info.configure(state="disabled")
        info.pack(fill=tk.X, pady=(8, 0))

    def _build_oracle(self, page: ttk.Frame) -> None:
        self._page_title(page, "settings_oracle")
        data = self.settings.setdefault("oracle", {})
        self.oracle_enabled_var = tk.BooleanVar(value=bool(data.get("enabled", False)))
        ttk.Checkbutton(page, text=self.t("oracle_enabled"), variable=self.oracle_enabled_var).pack(anchor="w", pady=(0, 14))
        self.oracle_provider_var = tk.StringVar(value=data.get("provider", "zhipu"))
        self.oracle_key_var = tk.StringVar(value=data.get("api_key", ""))
        self.oracle_base_var = tk.StringVar(value=data.get("api_base", ""))
        self.oracle_model_var = tk.StringVar(value=data.get("model", "glm-4.6v-flashx"))
        self.oracle_timeout_var = tk.StringVar(value=str(data.get("timeout", 120)))

        row = ttk.Frame(page, style="App.TFrame")
        row.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(row, text=self.t("oracle_provider"), width=20).pack(side=tk.LEFT)
        self.oracle_provider_combo = ttk.Combobox(
            row,
            textvariable=self.oracle_provider_var,
            values=["zhipu", "volcengine", "qwen_vl"],
            state="readonly",
        )
        self.oracle_provider_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.oracle_provider_combo.bind(
            "<<ComboboxSelected>>",
            self._oracle_provider_changed,
        )
        self._row(page, self.t("api_key"), self.oracle_key_var, secret=True)
        self._row(page, self.t("api_base"), self.oracle_base_var)
        self._row(page, self.t("model"), self.oracle_model_var)
        self._row(page, self.t("timeout"), self.oracle_timeout_var)

    def _show_page(self, name: str) -> None:
        self._pages[name].tkraise()
        for key, button in self._nav_buttons.items():
            button.configure(style="NavActive.TButton" if key == name else "Nav.TButton")

    def _store_provider(self) -> None:
        data = self.settings.setdefault("providers", {}).setdefault(self._active_provider, {})
        data["api_key"] = self.api_key_var.get().strip()
        data["api_base"] = self.api_base_var.get().strip()
        data["model"] = self.provider_model_var.get().strip()

    def _load_provider(self, provider: str) -> None:
        data = self.settings.setdefault("providers", {}).setdefault(provider, {})
        self._active_provider = provider
        self.api_key_var.set(data.get("api_key", ""))
        self.api_base_var.set(data.get("api_base", ""))
        self.provider_model_var.set(data.get("model", ""))

    def _change_provider(self, _event=None) -> None:
        self._store_provider()
        provider = self._provider_by_label.get(self.provider_var.get(), "zhipu")
        self._load_provider(provider)

    def _oracle_provider_changed(self, _event=None) -> None:
        self._store_provider()
        provider = self.oracle_provider_var.get().strip() or "zhipu"
        data = self.settings.setdefault("providers", {}).get(provider, {})
        self.oracle_key_var.set(data.get("api_key", ""))
        self.oracle_base_var.set(data.get("api_base", ""))
        self.oracle_model_var.set(data.get("model", ""))

    def _save(self) -> None:
        self._store_provider()
        self.settings.setdefault("adb", {}).update({
            "path": self.adb_path_var.get().strip() or "adb",
            "last_device_id": self.last_device_var.get().strip(),
        })
        self.settings.setdefault("audio", {})["sensevoice_model"] = self.sensevoice_var.get().strip() or "iic/SenseVoiceSmall"
        oracle = self.settings.setdefault("oracle", {})
        oracle.update({
            "enabled": self.oracle_enabled_var.get(),
            "provider": self.oracle_provider_var.get().strip(),
            "api_key": self.oracle_key_var.get().strip(),
            "api_base": self.oracle_base_var.get().strip(),
            "model": self.oracle_model_var.get().strip(),
            "timeout": self.oracle_timeout_var.get().strip() or "120",
        })
        try:
            save_settings(self.settings)
        except OSError as exc:
            messagebox.showerror(self.t("settings"), str(exc), parent=self)
            return
        self.on_save()
        self.destroy()
