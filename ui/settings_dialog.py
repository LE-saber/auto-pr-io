"""Settings dialog for API credentials and local tools."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

from settings_store import load_settings, save_settings


class SettingsDialog(tk.Toplevel):
    def __init__(self, master, on_save: Optional[Callable[[], None]] = None):
        super().__init__(master)
        self.title("Settings")
        self.geometry("640x560")
        self.minsize(560, 480)
        self.transient(master)
        self.grab_set()
        self.on_save = on_save
        self.settings = load_settings()
        self.vars: dict[tuple[str, str], tk.StringVar] = {}
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=10)
        container.pack(fill=tk.BOTH, expand=True)

        hint = (
            "Store API keys and local paths here. Main panels read these settings "
            "when you start a task."
        )
        ttk.Label(container, text=hint, wraplength=580).pack(fill=tk.X, pady=(0, 8))

        notebook = ttk.Notebook(container)
        notebook.pack(fill=tk.BOTH, expand=True)
        self._build_api_tab(notebook)
        self._build_adb_tab(notebook)
        self._build_audio_tab(notebook)
        self._build_oracle_tab(notebook)

        buttons = ttk.Frame(container)
        buttons.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(buttons, text="Save", command=self._save).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(
            side=tk.RIGHT, padx=(0, 8)
        )

    def _build_api_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="API")

        providers = [
            ("openai", "OpenAI"),
            ("anthropic", "Anthropic"),
            ("zhipu", "Zhipu (GLM)"),
            ("qwen_vl", "Qwen VL / DashScope"),
            ("deepseek_vision", "DeepSeek Vision (Phone ADB)"),
            ("custom", "Custom OpenAI-compatible"),
            ("vlm_coords", "Generic VLM coordinates"),
            ("autoglm_phone", "AutoGLM-Phone"),
        ]
        _std = [("api_key", "API Key", True), ("api_base", "API Base", False), ("model", "Default model", False)]
        fields = {
            "openai":           _std,
            "anthropic":        [("api_key", "API Key", True), ("model", "Default model", False)],
            "zhipu":            _std,
            "qwen_vl":          _std,
            "deepseek_vision":  _std,
            "custom":           _std,
            "vlm_coords":       _std,
            "autoglm_phone":    _std,
        }

        canvas = tk.Canvas(tab, highlightthickness=0)
        scrollbar = ttk.Scrollbar(tab, command=canvas.yview)
        body = ttk.Frame(canvas)
        body.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        providers_data = self.settings.setdefault("providers", {})
        for provider, title in providers:
            frame = ttk.LabelFrame(body, text=title)
            frame.pack(fill=tk.X, pady=(0, 8))
            provider_data = providers_data.setdefault(provider, {})
            for field, label, secret in fields[provider]:
                self._field(frame, provider, field, label, provider_data.get(field, ""), secret)

    def _build_adb_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="ADB")
        adb_data = self.settings.setdefault("adb", {})
        self._field(tab, "adb", "path", "ADB path", adb_data.get("path", "adb"), False)
        self._field(
            tab,
            "adb",
            "last_device_id",
            "Last selected device ID",
            adb_data.get("last_device_id", ""),
            False,
        )
        text = (
            "Connect your phone with USB debugging enabled, then use the Auto-click "
            "panel's Refresh button to detect available devices."
        )
        ttk.Label(tab, text=text, wraplength=560).pack(fill=tk.X, pady=(12, 0))

    def _build_audio_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Audio")
        audio_data = self.settings.setdefault("audio", {})
        self._field(
            tab,
            "audio",
            "sensevoice_model",
            "SenseVoice model",
            audio_data.get("sensevoice_model", "iic/SenseVoiceSmall"),
            False,
        )
        ttk.Label(
            tab,
            text=(
                "Audio transcription now uses local FunASR/SenseVoice realtime "
                "streaming only. Install FunASR and download/cache the model locally "
                "before running listening questions."
            ),
            wraplength=560,
        ).pack(fill=tk.X, pady=(12, 0))

    def _build_oracle_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Oracle")

        ttk.Label(
            tab,
            text=(
                "When the automation model encounters a complex problem "
                "(math olympiad, logic puzzles, competition problems), it will "
                "consult the Oracle model configured here."
            ),
            wraplength=560,
        ).pack(fill=tk.X, pady=(0, 8))

        oracle_data = self.settings.setdefault("oracle", {})

        self._oracle_enabled_var = tk.BooleanVar(
            value=bool(oracle_data.get("enabled", False))
        )
        ttk.Checkbutton(
            tab,
            text="Enable Oracle (consult reasoning model for complex problems)",
            variable=self._oracle_enabled_var,
        ).pack(anchor="w", pady=(0, 8))

        provider_row = ttk.Frame(tab)
        provider_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(provider_row, text="Provider", width=18).pack(side=tk.LEFT)
        self._oracle_provider_var = tk.StringVar(
            value=oracle_data.get("provider", "zhipu")
        )
        provider_cb = ttk.Combobox(
            provider_row,
            textvariable=self._oracle_provider_var,
            values=["zhipu", "deepseek", "openai", "anthropic", "custom"],
            state="readonly",
            width=20,
        )
        provider_cb.pack(side=tk.LEFT)
        provider_cb.bind("<<ComboboxSelected>>", self._on_oracle_provider_change)

        self._field(tab, "oracle", "api_key", "API Key",
                    oracle_data.get("api_key", ""), True)
        self._field(tab, "oracle", "api_base", "API Base",
                    oracle_data.get("api_base", "https://open.bigmodel.cn/api/paas/v4"), False)
        self._field(tab, "oracle", "model", "Model",
                    oracle_data.get("model", "glm-4.6v-flashx"), False)
        self._field(tab, "oracle", "timeout", "Timeout (s)",
                    str(oracle_data.get("timeout", 120)), False)

        ttk.Label(
            tab,
            text="Recommended: GLM vision (glm-4.6v-flashx) for screenshot-aware phone tasks.",
            wraplength=560,
        ).pack(fill=tk.X, pady=(10, 0))

    def _on_oracle_provider_change(self, event=None) -> None:
        provider = self._oracle_provider_var.get()
        defaults = {
            "zhipu": ("https://open.bigmodel.cn/api/paas/v4", "glm-4.6v-flashx"),
            "deepseek": ("https://api.deepseek.com/v1", "deepseek-reasoner"),
            "openai":   ("https://api.openai.com/v1",   "o3-mini"),
            "anthropic": ("",                            "claude-opus-4-6"),
            "custom":   ("",                             ""),
        }
        api_base, model = defaults.get(provider, ("", ""))
        if provider != "custom":
            if ("oracle", "api_base") in self.vars:
                self.vars[("oracle", "api_base")].set(api_base)
            if ("oracle", "model") in self.vars:
                self.vars[("oracle", "model")].set(model)

    def _field(
        self,
        parent,
        section: str,
        field: str,
        label: str,
        value: str,
        secret: bool,
    ) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, padx=8, pady=3)
        ttk.Label(row, text=label, width=18).pack(side=tk.LEFT)
        var = tk.StringVar(value=value or "")
        self.vars[(section, field)] = var
        entry = ttk.Entry(row, textvariable=var, show="*" if secret else "")
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _save(self) -> None:
        for (section, field), var in self.vars.items():
            if section == "adb":
                self.settings.setdefault("adb", {})[field] = var.get().strip()
            elif section == "oracle":
                self.settings.setdefault("oracle", {})[field] = var.get().strip()
            elif section == "audio":
                self.settings.setdefault("audio", {})[field] = var.get().strip()
            else:
                self.settings.setdefault("providers", {}).setdefault(section, {})[field] = (
                    var.get().strip()
                )
        # persist oracle checkbox and provider dropdown (not routed through self.vars)
        if hasattr(self, "_oracle_enabled_var"):
            self.settings.setdefault("oracle", {})["enabled"] = self._oracle_enabled_var.get()
        if hasattr(self, "_oracle_provider_var"):
            self.settings.setdefault("oracle", {})["provider"] = self._oracle_provider_var.get()
        try:
            save_settings(self.settings)
        except OSError as exc:
            messagebox.showerror("Settings", str(exc))
            return
        if self.on_save:
            self.on_save()
        self.destroy()
