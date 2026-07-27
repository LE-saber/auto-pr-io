"""Auto-click control panel."""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

from auto_click.modes.profiles import ADB_MODE_BACKENDS, MODE_PROFILES, backend_profile
from settings_store import get_adb_settings, get_audio_settings, get_oracle_settings, get_provider_settings, update_adb_device

logger = logging.getLogger(__name__)


class AutoClickPanel(ttk.LabelFrame):
    """Panel for configuring and running model-driven automation."""

    ADB_BACKENDS = {"openai_adb", "adb_vlm", "glm_adb", "deepseek_adb", *ADB_MODE_BACKENDS, "observe_adb", "autoglm_phone"}

    BACKEND_LABELS = {
        "openai":         "Windows - OpenAI Computer Use",
        "vlm_coords":     "Windows - Generic VLM coordinates",
        "openai_adb":     "Android ADB - OpenAI Computer Use",
        "adb_vlm":        "Android ADB - Generic VLM coordinates",
        "glm_adb":        "Android ADB - GLM Vision (glm-4.6v-flashx)",
        "deepseek_adb":   "Android ADB - DeepSeek Vision (deepseek-vl2)",
        "cida_work":      f"Android ADB - {MODE_PROFILES['cida_work'].label}",
        "observe_adb":    "Android ADB - Observe only / Notes",
        "autoglm_phone":  "Android ADB - AutoGLM-Phone",
    }

    def __init__(
        self,
        master,
        get_screenshot_fn: Optional[Callable[[], str]] = None,
        open_settings_fn: Optional[Callable[[], None]] = None,
        forbidden_rects_fn: Optional[Callable[[], list[dict]]] = None,
        adb_parent=None,
        show_backend_selector: bool = True,
        on_history_update: Optional[Callable[[], None]] = None,
        on_chat_message: Optional[Callable[[str, dict], None]] = None,
        **kwargs,
    ):
        super().__init__(master, text="Auto-click", **kwargs)
        self._get_screenshot = get_screenshot_fn
        self._open_settings = open_settings_fn
        self._forbidden_rects_fn = forbidden_rects_fn
        self._adb_parent = adb_parent
        self._show_backend_selector = show_backend_selector
        self._on_history_update = on_history_update
        self._on_chat_message = on_chat_message
        self._clicker = None
        self._phone_screen = None  # PhoneScreenPanel reference set after creation
        self._chat_messages: list[str] = []
        self._device_map: dict[str, str] = {}
        self._device_info_map: dict[str, object] = {}  # device_id → ADBDeviceInfo
        self._build_ui()
        self.reload_settings()
        self._load_panel_state()   # restore last session (overrides reload defaults)
        self._on_backend_change()  # refresh ADB visibility based on loaded backend
        self.after(500, self._auto_wifi_connect)

    def _build_ui(self) -> None:
        # ── Scrollable container ───────────────────────────────────────────
        self._canvas = tk.Canvas(self, highlightthickness=0)
        self._scrollbar = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._frame = ttk.Frame(self._canvas)
        self._frame_id = self._canvas.create_window((0, 0), window=self._frame, anchor="nw")
        self._frame.bind("<Configure>", self._on_frame_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        PX, PY = 10, 4  # standard outer padding

        # ── Section 1: Backend & Model ─────────────────────────────────────
        sec1 = ttk.LabelFrame(
            self._frame,
            text="Backend & Model" if self._show_backend_selector else "Model",
        )
        sec1.pack(fill=tk.X, padx=PX, pady=(8, PY))

        self._backend_var = tk.StringVar(value=self.BACKEND_LABELS["openai"])
        if self._show_backend_selector:
            backend_hdr = ttk.Frame(sec1)
            backend_hdr.pack(fill=tk.X, padx=8, pady=(6, 2))
            ttk.Label(backend_hdr, text="Automation backend").pack(side=tk.LEFT)
            if self._open_settings:
                ttk.Button(backend_hdr, text="Settings", command=self._open_settings).pack(side=tk.RIGHT)

            self._backend_cb = ttk.Combobox(
                sec1,
                textvariable=self._backend_var,
                values=list(self._visible_backend_labels().values()),
                state="readonly",
            )
            self._backend_cb.pack(fill=tk.X, padx=8, pady=(0, 6))
            self._backend_cb.bind("<<ComboboxSelected>>", self._on_backend_change)
        else:
            self._backend_cb = None

        model_row = ttk.Frame(sec1)
        model_row.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Label(model_row, text="Model", width=7).pack(side=tk.LEFT)
        self._model_var = tk.StringVar(value="gpt-5.5")
        ttk.Entry(model_row, textvariable=self._model_var).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ── Section 2: Android Device (ADB) ───────────────────────────────
        self._adb_frame = ttk.LabelFrame(self._adb_parent or self._frame, text="Android Device (ADB)")
        # packed/unpacked dynamically by _on_backend_change

        device_row = ttk.Frame(self._adb_frame)
        device_row.pack(fill=tk.X, padx=8, pady=(6, 2))
        self._device_var = tk.StringVar()
        self._device_cb = ttk.Combobox(device_row, textvariable=self._device_var, state="readonly")
        self._device_cb.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._device_cb.bind("<<ComboboxSelected>>", self._on_device_selected)
        ttk.Button(device_row, text="Refresh", command=self._refresh_devices).pack(
            side=tk.LEFT, padx=(6, 0)
        )

        self._adb_status_var = tk.StringVar(value="No device scan yet.")
        ttk.Label(
            self._adb_frame, textvariable=self._adb_status_var,
            wraplength=300, font=("Segoe UI", 8),
        ).pack(fill=tk.X, padx=8, pady=(2, 0))

        self._device_detail_var = tk.StringVar(value="")
        ttk.Label(
            self._adb_frame, textvariable=self._device_detail_var,
            wraplength=300, font=("Segoe UI", 8), foreground="#888888",
        ).pack(fill=tk.X, padx=8, pady=(0, 4))

        # ADB Keyboard
        ttk.Separator(self._adb_frame, orient="horizontal").pack(fill=tk.X, padx=8, pady=(2, 6))
        ttk.Label(self._adb_frame, text="ADB Keyboard", font=("Segoe UI", 9, "bold")).pack(
            anchor="w", padx=8
        )
        keyboard_row = ttk.Frame(self._adb_frame)
        keyboard_row.pack(fill=tk.X, padx=8, pady=(4, 2))
        ttk.Button(
            keyboard_row, text="Enable", command=self._enable_adb_keyboard
        ).pack(side=tk.LEFT)
        ttk.Button(
            keyboard_row, text="Check", command=self._check_adb_keyboard
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            keyboard_row, text="Open Audio Helper", command=self._open_audio_helper
        ).pack(side=tk.LEFT, padx=(6, 0))
        self._keyboard_status_var = tk.StringVar(value="Will auto-enable before typing.")
        ttk.Label(
            self._adb_frame, textvariable=self._keyboard_status_var,
            font=("Segoe UI", 8), wraplength=300,
        ).pack(fill=tk.X, padx=8, pady=(0, 4))

        # Wireless ADB
        ttk.Separator(self._adb_frame, orient="horizontal").pack(fill=tk.X, padx=8, pady=(2, 6))
        ttk.Label(self._adb_frame, text="Wireless ADB", font=("Segoe UI", 9, "bold")).pack(
            anchor="w", padx=8
        )

        wifi_row1 = ttk.Frame(self._adb_frame)
        wifi_row1.pack(fill=tk.X, padx=8, pady=(4, 2))
        ttk.Label(wifi_row1, text="IP:port", width=7).pack(side=tk.LEFT)
        self._wifi_addr_var = tk.StringVar()
        ttk.Entry(wifi_row1, textvariable=self._wifi_addr_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 6)
        )
        ttk.Button(wifi_row1, text="Connect", command=self._wifi_connect).pack(side=tk.LEFT)
        ttk.Button(wifi_row1, text="Disconnect", command=self._wifi_disconnect).pack(
            side=tk.LEFT, padx=(4, 0)
        )

        wifi_row2 = ttk.Frame(self._adb_frame)
        wifi_row2.pack(fill=tk.X, padx=8, pady=(0, 2))
        ttk.Label(wifi_row2, text="Pair port", width=7).pack(side=tk.LEFT)
        self._wifi_pair_port_var = tk.StringVar()
        ttk.Entry(wifi_row2, textvariable=self._wifi_pair_port_var, width=8).pack(
            side=tk.LEFT, padx=(4, 6)
        )
        ttk.Label(wifi_row2, text="Code").pack(side=tk.LEFT)
        self._wifi_pair_code_var = tk.StringVar()
        ttk.Entry(wifi_row2, textvariable=self._wifi_pair_code_var, width=8).pack(
            side=tk.LEFT, padx=(4, 6)
        )
        ttk.Button(wifi_row2, text="Pair", command=self._wifi_pair).pack(side=tk.LEFT)

        self._wifi_auto_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self._adb_frame, text="Auto-connect on startup", variable=self._wifi_auto_var
        ).pack(anchor="w", padx=8, pady=(2, 0))

        self._wifi_status_var = tk.StringVar(value="")
        ttk.Label(
            self._adb_frame, textvariable=self._wifi_status_var,
            font=("Segoe UI", 8), wraplength=300,
        ).pack(fill=tk.X, padx=8, pady=(2, 4))

        # Audio capture
        ttk.Separator(self._adb_frame, orient="horizontal").pack(fill=tk.X, padx=8, pady=(2, 6))
        ttk.Label(self._adb_frame, text="Audio Capture", font=("Segoe UI", 9, "bold")).pack(
            anchor="w", padx=8
        )

        audio_row = ttk.Frame(self._adb_frame)
        audio_row.pack(fill=tk.X, padx=8, pady=(4, 2))
        self._audio_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            audio_row, text="Enable (Android 13+)", variable=self._audio_var
        ).pack(side=tk.LEFT)
        self._continuous_audio_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            audio_row, text="Keep recording", variable=self._continuous_audio_var
        ).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Label(audio_row, text="Duration", font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(16, 4))
        self._audio_duration_var = tk.StringVar(value="5s")
        ttk.Combobox(
            audio_row, textvariable=self._audio_duration_var,
            values=["5s", "10s", "20s", "30s", "5min"], state="readonly", width=6,
        ).pack(side=tk.LEFT)

        whisper_row = ttk.Frame(self._adb_frame)
        whisper_row.pack(fill=tk.X, padx=8, pady=(0, 2))
        ttk.Label(whisper_row, text="Realtime ASR").pack(side=tk.LEFT)
        self._whisper_mode_var = tk.StringVar(value="sensevoice_streaming")
        ttk.Combobox(
            whisper_row, textvariable=self._whisper_mode_var,
            values=["sensevoice_streaming"], state="readonly", width=20,
        ).pack(side=tk.LEFT, padx=(6, 8))
        ttk.Label(
            whisper_row, text="local FunASR/SenseVoice streaming only",
            font=("Segoe UI", 8), foreground="#888888",
        ).pack(side=tk.LEFT)

        self._audio_status_var = tk.StringVar(value="")
        ttk.Label(
            self._adb_frame, textvariable=self._audio_status_var,
            font=("Segoe UI", 8), wraplength=300,
        ).pack(fill=tk.X, padx=8, pady=(2, 8))

        # ── Section 3: Task Description ────────────────────────────────────
        sec3 = ttk.LabelFrame(self._frame, text="Task Description")
        sec3.pack(fill=tk.X, padx=PX, pady=PY)

        self._task_text = tk.Text(
            sec3, height=5, wrap="word", font=("Segoe UI", 9), relief="flat", bd=0,
        )
        self._task_text.pack(fill=tk.X, padx=8, pady=(6, 4))
        self._task_text.insert("1.0", "Click the Submit button")

        ttk.Label(
            sec3,
            text="e.g. open Settings and turn on Wi-Fi; reply to the current message",
            font=("Segoe UI", 8), foreground="#888888", wraplength=300,
        ).pack(fill=tk.X, padx=8, pady=(0, 6))

        # ── Section 4: Options ─────────────────────────────────────────────
        sec4 = ttk.LabelFrame(self._frame, text="Options")
        sec4.pack(fill=tk.X, padx=PX, pady=PY)

        opt_row = ttk.Frame(sec4)
        opt_row.pack(fill=tk.X, padx=8, pady=(6, 4))
        ttk.Label(opt_row, text="Max steps").pack(side=tk.LEFT)
        self._steps_var = tk.IntVar(value=20)
        ttk.Spinbox(opt_row, from_=1, to=500, textvariable=self._steps_var, width=5).pack(
            side=tk.LEFT, padx=(6, 20)
        )
        self._confirm_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt_row, text="Log each action", variable=self._confirm_var).pack(
            side=tk.LEFT
        )

        # ── Section 5: Run Controls ────────────────────────────────────────
        ctrl_frame = ttk.Frame(self._frame)
        ctrl_frame.pack(fill=tk.X, padx=PX, pady=(8, 4))

        self._run_btn = tk.Button(
            ctrl_frame, text="  Start  ", command=self._start,
            bg="#2ea043", fg="white", activebackground="#3cb750", activeforeground="white",
            font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2",
            padx=14, pady=6,
        )
        self._run_btn.pack(side=tk.LEFT, padx=(0, 8))

        self._stop_btn = tk.Button(
            ctrl_frame, text="  Stop  ", command=self._stop,
            bg="#da3633", fg="white", activebackground="#e85250", activeforeground="white",
            font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2",
            padx=14, pady=6, state="disabled",
        )
        self._stop_btn.pack(side=tk.LEFT)

        ttk.Button(
            ctrl_frame, text="Reset", command=self._reset_panel,
        ).pack(side=tk.LEFT, padx=(12, 0))

        self._status_var = tk.StringVar(value="Ready")
        ttk.Label(
            ctrl_frame, textvariable=self._status_var, font=("Segoe UI", 9),
        ).pack(side=tk.LEFT, padx=(16, 0))

        # ── Section 6: Action Log ──────────────────────────────────────────
        log_lf = ttk.LabelFrame(self._frame, text="Action Log")
        log_lf.pack(fill=tk.BOTH, expand=True, padx=PX, pady=(4, 10))

        log_inner = ttk.Frame(log_lf)
        log_inner.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))

        log_sb = ttk.Scrollbar(log_inner, orient="vertical")
        self._log = tk.Text(
            log_inner, height=8, state="disabled",
            font=("Consolas", 8), bg="#0d1117", fg="#7ee787",
            relief="flat", yscrollcommand=log_sb.set,
        )
        log_sb.configure(command=self._log.yview)
        log_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def set_phone_screen_panel(self, panel) -> None:
        """Wire up the live phone screen panel (called from MainWindow after creation)."""
        self._phone_screen = panel

    def reload_settings(self) -> None:
        backend = self._selected_backend()
        self._model_var.set(self._default_model_for_backend(backend))
        if backend in self.ADB_BACKENDS:
            self._refresh_devices(silent=True)

    def _selected_backend(self) -> str:
        label = self._backend_var.get()
        return next(
            (key for key, value in self.BACKEND_LABELS.items() if value == label),
            "openai",
        )

    @classmethod
    def _visible_backend_labels(cls) -> dict[str, str]:
        return {key: value for key, value in cls.BACKEND_LABELS.items() if key != "observe_adb"}

    def set_backend(self, backend: str) -> None:
        """Select backend from the external mode selector."""
        if backend not in self.BACKEND_LABELS:
            return
        self._backend_var.set(self.BACKEND_LABELS[backend])
        if self._backend_cb is not None:
            self._backend_cb.set(self.BACKEND_LABELS[backend])
        self._on_backend_change()

    def get_backend(self) -> str:
        return self._selected_backend()

    def _on_backend_change(self, event=None) -> None:
        backend = self._selected_backend()
        self._model_var.set(self._default_model_for_backend(backend))
        profile = backend_profile(backend)
        if profile:
            if profile.force_audio:
                self._audio_var.set(True)
            if profile.asr_mode:
                self._whisper_mode_var.set(profile.asr_mode)
            if int(self._steps_var.get() or 0) <= 20:
                self._steps_var.set(profile.default_steps)
            if not self._task_text.get("1.0", tk.END).strip() or self._task_text.get("1.0", tk.END).strip() == "Click the Submit button":
                self._task_text.delete("1.0", tk.END)
                self._task_text.insert("1.0", profile.default_task)
        elif backend == "observe_adb":
            self._audio_var.set(True)
            self._continuous_audio_var.set(True)
            if int(self._steps_var.get() or 0) <= 20:
                self._steps_var.set(500)
            current_task = self._task_text.get("1.0", tk.END).strip()
            if not current_task or current_task == "Click the Submit button":
                self._task_text.delete("1.0", tk.END)
                self._task_text.insert(
                    "1.0",
                    "只观察和收听手机内容，不要控制手机。请实时整理网课/会议笔记，"
                    "提炼重点、待办和问题；如果屏幕或语音中出现问题，请给出回答。",
                )
        if backend in self.ADB_BACKENDS:
            self._adb_frame.pack(fill=tk.X, padx=8, pady=(4, 2))
            self._refresh_devices(silent=True)
        else:
            self._adb_frame.pack_forget()

    def _default_model_for_backend(self, backend: str) -> str:
        hardcoded = {
            "glm_adb":       "glm-4.6v-flashx",
            "deepseek_adb":  "deepseek-vl2",
            "observe_adb":   "qwen3-vl-plus",
            "autoglm_phone": "autoglm-phone",
        }
        profile = backend_profile(backend)
        if profile:
            return profile.main_model
        if backend in hardcoded:
            return hardcoded[backend]
        provider = self._settings_provider_for_backend(backend)
        configured = get_provider_settings(provider).get("model", "")
        defaults = {
            "openai":     "gpt-5.5",
            "openai_adb": "gpt-5.5",
            "adb_vlm":    "gpt-4o",
            "vlm_coords": "gpt-4o",
        }
        return configured or defaults.get(backend, "")

    def _settings_provider_for_backend(self, backend: str) -> str:
        if backend in {"openai", "openai_adb"}:
            return "openai"
        if backend in {"vlm_coords", "adb_vlm"}:
            return "vlm_coords"
        if backend == "glm_adb":
            return "zhipu"
        if backend == "observe_adb":
            return "qwen_vl"
        profile = backend_profile(backend)
        if profile:
            return profile.provider
        if backend == "deepseek_adb":
            return "deepseek_vision"
        return backend

    def _refresh_devices(self, silent: bool = False) -> None:
        try:
            from auto_click.adb import ADBController

            adb_settings = get_adb_settings()
            controller = ADBController(adb_path=adb_settings.get("path", "adb"))
            devices = controller.list_devices()
        except Exception as exc:
            self._device_map = {}
            self._device_cb["values"] = []
            self._device_var.set("")
            self._adb_status_var.set(f"ADB scan failed: {exc}")
            logger.exception("ADB device scan failed")
            if not silent:
                messagebox.showerror("ADB devices", str(exc))
            return

        labels = []
        self._device_map = {}
        self._device_info_map = {}
        for device in devices:
            label = device.display_name
            labels.append(label)
            self._device_map[label] = device.device_id
            self._device_info_map[device.device_id] = device
        self._device_cb["values"] = labels

        last_device = get_adb_settings().get("last_device_id", "")
        selected = ""
        for label, device_id in self._device_map.items():
            if device_id == last_device:
                selected = label
                break
        if not selected and labels:
            selected = labels[0]
        self._device_var.set(selected)
        self._update_device_detail()

        ready_count = sum(1 for device in devices if device.state == "device")
        unauth_count = sum(1 for device in devices if device.state == "unauthorized")
        if not devices:
            self._adb_status_var.set("No ADB devices found.")
        else:
            parts = [f"{len(devices)} device(s) found"]
            if ready_count:
                parts.append(f"{ready_count} ready")
            if unauth_count:
                parts.append(f"{unauth_count} unauthorized — enable USB debugging")
            self._adb_status_var.set(",  ".join(parts) + ".")
        logger.info("ADB scan: %s device(s), %s ready", len(devices), ready_count)

    def _on_device_selected(self, event=None) -> None:
        device_id = self._selected_device_id()
        if device_id:
            update_adb_device(device_id)
            self._update_device_detail()
            logger.info("ADB device selected: %s", device_id)

    def _update_device_detail(self) -> None:
        """Refresh the small detail label below the device dropdown."""
        device_id = self._selected_device_id()
        if not device_id:
            self._device_detail_var.set("")
            return
        info = self._device_info_map.get(device_id)
        if info is None:
            self._device_detail_var.set(f"ID: {device_id}")
            return
        if info.state != "device":
            self._device_detail_var.set(f"Status: {info.state}  —  cannot be used until ready")
            return
        parts = []
        if info.manufacturer:
            parts.append(f"Mfr: {info.manufacturer}")
        if info.model:
            parts.append(f"Model: {info.model}")
        if info.android_version:
            parts.append(f"Android {info.android_version}")
        parts.append(f"ID: {device_id}")
        self._device_detail_var.set("  |  ".join(parts))

    def _selected_device_id(self) -> str:
        return self._device_map.get(self._device_var.get(), "")

    def _make_adb_controller(self):
        from auto_click.adb import ADBController

        return ADBController(adb_path=self._adb_exe(), device_id=self._selected_device_id())

    def _enable_adb_keyboard(self) -> None:
        device_id = self._selected_device_id()
        if not device_id:
            messagebox.showwarning("ADB Keyboard", "Select a ready Android device first.")
            return
        self._keyboard_status_var.set("Enabling ADB Keyboard...")
        self.update_idletasks()
        try:
            controller = self._make_adb_controller()
            controller.ensure_ready()
            ime_id = controller.ensure_adb_keyboard()
            if ime_id:
                self._keyboard_status_var.set(f"Enabled: {ime_id}")
                self._log_line(f"ADB Keyboard enabled: {ime_id}")
            else:
                self._keyboard_status_var.set(
                    "ADB Keyboard not found. Install the Auto-GLMPhone/ADB keyboard app first."
                )
        except Exception as exc:
            logger.exception("ADB Keyboard enable failed")
            self._keyboard_status_var.set(f"Enable failed: {exc}")
            messagebox.showerror("ADB Keyboard", str(exc))

    def _check_adb_keyboard(self) -> None:
        device_id = self._selected_device_id()
        if not device_id:
            messagebox.showwarning("ADB Keyboard", "Select a ready Android device first.")
            return
        try:
            controller = self._make_adb_controller()
            controller.ensure_ready()
            installed = controller.list_imes()
            current = controller.current_ime()
            ime_id = controller.find_adb_keyboard_ime()
            if ime_id:
                self._keyboard_status_var.set(f"Installed: {ime_id} | Current: {current or '-'}")
            else:
                self._keyboard_status_var.set(
                    f"Not found. Installed IMEs: {', '.join(installed[:3]) or '-'}"
                )
            logger.info("ADB Keyboard check: found=%s current=%s installed=%s", ime_id, current, installed)
        except Exception as exc:
            logger.exception("ADB Keyboard check failed")
            self._keyboard_status_var.set(f"Check failed: {exc}")
            messagebox.showerror("ADB Keyboard", str(exc))

    def _open_audio_helper(self) -> None:
        device_id = self._selected_device_id()
        if not device_id:
            messagebox.showwarning("Audio Helper", "Select a ready Android device first.")
            return
        try:
            controller = self._make_adb_controller()
            controller.ensure_ready()
            result = controller._shell([
                "am",
                "start",
                "-n",
                "com.autopr.keyboardaudio/.MainActivity",
            ])
            self._keyboard_status_var.set("Audio Helper UI opened on Android device.")
            logger.info("Audio Helper opened: %s", result.stdout.strip())
        except Exception as exc:
            logger.exception("Open Audio Helper failed")
            self._keyboard_status_var.set(f"Open Audio Helper failed: {exc}")
            messagebox.showerror(
                "Audio Helper",
                "Install AutoPr Keyboard Audio APK first, then retry.\n\n" + str(exc),
            )

    def _parse_audio_duration(self) -> int:
        val = self._audio_duration_var.get()
        mapping = {"3s": 3, "5s": 5, "10s": 10, "20s": 20, "30s": 30, "5min": 300}
        return max(5, mapping.get(val, 5))

    def _adb_exe(self) -> str:
        return get_adb_settings().get("path", "adb") or "adb"

    def _wifi_pair(self) -> None:
        import subprocess
        pair_port = self._wifi_pair_port_var.get().strip()
        code = self._wifi_pair_code_var.get().strip()
        ip = self._wifi_addr_var.get().strip().split(":")[0]
        if not ip or not pair_port or not code:
            self._wifi_status_var.set("Fill IP:port, pair port, and pair code.")
            return
        addr = f"{ip}:{pair_port}"
        self._wifi_status_var.set(f"Pairing {addr} ...")
        self.update_idletasks()
        try:
            r = subprocess.run(
                [self._adb_exe(), "pair", addr, code],
                capture_output=True, text=True, timeout=15
            )
            out = (r.stdout + r.stderr).strip()
            if "Successfully paired" in out:
                self._wifi_status_var.set("Pairing succeeded. Click Connect.")
            else:
                self._wifi_status_var.set(f"Pairing failed: {out[:80]}")
        except Exception as e:
            self._wifi_status_var.set(f"Pairing error: {e}")

    def _wifi_connect(self) -> None:
        import subprocess
        addr = self._wifi_addr_var.get().strip()
        if not addr:
            self._wifi_status_var.set("Fill IP:port, for example 192.168.1.x:43995.")
            return
        self._wifi_status_var.set(f"Connecting {addr} ...")
        self.update_idletasks()
        try:
            r = subprocess.run(
                [self._adb_exe(), "connect", addr],
                capture_output=True, text=True, timeout=10
            )
            out = (r.stdout + r.stderr).strip()
            if "connected" in out.lower():
                self._wifi_status_var.set(f"Connected: {addr}")
                if self._wifi_auto_var.get():
                    self._save_wifi_settings(addr)
                self._refresh_devices(silent=True)
            else:
                self._wifi_status_var.set(f"Connect failed: {out[:80]}")
        except Exception as e:
            self._wifi_status_var.set(f"Connect error: {e}")

    def _wifi_disconnect(self) -> None:
        import subprocess
        addr = self._wifi_addr_var.get().strip()
        if not addr:
            return
        try:
            subprocess.run([self._adb_exe(), "disconnect", addr],
                           capture_output=True, timeout=5)
            self._wifi_status_var.set(f"Disconnected: {addr}")
            self._refresh_devices(silent=True)
        except Exception as e:
            self._wifi_status_var.set(f"Disconnect error: {e}")

    def _save_wifi_settings(self, addr: str) -> None:
        try:
            from settings_store import load_settings, save_settings
            s = load_settings()
            s.setdefault("wifi_adb", {})["last_addr"] = addr
            s["wifi_adb"]["auto_connect"] = True
            save_settings(s)
        except Exception:
            pass

    def _auto_wifi_connect(self) -> None:
        try:
            from settings_store import load_settings
            s = load_settings()
            wa = s.get("wifi_adb", {})
            if wa.get("auto_connect") and wa.get("last_addr"):
                addr = wa["last_addr"]
                self._wifi_addr_var.set(addr)
                self._wifi_auto_var.set(True)
                self._wifi_connect()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Panel state persistence
    # ------------------------------------------------------------------

    _DEFAULT_PROFILE = MODE_PROFILES["cida_work"]

    _PANEL_DEFAULTS = {
        "backend":        _DEFAULT_PROFILE.backend,
        "model":          "",
        "task":           _DEFAULT_PROFILE.default_task,
        "steps":          _DEFAULT_PROFILE.default_steps,
        "confirm":        True,
        "audio_enabled":  _DEFAULT_PROFILE.force_audio,
        "continuous_audio": True,
        "audio_duration": "5s",
        "whisper_mode":   _DEFAULT_PROFILE.asr_mode,
        "wifi_addr":      "",
        "wifi_auto":      False,
    }

    def _load_panel_state(self) -> None:
        """Restore panel fields from the last saved session."""
        try:
            from settings_store import load_settings
            state = load_settings().get("panel_state", {})
            if not state:
                return
            backend = state.get("backend", "")
            if backend in self.BACKEND_LABELS:
                self._backend_var.set(self.BACKEND_LABELS[backend])
            if state.get("model"):
                self._model_var.set(state["model"])
            task = state.get("task", "")
            if task:
                self._task_text.delete("1.0", tk.END)
                self._task_text.insert("1.0", task)
            if "steps" in state:
                self._steps_var.set(int(state["steps"]))
            if "confirm" in state:
                self._confirm_var.set(bool(state["confirm"]))
            if "audio_enabled" in state:
                self._audio_var.set(bool(state["audio_enabled"]))
            if "continuous_audio" in state:
                self._continuous_audio_var.set(bool(state["continuous_audio"]))
            if state.get("audio_duration"):
                self._audio_duration_var.set(state["audio_duration"])
            if state.get("whisper_mode"):
                self._whisper_mode_var.set("sensevoice_streaming")
            if state.get("wifi_addr"):
                self._wifi_addr_var.set(state["wifi_addr"])
            if "wifi_auto" in state:
                self._wifi_auto_var.set(bool(state["wifi_auto"]))
        except Exception:
            logger.debug("Failed to load panel state", exc_info=True)

    def save_panel_state(self) -> None:
        """Persist current panel values to settings.json (called on window close)."""
        try:
            from settings_store import load_settings, save_settings
            settings = load_settings()
            settings["panel_state"] = {
                "backend":        self._selected_backend(),
                "model":          self._model_var.get(),
                "task":           self._task_text.get("1.0", tk.END).strip(),
                "steps":          self._steps_var.get(),
                "confirm":        self._confirm_var.get(),
                "audio_enabled":  self._audio_var.get(),
                "continuous_audio": self._continuous_audio_var.get(),
                "audio_duration": self._audio_duration_var.get(),
                "whisper_mode":   self._whisper_mode_var.get(),
                "wifi_addr":      self._wifi_addr_var.get(),
                "wifi_auto":      self._wifi_auto_var.get(),
            }
            save_settings(settings)
            logger.debug("Panel state saved")
        except Exception:
            logger.debug("Failed to save panel state", exc_info=True)

    def _reset_panel(self) -> None:
        """Reset all fields to defaults and clear the saved panel state."""
        d = self._PANEL_DEFAULTS
        self._backend_var.set(self.BACKEND_LABELS[d["backend"]])
        self._model_var.set(self._default_model_for_backend(d["backend"]))
        self._task_text.delete("1.0", tk.END)
        self._task_text.insert("1.0", d["task"])
        self._steps_var.set(d["steps"])
        self._confirm_var.set(d["confirm"])
        self._audio_var.set(d["audio_enabled"])
        self._continuous_audio_var.set(d["continuous_audio"])
        self._audio_duration_var.set(d["audio_duration"])
        self._whisper_mode_var.set(d["whisper_mode"])
        self._wifi_addr_var.set(d["wifi_addr"])
        self._wifi_auto_var.set(d["wifi_auto"])
        self._wifi_status_var.set("")
        self._audio_status_var.set("")
        self._on_backend_change()
        try:
            from settings_store import load_settings, save_settings
            s = load_settings()
            s.pop("panel_state", None)
            save_settings(s)
        except Exception:
            pass

    def _on_frame_configure(self, event=None) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event=None) -> None:
        self._canvas.itemconfig(self._frame_id, width=event.width)

    def _on_mousewheel(self, event) -> None:
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _start(self) -> None:
        task = self._task_text.get("1.0", tk.END).strip()
        if not task:
            messagebox.showwarning("Auto-click", "Please enter a task.")
            return

        backend = self._selected_backend()
        provider = self._settings_provider_for_backend(backend)
        provider_settings = get_provider_settings(provider)
        api_key = provider_settings.get("api_key", "")
        api_base = provider_settings.get("api_base", "")

        if not api_key and backend not in {"vlm_coords", "adb_vlm"}:
            self._show_missing_setting(f"{provider} API key")
            return
        if backend in {"openai", "openai_adb"} and not api_key:
            self._show_missing_setting("OpenAI API key")
            return
        if backend in {"vlm_coords", "adb_vlm", "glm_adb", "deepseek_adb", "cida_work", "observe_adb"} and not api_base:
            self._show_missing_setting(f"{provider} API Base URL")
            return

        device_id = ""
        if backend in self.ADB_BACKENDS:
            device_id = self._selected_device_id()
            if not device_id:
                messagebox.showwarning(
                    "ADB device",
                    "Refresh devices and select a ready Android device first.",
                )
                return
            update_adb_device(device_id)

        screenshot_b64 = None
        if backend in {"openai", "vlm_coords"} and self._get_screenshot:
            try:
                screenshot_b64 = self._get_screenshot()
            except Exception as exc:
                logger.warning("Unable to capture initial screenshot: %s", exc)

        try:
            from auto_click.clicker import AutoClicker

            self._chat_messages.clear()
            adb_settings = get_adb_settings()
            audio_settings = get_audio_settings()
            profile = backend_profile(backend)
            whisper_mode = "sensevoice_streaming"
            audio_enabled = True if profile and profile.force_audio else self._audio_var.get()
            local_asr_model = audio_settings.get(
                "sensevoice_model", profile.asr_model if profile else "iic/SenseVoiceSmall"
            )
            self._clicker = AutoClicker(
                backend=backend,
                api_key=api_key or "EMPTY",
                api_base=api_base,
                model=self._model_var.get().strip(),
                adb_path=adb_settings.get("path", "adb"),
                device_id=device_id,
                audio_enabled=audio_enabled,
                continuous_audio=bool(audio_enabled and self._continuous_audio_var.get()),
                whisper_mode=whisper_mode,
                whisper_api_key="",
                whisper_api_base="",
                whisper_api_model="",
                local_whisper_model=local_asr_model,
                audio_duration_s=self._parse_audio_duration(),
                on_audio_status=self._on_audio_status,
                forbidden_rects=(
                    self._forbidden_rects_fn() if self._forbidden_rects_fn else []
                ),
                max_steps=self._steps_var.get(),
                confirm_before_execute=self._confirm_var.get(),
                on_action=self._on_action,
                on_complete=self._on_complete,
                oracle_settings=get_oracle_settings(),
            )
            logger.info("Starting automation backend=%s device=%s", backend, device_id or "desktop")
            if self._phone_screen is not None and backend in self.ADB_BACKENDS:
                self._phone_screen.start_run()
            self._clicker.run_task(task, screenshot_b64=screenshot_b64)
        except Exception as exc:
            logger.exception("Unable to start automation")
            messagebox.showerror("Auto-click", str(exc))
            return

        # Auto-start live preview for ADB backends
        if self._phone_screen is not None and backend in self.ADB_BACKENDS:
            adb_settings = get_adb_settings()
            self._phone_screen.start(
                adb_path=adb_settings.get("path", "adb"),
                device_id=device_id,
            )

        self._set_running(True)
        self._set_status("Running")

    def _show_missing_setting(self, name: str) -> None:
        messagebox.showwarning(
            "Missing setting",
            f"Open Settings and configure {name} before starting this backend.",
        )

    def _stop(self) -> None:
        if self._clicker:
            self._clicker.stop()
        self._set_running(False)
        self._set_status("Stopped")
        logger.info("Automation stopped by user")

    def _on_audio_status(self, msg: str) -> None:
        self.after(0, lambda: self._audio_status_var.set(msg))

    def _on_action(self, action: dict, step: int) -> None:
        self.after(0, lambda: self._log_action(action, step))

    def _on_complete(self, success: bool, message: str) -> None:
        self.after(0, lambda: self._handle_complete(success, message))

    def _handle_complete(self, success: bool, message: str) -> None:
        self._set_running(False)
        self._set_status(("Done: " if success else "Error: ") + message[:120])
        self._log_line(f"=== {'done' if success else 'error'}: {message} ===")
        self._save_task_history(success, message)
        if success:
            logger.info("Automation complete: %s", message)
        else:
            logger.error("Automation failed: %s", message)

    def _save_task_history(self, success: bool, message: str) -> None:
        try:
            from auto_click.history import append_task_history

            append_task_history(
                {
                    "success": success,
                    "message": message,
                    "backend": self._selected_backend(),
                    "model": self._model_var.get().strip(),
                    "task": self._task_text.get("1.0", tk.END).strip(),
                    "chat_messages": list(self._chat_messages),
                    "screenshots": (
                        self._phone_screen.get_recent_screenshots()
                        if self._phone_screen is not None and hasattr(self._phone_screen, "get_recent_screenshots")
                        else []
                    ),
                }
            )
            if self._on_history_update:
                self._on_history_update()
        except Exception:
            logger.debug("Failed to save task history", exc_info=True)

    def _set_running(self, running: bool) -> None:
        self._run_btn.configure(state="disabled" if running else "normal")
        self._stop_btn.configure(state="normal" if running else "disabled")

    def _set_status(self, msg: str) -> None:
        self._status_var.set(msg)

    def _log_action(self, action: dict, step: int) -> None:
        # Forward click actions to the live phone screen for overlay
        if self._phone_screen is not None:
            self._phone_screen.mark_action(action)

        action_type = action.get("type", "?")
        detail = ""
        if action_type in {"click", "double_click", "move"}:
            detail = f"({action.get('x')},{action.get('y')})"
        elif action_type == "type":
            detail = repr(action.get("text", ""))[:60]
        elif action_type in {"enable_keyboard", "enable_adb_keyboard"}:
            detail = "ADB Keyboard"
        elif action_type in {"key", "keypress"}:
            detail = "+".join(action.get("keys", [])) or str(action.get("key", ""))
        elif action_type == "ask_oracle":
            detail = repr(action.get("question", ""))[:50] + " → " + repr(action.get("answer_preview", ""))[:40]
        elif action_type in {"listen_audio", "analyze_audio", "transcribe_audio", "listen"}:
            detail = f"{action.get('duration', action.get('seconds', ''))}s {action.get('question', '')}"[:80]
        elif action_type == "audio_transcript":
            detail = f"{action.get('duration', '')}s {action.get('text', '')}"[:80]
        elif action_type == "observation_note":
            text = str(action.get("text", "")).strip()
            if text:
                self._chat_messages.append(text)
            if self._on_chat_message:
                self._on_chat_message(text, action)
            self._log_line(f"[{step:02d}] observation_note")
            self._log_line(text)
            return
        elif action_type == "blocked_click":
            detail = action.get("reason", "")[:80]
        elif action_type == "scroll":
            detail = f"{action.get('direction', '')} {action.get('amount', '')}"
        elif action_type == "oracle_answer":
            answer = action.get("answer", "")
            detail = f"Q{action.get('question_step', step)} → {answer[:60]}"
        elif action_type == "phone_task":
            detail = action.get("task", "")[:60]
        elif action_type == "phone_step":
            detail = action.get("result", "")[:60]
        self._log_line(f"[{step:02d}] {action_type} {detail}")

    def _log_line(self, text: str) -> None:
        self._log.configure(state="normal")
        self._log.insert(tk.END, text + "\n")
        self._log.see(tk.END)
        self._log.configure(state="disabled")
