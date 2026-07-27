"""Right panel: VLM provider, model, and prompt configuration."""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox, ttk

logger = logging.getLogger(__name__)


class VLMPanel(ttk.LabelFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, text="VLM")
        self._build_ui()
        self._load_defaults()

    def _build_ui(self) -> None:
        PX, PY = 10, 3

        # Provider & Model
        sec1 = ttk.LabelFrame(self, text="Provider & Model")
        sec1.pack(fill=tk.X, padx=PX, pady=(8, PY))

        prov_row = ttk.Frame(sec1)
        prov_row.pack(fill=tk.X, padx=8, pady=(6, 3))
        ttk.Label(prov_row, text="Provider", width=8).pack(side=tk.LEFT)
        self._provider_var = tk.StringVar(value="openai")
        self._provider_cb = ttk.Combobox(
            prov_row,
            textvariable=self._provider_var,
            values=["openai", "anthropic", "zhipu", "qwen_vl", "custom"],
            state="readonly",
        )
        self._provider_cb.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._provider_cb.bind("<<ComboboxSelected>>", self._on_provider_change)

        model_row = ttk.Frame(sec1)
        model_row.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Label(model_row, text="Model", width=8).pack(side=tk.LEFT)
        self._model_var = tk.StringVar()
        self._model_cb = ttk.Combobox(model_row, textvariable=self._model_var)
        self._model_cb.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Parameters
        sec2 = ttk.LabelFrame(self, text="Parameters")
        sec2.pack(fill=tk.X, padx=PX, pady=PY)

        temp_row = ttk.Frame(sec2)
        temp_row.pack(fill=tk.X, padx=8, pady=(6, 2))
        ttk.Label(temp_row, text="Temperature", width=12).pack(side=tk.LEFT)
        self._temp_label = ttk.Label(temp_row, text="0.20", width=5)
        self._temp_label.pack(side=tk.RIGHT)
        self._temp_var = tk.DoubleVar(value=0.2)
        self._temp_scale = ttk.Scale(
            sec2, from_=0.0, to=2.0, variable=self._temp_var,
            command=self._on_temp_change, orient="horizontal",
        )
        self._temp_scale.pack(fill=tk.X, padx=8, pady=(0, 4))

        tok_row = ttk.Frame(sec2)
        tok_row.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Label(tok_row, text="Max tokens", width=12).pack(side=tk.LEFT)
        self._tokens_var = tk.IntVar(value=2048)
        ttk.Spinbox(
            tok_row, from_=256, to=8192, increment=256,
            textvariable=self._tokens_var, width=8,
        ).pack(side=tk.LEFT)

        # Prompt
        sec3 = ttk.LabelFrame(self, text="Prompt")
        sec3.pack(fill=tk.BOTH, expand=True, padx=PX, pady=PY)

        tpl_row = ttk.Frame(sec3)
        tpl_row.pack(fill=tk.X, padx=8, pady=(6, 3))
        ttk.Label(tpl_row, text="Template", width=8).pack(side=tk.LEFT)
        self._tpl_var = tk.StringVar()
        self._tpl_cb = ttk.Combobox(tpl_row, textvariable=self._tpl_var, state="readonly")
        self._tpl_cb.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._tpl_cb.bind("<<ComboboxSelected>>", self._on_template_select)

        self._prompt_text = tk.Text(
            sec3, height=6, wrap="word", font=("Segoe UI", 9), relief="flat", bd=0,
        )
        self._prompt_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=(2, 4))

        save_row = ttk.Frame(sec3)
        save_row.pack(fill=tk.X, padx=8, pady=(0, 8))
        self._tpl_name_var = tk.StringVar()
        ttk.Entry(save_row, textvariable=self._tpl_name_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6)
        )
        ttk.Button(save_row, text="Save template", command=self._save_template).pack(side=tk.LEFT)

    def _load_defaults(self) -> None:
        try:
            import config

            self._temp_var.set(config.DEFAULT_TEMPERATURE)
            self._tokens_var.set(config.DEFAULT_MAX_TOKENS)
        except Exception:
            pass
        self._on_provider_change()
        self._reload_templates()

    def reload_settings(self) -> None:
        self._on_provider_change()

    def _on_provider_change(self, event=None) -> None:
        try:
            from settings_store import get_provider_settings
            from vlm.models import PROVIDER_DEFAULTS

            provider = self._provider_var.get()
            models = PROVIDER_DEFAULTS.get(provider, {}).get("models", [])
            configured = get_provider_settings(provider).get("model", "")
            default = configured or PROVIDER_DEFAULTS.get(provider, {}).get("default", "")
            self._model_cb["values"] = models
            self._model_cb.configure(state="normal")
            self._model_var.set(default)
        except Exception:
            logger.exception("Unable to load provider defaults")

    def _on_temp_change(self, _val=None) -> None:
        self._temp_label.configure(text=f"{self._temp_var.get():.2f}")

    def _reload_templates(self) -> None:
        try:
            from config import PROMPTS_FILE
            from vlm.prompt_manager import PromptManager

            pm = PromptManager(PROMPTS_FILE)
            names = pm.get_template_names()
            self._tpl_cb["values"] = names
            if names:
                self._tpl_var.set(names[0])
                self._prompt_text.delete("1.0", tk.END)
                self._prompt_text.insert("1.0", pm.get_template(names[0]))
        except Exception:
            logger.exception("Unable to load prompt templates")
            self._tpl_cb["values"] = ["custom"]
            self._tpl_var.set("custom")

    def _on_template_select(self, event=None) -> None:
        try:
            from config import PROMPTS_FILE
            from vlm.prompt_manager import PromptManager

            pm = PromptManager(PROMPTS_FILE)
            text = pm.get_template(self._tpl_var.get())
            self._prompt_text.delete("1.0", tk.END)
            self._prompt_text.insert("1.0", text)
        except Exception:
            logger.exception("Unable to select prompt template")

    def _save_template(self) -> None:
        name = self._tpl_name_var.get().strip()
        if not name:
            messagebox.showwarning("Save template", "Enter a template name first.")
            return
        content = self._prompt_text.get("1.0", tk.END).strip()
        try:
            from config import PROMPTS_FILE
            from vlm.prompt_manager import PromptManager

            pm = PromptManager(PROMPTS_FILE)
            pm.save_template(name, content)
            self._reload_templates()
            self._tpl_var.set(name)
            logger.info("Prompt template saved: %s", name)
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))

    def get_config(self):
        from settings_store import get_provider_settings
        from vlm.models import VLMConfig

        provider = self._provider_var.get()
        provider_settings = get_provider_settings(provider)
        return VLMConfig(
            provider=provider,
            model=self._model_var.get().strip() or provider_settings.get("model", ""),
            api_key=provider_settings.get("api_key", ""),
            api_base=provider_settings.get("api_base", ""),
            temperature=round(self._temp_var.get(), 2),
            max_tokens=self._tokens_var.get(),
        )

    def get_prompt(self) -> str:
        return self._prompt_text.get("1.0", tk.END).strip()
