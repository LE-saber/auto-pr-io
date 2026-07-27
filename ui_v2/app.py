"""Application shell for the completely redesigned auto-pr-io GUI."""
from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional

from PIL import Image

import config
from auto_click.modes.profiles import backend_profile
from settings_store import get_adb_settings, get_ui_settings, load_settings, save_settings, update_adb_device, update_ui_settings
from ui_v2.backend import BackendBridge, RunRequest, backend_options, default_model_for_backend
from ui_v2.desktop import RegionPicker, WindowPicker
from ui_v2.i18n import LANGUAGES, Translator
from ui_v2.screen import ScreenSurface
from ui_v2.settings import SettingsWindow
from ui_v2.theme import COLORS, MONO_FONT, UI_FONT, apply_theme, text_widget_options
from ui_v2.views import ActivityView, ChatView, HistoryView, LogsView, SkillsView, UILogHandler, ZoneView

logger = logging.getLogger(__name__)


class VerticalScrolledFrame(ttk.Frame):
    """A restrained scrolling surface for the dense run configuration pane."""

    def __init__(self, master, width: int = 320) -> None:
        super().__init__(master, style="App.TFrame", width=width)
        self.canvas = tk.Canvas(
            self,
            width=width,
            background=COLORS["bg"],
            highlightthickness=0,
            borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.interior = ttk.Frame(self.canvas, style="App.TFrame", padding=14)
        self._window = self.canvas.create_window((0, 0), window=self.interior, anchor="nw")
        self.interior.bind("<Configure>", self._update_scroll_region)
        self.canvas.bind("<Configure>", self._resize_interior)

    def _update_scroll_region(self, _event=None) -> None:
        bounds = self.canvas.bbox("all")
        if bounds:
            self.canvas.configure(scrollregion=bounds)

    def _resize_interior(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._window, width=max(1, event.width))


class MainWindow:
    """New application shell. No legacy ``ui`` widgets are imported or reused."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        ui_settings = get_ui_settings()
        self.language = ui_settings.get("language", "zh-CN")
        self.font_size = max(9, min(16, int(ui_settings.get("font_size", 10) or 10)))
        self.translator = Translator(self.language)
        self.t = self.translator
        apply_theme(root, self.font_size)

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.log_handler = self._install_log_handler()
        self.bridge = BackendBridge(self._emit, lambda: self.screen.recent_screenshots() if hasattr(self, "screen") else [])
        self.devices: dict[str, object] = {}
        self.device_label_to_id: dict[str, str] = {}
        self.backend_label_to_id: dict[str, str] = {}
        self.views: dict[str, ttk.Frame] = {}
        self.nav_buttons: dict[str, ttk.Button] = {}
        self.current_view = "workspace"
        self.running = False
        self.desktop_capture_spec: dict = {"mode": "fullscreen", "monitor": 1}
        self._desktop_window_hidden = False
        self._settings_window: Optional[SettingsWindow] = None

        state = load_settings().get("panel_state", {})
        saved_backend = str(state.get("backend", "cida_work"))
        self.target = "android" if saved_backend in {*backend_options("android", "build"), "observe_adb"} else "desktop"
        self.work_mode = "chat" if saved_backend == "observe_adb" else "build"
        self.saved_backend = saved_backend

        self.root.title(config.APP_TITLE)
        self.root.geometry(f"{max(1180, config.WINDOW_WIDTH)}x{max(740, config.WINDOW_HEIGHT)}")
        self.root.minsize(1120, 700)
        self._build()
        self._bind_shortcuts()
        self._set_target(self.target, initial=True)
        self._set_work_mode(self.work_mode, initial=True)
        self._load_panel_state(state)
        self._apply_backend_profile(self._selected_backend())
        self._show_view(str(ui_settings.get("last_view", "workspace")))
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(100, self._drain_events)
        if self.target == "android":
            self.root.after(250, self.refresh_devices)

    def _install_log_handler(self) -> UILogHandler:
        handler = UILogHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logging.getLogger().addHandler(handler)
        return handler

    def _build(self) -> None:
        shell = ttk.Frame(self.root, style="App.TFrame")
        shell.pack(fill=tk.BOTH, expand=True)
        self._build_header(shell)
        self._build_statusbar(shell)
        body = ttk.Frame(shell, style="App.TFrame")
        body.pack(fill=tk.BOTH, expand=True)
        self._build_navigation(body)
        self.stage = ttk.Frame(body, style="App.TFrame")
        self.stage.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.stage.rowconfigure(0, weight=1)
        self.stage.columnconfigure(0, weight=1)

        self.views["workspace"] = self._build_workspace(self.stage)
        self.history_view = HistoryView(self.stage, self.t, self.font_size)
        self.views["history"] = self.history_view
        self.skills_view = SkillsView(self.stage, self.t, self.font_size)
        self.views["skills"] = self.skills_view
        self.logs_view = LogsView(self.stage, self.t, self.log_handler, self.font_size)
        self.views["logs"] = self.logs_view
        for view in self.views.values():
            view.grid(row=0, column=0, sticky="nsew")

    def _build_header(self, parent) -> None:
        header = ttk.Frame(parent, style="Header.TFrame", padding=(16, 10))
        header.pack(fill=tk.X)
        brand = ttk.Frame(header, style="Header.TFrame")
        brand.pack(side=tk.LEFT)
        self.brand_label = ttk.Label(brand, text=self.t("app_name"), style="Heading.TLabel")
        self.brand_label.pack(side=tk.LEFT)
        self.tagline_label = ttk.Label(brand, text=self.t("app_tagline"), style="Muted.TLabel")
        self.tagline_label.pack(side=tk.LEFT, padx=(12, 0))

        self.global_status_var = tk.StringVar(value=self.t("ready"))
        self.global_status = ttk.Label(header, textvariable=self.global_status_var, style="Success.TLabel")
        self.global_status.pack(side=tk.LEFT, padx=(28, 0))
        self.progress = ttk.Progressbar(header, mode="indeterminate", length=90)
        self.progress.pack(side=tk.LEFT, padx=(10, 0))

        self.settings_button = ttk.Button(header, text=self.t("settings"), command=self._open_settings)
        self.settings_button.pack(side=tk.RIGHT)
        self.font_var = tk.IntVar(value=self.font_size)
        self.font_spin = ttk.Spinbox(header, from_=9, to=16, width=4, textvariable=self.font_var, command=self._font_changed)
        self.font_spin.pack(side=tk.RIGHT, padx=(8, 14))
        self.font_label = ttk.Label(header, text=self.t("font_size"), style="Muted.TLabel")
        self.font_label.pack(side=tk.RIGHT)
        self.language_var = tk.StringVar(value=LANGUAGES.get(self.language, LANGUAGES["en"]))
        self.language_combo = ttk.Combobox(header, textvariable=self.language_var, values=list(LANGUAGES.values()), state="readonly", width=10)
        self.language_combo.pack(side=tk.RIGHT, padx=(8, 14))
        self.language_combo.bind("<<ComboboxSelected>>", self._language_changed)
        self.language_label = ttk.Label(header, text=self.t("language"), style="Muted.TLabel")
        self.language_label.pack(side=tk.RIGHT)

    def _build_navigation(self, parent) -> None:
        nav = ttk.Frame(parent, style="Nav.TFrame", width=160)
        nav.pack(side=tk.LEFT, fill=tk.Y)
        nav.pack_propagate(False)
        for index, key in enumerate(("workspace", "history", "skills", "logs")):
            button = ttk.Button(nav, text=self.t(key), style="Nav.TButton", command=lambda name=key: self._show_view(name))
            button.pack(fill=tk.X, padx=8, pady=((12 if index == 0 else 2), 2))
            self.nav_buttons[key] = button
        self.shortcut_label = ttk.Label(nav, text=self.t("nav_shortcut"), style="NavMuted.TLabel", wraplength=132, justify="left")
        self.shortcut_label.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=12)

    def _build_workspace(self, parent) -> ttk.Frame:
        view = ttk.Frame(parent, style="App.TFrame")
        toolbar = ttk.Frame(view, style="Header.TFrame", padding=(14, 10))
        toolbar.pack(fill=tk.X)

        self.target_label = ttk.Label(toolbar, text=self.t("target"), style="Muted.TLabel")
        self.target_label.pack(side=tk.LEFT)
        self.windows_button = ttk.Button(toolbar, text=self.t("windows"), style="Segment.TButton", command=lambda: self._set_target("desktop"))
        self.windows_button.pack(side=tk.LEFT, padx=(8, 0))
        self.android_button = ttk.Button(toolbar, text=self.t("android"), style="Segment.TButton", command=lambda: self._set_target("android"))
        self.android_button.pack(side=tk.LEFT, padx=(4, 18))
        self.mode_label = ttk.Label(toolbar, text=self.t("work_mode"), style="Muted.TLabel")
        self.mode_label.pack(side=tk.LEFT)
        self.build_button = ttk.Button(toolbar, text=self.t("build"), style="Segment.TButton", command=lambda: self._set_work_mode("build"))
        self.build_button.pack(side=tk.LEFT, padx=(8, 0))
        self.chat_button = ttk.Button(toolbar, text=self.t("chat"), style="Segment.TButton", command=lambda: self._set_work_mode("chat"))
        self.chat_button.pack(side=tk.LEFT, padx=(4, 0))
        self.mode_hint_var = tk.StringVar()
        self.mode_hint = ttk.Label(toolbar, textvariable=self.mode_hint_var, style="Muted.TLabel")
        self.mode_hint.pack(side=tk.RIGHT)

        pane = ttk.PanedWindow(view, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True)
        control_surface = VerticalScrolledFrame(pane, width=320)
        center = ttk.Frame(pane, style="App.TFrame", width=560)
        inspector = ttk.Frame(pane, style="Inspector.TFrame", width=310)
        pane.add(control_surface, weight=0)
        pane.add(center, weight=1)
        pane.add(inspector, weight=0)
        self.workspace_pane = pane
        self._build_controls(control_surface.interior)
        self.screen = ScreenSurface(center, self.t, self._zone_added)
        self.screen.pack(fill=tk.BOTH, expand=True)
        self._build_inspector(inspector)
        self.root.after_idle(self._position_workspace_panes)
        return view

    def _position_workspace_panes(self) -> None:
        width = self.workspace_pane.winfo_width()
        if width < 760:
            return
        left = max(280, min(330, int(width * 0.26)))
        right = max(285, min(340, int(width * 0.27)))
        try:
            self.workspace_pane.sashpos(0, left)
            self.workspace_pane.sashpos(1, max(left + 280, width - right))
        except tk.TclError:
            logger.debug("Unable to set initial workspace sash positions", exc_info=True)

    def _section(self, parent, key: str) -> ttk.Label:
        ttk.Separator(parent).pack(fill=tk.X, pady=(14, 12))
        label = ttk.Label(parent, text=self.t(key), style="Heading.TLabel")
        label.pack(anchor="w", pady=(0, 8))
        return label

    def _build_controls(self, parent) -> None:
        self.connection_title = ttk.Label(parent, text=self.t("connection"), style="Heading.TLabel")
        self.connection_title.pack(anchor="w", pady=(0, 8))

        self.android_connection = ttk.Frame(parent, style="App.TFrame")
        self.device_label = ttk.Label(self.android_connection, text=self.t("device"), style="Muted.TLabel")
        self.device_label.pack(anchor="w")
        device_row = ttk.Frame(self.android_connection, style="App.TFrame")
        device_row.pack(fill=tk.X, pady=(4, 4))
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(device_row, textvariable=self.device_var, state="readonly")
        self.device_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.device_combo.bind("<<ComboboxSelected>>", self._device_selected)
        self.refresh_button = ttk.Button(device_row, text=self.t("refresh"), style="Compact.TButton", command=self.refresh_devices)
        self.refresh_button.pack(side=tk.LEFT, padx=(6, 0))
        self.device_detail_var = tk.StringVar(value=self.t("no_devices"))
        ttk.Label(self.android_connection, textvariable=self.device_detail_var, style="Muted.TLabel", wraplength=320).pack(anchor="w", fill=tk.X)
        tools = ttk.Frame(self.android_connection, style="App.TFrame")
        tools.pack(fill=tk.X, pady=(8, 0))
        self.keyboard_button = ttk.Button(tools, text=self.t("enable_keyboard"), style="Compact.TButton", command=self._enable_keyboard)
        self.keyboard_button.pack(side=tk.LEFT)
        self.audio_helper_button = ttk.Button(tools, text=self.t("audio_helper"), style="Compact.TButton", command=self._open_audio_helper)
        self.audio_helper_button.pack(side=tk.LEFT, padx=(6, 0))

        self.desktop_connection = ttk.Frame(parent, style="App.TFrame")
        capture_row = ttk.Frame(self.desktop_connection, style="App.TFrame")
        capture_row.pack(fill=tk.X)
        self.fullscreen_button = ttk.Button(capture_row, text=self.t("fullscreen"), style="Compact.TButton", command=self._capture_fullscreen)
        self.fullscreen_button.pack(side=tk.LEFT)
        self.region_button = ttk.Button(capture_row, text=self.t("region"), style="Compact.TButton", command=self._capture_region)
        self.region_button.pack(side=tk.LEFT, padx=(6, 0))
        self.window_button = ttk.Button(capture_row, text=self.t("window"), style="Compact.TButton", command=self._capture_window)
        self.window_button.pack(side=tk.LEFT, padx=(6, 0))

        self.model_title = self._section(parent, "configuration")
        self.backend_label = ttk.Label(parent, text=self.t("backend"), style="Muted.TLabel")
        self.backend_label.pack(anchor="w")
        self.backend_var = tk.StringVar()
        self.backend_combo = ttk.Combobox(parent, textvariable=self.backend_var, state="readonly")
        self.backend_combo.pack(fill=tk.X, pady=(4, 8))
        self.backend_combo.bind("<<ComboboxSelected>>", self._backend_changed)
        self.model_label = ttk.Label(parent, text=self.t("model"), style="Muted.TLabel")
        self.model_label.pack(anchor="w")
        self.model_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.model_var).pack(fill=tk.X, pady=(4, 0))

        self.task_title = self._section(parent, "task")
        self.task_text = tk.Text(parent, width=30, height=7, wrap="word", undo=True, **text_widget_options(self.font_size))
        self.task_text.pack(fill=tk.BOTH, expand=True, pady=(0, 2))

        self.execution_title = self._section(parent, "execution")
        options = ttk.Frame(parent, style="App.TFrame")
        options.pack(fill=tk.X)
        options.columnconfigure(1, weight=1)
        self.steps_label = ttk.Label(options, text=self.t("max_steps"), style="Muted.TLabel")
        self.steps_label.grid(row=0, column=0, sticky="w", pady=2)
        self.steps_var = tk.IntVar(value=200)
        ttk.Spinbox(options, from_=1, to=1000, textvariable=self.steps_var, width=8).grid(row=0, column=1, sticky="e", pady=2)
        self.confirm_var = tk.BooleanVar(value=False)
        self.confirm_check = ttk.Checkbutton(options, text=self.t("confirm_actions"), variable=self.confirm_var)
        self.confirm_check.grid(row=1, column=0, columnspan=2, sticky="w")
        self.audio_var = tk.BooleanVar(value=True)
        self.audio_check = ttk.Checkbutton(options, text=self.t("audio"), variable=self.audio_var)
        self.audio_check.grid(row=2, column=0, columnspan=2, sticky="w")
        self.continuous_var = tk.BooleanVar(value=True)
        self.continuous_check = ttk.Checkbutton(options, text=self.t("continuous_audio"), variable=self.continuous_var)
        self.continuous_check.grid(row=3, column=0, columnspan=2, sticky="w")
        self.duration_label = ttk.Label(options, text=self.t("audio_duration"), style="Muted.TLabel")
        self.duration_label.grid(row=4, column=0, sticky="w", pady=(3, 0))
        self.duration_var = tk.IntVar(value=5)
        ttk.Spinbox(options, from_=1, to=30, textvariable=self.duration_var, width=8).grid(row=4, column=1, sticky="e", pady=(3, 0))

        self.audio_status_var = tk.StringVar(value=self.t("audio_idle"))
        ttk.Label(parent, textvariable=self.audio_status_var, style="Muted.TLabel", wraplength=320).pack(fill=tk.X, pady=(10, 8))
        actions = ttk.Frame(parent, style="App.TFrame")
        actions.pack(fill=tk.X)
        self.start_button = ttk.Button(actions, text=self.t("start"), style="Accent.TButton", command=self.start_task)
        self.start_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.stop_button = ttk.Button(actions, text=self.t("stop"), style="Danger.TButton", command=self.stop_task, state="disabled")
        self.stop_button.pack(side=tk.LEFT, padx=(8, 0))

    def _build_inspector(self, parent) -> None:
        self.inspector_tabs = ttk.Notebook(parent)
        self.inspector_tabs.pack(fill=tk.BOTH, expand=True)
        self.activity_tab = ActivityView(self.inspector_tabs, self.t)
        self.chat_tab = ChatView(self.inspector_tabs, self.t, self.font_size)
        self.zone_tab = ZoneView(self.inspector_tabs, self.t, self._zones_changed)
        self.inspector_tabs.add(self.activity_tab, text=self.t("activity"))
        self.inspector_tabs.add(self.chat_tab, text=self.t("chat_output"))
        self.inspector_tabs.add(self.zone_tab, text=self.t("zones"))

    def _build_statusbar(self, parent) -> None:
        bar = ttk.Frame(parent, style="Nav.TFrame", padding=(12, 5))
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_var = tk.StringVar(value=self.t("ready"))
        ttk.Label(bar, textvariable=self.status_var, style="Status.TLabel").pack(side=tk.LEFT)
        self.target_status_var = tk.StringVar()
        ttk.Label(bar, textvariable=self.target_status_var, style="Status.TLabel").pack(side=tk.RIGHT)

    def _show_view(self, name: str) -> None:
        if name not in self.views:
            name = "workspace"
        self.current_view = name
        self.views[name].tkraise()
        for key, button in self.nav_buttons.items():
            button.configure(style="NavActive.TButton" if key == name else "Nav.TButton")
        if name == "history":
            self.history_view.reload()

    def _set_target(self, target: str, initial: bool = False) -> None:
        if target not in {"desktop", "android"}:
            return
        self.target = target
        if target == "desktop" and self.work_mode == "chat":
            self.work_mode = "build"
        self.windows_button.configure(style="SegmentActive.TButton" if target == "desktop" else "Segment.TButton")
        self.android_button.configure(style="SegmentActive.TButton" if target == "android" else "Segment.TButton")
        self.chat_button.configure(state="normal" if target == "android" else "disabled")
        if target == "android":
            self.desktop_connection.pack_forget()
            self.android_connection.pack(fill=tk.X, before=self.model_title)
        else:
            self.android_connection.pack_forget()
            self.desktop_connection.pack(fill=tk.X, before=self.model_title)
        self.screen.set_target(target)
        self._update_backend_options(preferred=self.saved_backend if initial else "")
        self._update_mode_controls()
        self._update_target_status()
        if target == "android" and not initial:
            self.refresh_devices()

    def _set_work_mode(self, mode: str, initial: bool = False) -> None:
        if mode == "chat" and self.target != "android":
            mode = "build"
        self.work_mode = mode if mode in {"build", "chat"} else "build"
        self._update_mode_controls()
        self._update_backend_options(preferred="observe_adb" if self.work_mode == "chat" else (self.saved_backend if initial else ""))
        if self.work_mode == "chat":
            current = self.task_text.get("1.0", "end-1c").strip()
            if not current:
                self.task_text.insert("1.0", self.t("chat_default_task"))
            self.inspector_tabs.select(self.chat_tab)
        else:
            self.inspector_tabs.select(self.activity_tab)

    def _update_mode_controls(self) -> None:
        self.build_button.configure(style="SegmentActive.TButton" if self.work_mode == "build" else "Segment.TButton")
        self.chat_button.configure(style="SegmentActive.TButton" if self.work_mode == "chat" else "Segment.TButton")
        self.mode_hint_var.set(self.t("chat_hint" if self.work_mode == "chat" else "build_hint"))

    def _update_backend_options(self, preferred: str = "") -> None:
        options = backend_options(self.target, self.work_mode)
        self.backend_label_to_id = {label: key for key, label in options.items()}
        self.backend_combo.configure(values=list(self.backend_label_to_id))
        backend = preferred if preferred in options else next(iter(options))
        self.backend_var.set(options[backend])
        self.model_var.set(default_model_for_backend(backend))
        self._apply_backend_profile(backend)

    def _selected_backend(self) -> str:
        return self.backend_label_to_id.get(self.backend_var.get(), next(iter(backend_options(self.target, self.work_mode))))

    def _backend_changed(self, _event=None) -> None:
        backend = self._selected_backend()
        self.model_var.set(default_model_for_backend(backend))
        self._apply_backend_profile(backend)

    def _apply_backend_profile(self, backend: str) -> None:
        profile = backend_profile(backend)
        self.audio_check.configure(state="normal")
        if profile:
            self.steps_var.set(profile.default_steps)
            if profile.force_audio:
                self.audio_var.set(True)
                self.continuous_var.set(True)
                self.audio_check.configure(state="disabled")
            current = self.task_text.get("1.0", "end-1c").strip()
            if not current:
                self.task_text.insert("1.0", profile.default_task)
        elif backend == "observe_adb":
            self.steps_var.set(500)
            self.audio_var.set(True)
            self.continuous_var.set(True)

    def refresh_devices(self) -> None:
        if self.target != "android":
            return
        self.refresh_button.configure(state="disabled")
        self.device_detail_var.set(self.t("scanning"))
        self.progress.start(12)

        def worker() -> None:
            try:
                self._emit("devices", BackendBridge.scan_devices())
            except Exception as exc:
                self._emit("device_error", str(exc))

        threading.Thread(target=worker, name="UIV2ADBScan", daemon=True).start()

    def _apply_devices(self, devices: list[object]) -> None:
        self.refresh_button.configure(state="normal")
        if not self.running:
            self.progress.stop()
        self.devices = {getattr(device, "device_id", ""): device for device in devices}
        self.device_label_to_id = {getattr(device, "display_name", getattr(device, "device_id", "")): getattr(device, "device_id", "") for device in devices}
        labels = list(self.device_label_to_id)
        self.device_combo.configure(values=labels)
        last = get_adb_settings().get("last_device_id", "")
        selected = next((label for label, device_id in self.device_label_to_id.items() if device_id == last), labels[0] if labels else "")
        self.device_var.set(selected)
        self._device_selected()
        if not devices:
            self.device_detail_var.set(self.t("no_devices"))
        logger.info("ADB scan: %d device(s), %d ready", len(devices), sum(1 for d in devices if getattr(d, "state", "") == "device"))

    def _device_selected(self, _event=None) -> None:
        device_id = self._selected_device_id()
        if not device_id:
            self.device_detail_var.set(self.t("no_devices"))
            return
        device = self.devices.get(device_id)
        state = getattr(device, "state", "")
        if state != "device":
            self.device_detail_var.set(f"{self.t('device_unavailable')} · {state}")
            return
        detail = [self.t("device_ready")]
        manufacturer = getattr(device, "manufacturer", "")
        model = getattr(device, "model", "")
        android = getattr(device, "android_version", "")
        if manufacturer or model:
            detail.append(f"{manufacturer} {model}".strip())
        if android:
            detail.append(f"Android {android}")
        detail.append(device_id)
        self.device_detail_var.set("  ·  ".join(detail))
        update_adb_device(device_id)
        self.screen.configure_phone(get_adb_settings().get("path", "adb"), device_id)
        self.screen.start_preview()
        self._update_target_status()

    def _selected_device_id(self) -> str:
        return self.device_label_to_id.get(self.device_var.get(), "")

    def _enable_keyboard(self) -> None:
        device = self._selected_device_id()
        if not device:
            messagebox.showwarning(self.t("keyboard"), self.t("select_device"), parent=self.root)
            return
        self.keyboard_button.configure(state="disabled")

        def worker() -> None:
            try:
                self._emit("keyboard", BackendBridge.enable_keyboard(device))
            except Exception as exc:
                self._emit("keyboard_error", str(exc))

        threading.Thread(target=worker, name="UIV2Keyboard", daemon=True).start()

    def _open_audio_helper(self) -> None:
        device = self._selected_device_id()
        if not device:
            messagebox.showwarning(self.t("audio_helper"), self.t("select_device"), parent=self.root)
            return

        def worker() -> None:
            try:
                BackendBridge.open_audio_helper(device)
                self._emit("audio", self.t("audio_idle"))
            except Exception as exc:
                self._emit("start_error", str(exc))

        threading.Thread(target=worker, name="UIV2AudioHelper", daemon=True).start()

    def _capture_fullscreen(self) -> None:
        from windows.capture import fullscreen_capture_spec

        self.desktop_capture_spec = fullscreen_capture_spec()
        self._update_target_status()
        self.root.iconify()

        def capture() -> None:
            try:
                from windows.capture import capture_desktop

                image, _frame = capture_desktop(
                    self.desktop_capture_spec,
                    save=True,
                )
                self._emit("desktop_image", image)
            except Exception as exc:
                self._emit("start_error", str(exc))
            finally:
                self.root.after(0, self.root.deiconify)

        self.root.after(250, capture)

    def _capture_region(self) -> None:
        self.root.withdraw()

        def selected(region) -> None:
            if not region:
                self.root.deiconify()
                return
            from windows.capture import region_capture_spec

            self.desktop_capture_spec = region_capture_spec(*region)
            self._update_target_status()

            def capture() -> None:
                try:
                    from windows.capture import capture_desktop

                    image, _frame = capture_desktop(
                        self.desktop_capture_spec,
                        save=True,
                    )
                    self.screen.set_desktop_image(image)
                except Exception as exc:
                    messagebox.showerror(
                        self.t("desktop_capture"),
                        str(exc),
                        parent=self.root,
                    )
                finally:
                    self.root.deiconify()

            self.root.after(150, capture)

        RegionPicker(self.root, self.t, selected)

    def _capture_window(self) -> None:
        def selected(hwnd: Optional[int]) -> None:
            if hwnd is None:
                return
            try:
                from windows.capture import (
                    capture_desktop,
                    window_capture_spec,
                )

                self.desktop_capture_spec = window_capture_spec(hwnd)
                image, _frame = capture_desktop(
                    self.desktop_capture_spec,
                    save=True,
                )
                self.screen.set_desktop_image(image)
                self._update_target_status()
            except Exception as exc:
                messagebox.showerror(self.t("desktop_capture"), str(exc), parent=self.root)

        WindowPicker(self.root, self.t, selected)

    def start_task(self) -> None:
        if self.running:
            return
        request = RunRequest(
            target=self.target,
            work_mode=self.work_mode,
            backend=self._selected_backend(),
            model=self.model_var.get().strip(),
            task=self.task_text.get("1.0", "end-1c").strip(),
            device_id=self._selected_device_id() if self.target == "android" else "",
            screenshot_b64=None,
            desktop_capture=(
                dict(self.desktop_capture_spec)
                if self.target == "desktop"
                else None
            ),
            max_steps=self._coerce_int(self.steps_var.get(), 200, 1, 1000),
            confirm_actions=self.confirm_var.get(),
            audio_enabled=self.audio_var.get(),
            continuous_audio=self.continuous_var.get(),
            audio_duration=self._coerce_int(self.duration_var.get(), 5, 1, 30),
            forbidden_rects=self.zone_tab.current_zones(),
        )
        self.activity_tab.clear()
        if self.work_mode == "chat":
            self.chat_tab.clear()
        self.screen.start_run()
        self._set_running(True)
        self.status_var.set(self.t("running"))

        def worker() -> None:
            try:
                self.bridge.start(request)
            except Exception as exc:
                self._emit("start_error", str(exc))

        if self.target == "desktop":
            capture_mode = str(self.desktop_capture_spec.get("mode", "fullscreen"))
            self._desktop_window_hidden = capture_mode in {"fullscreen", "region"}
            if self._desktop_window_hidden:
                self.root.iconify()
            self._start_desktop_stop_watcher()
            self.root.after(
                250 if self._desktop_window_hidden else 0,
                lambda: threading.Thread(
                    target=worker,
                    name="UIV2TaskStart",
                    daemon=True,
                ).start(),
            )
        else:
            threading.Thread(
                target=worker,
                name="UIV2TaskStart",
                daemon=True,
            ).start()
        self._save_panel_state()

    def stop_task(self) -> None:
        if not self.running:
            return
        self.bridge.stop()
        self.status_var.set(self.t("stopped"))
        self.global_status_var.set(self.t("stopped"))

    def _set_running(self, running: bool) -> None:
        self.running = running
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")
        if running:
            self.global_status.configure(style="Warning.TLabel")
            self.global_status_var.set(self.t("running"))
            self.progress.start(12)
        else:
            self.global_status.configure(style="Success.TLabel")
            self.global_status_var.set(self.t("ready"))
            self.progress.stop()

    def _zones_changed(self, zones: list[dict], draw: bool) -> None:
        if hasattr(self, "screen"):
            self.screen.set_zones(zones)
            self.screen.set_zone_drawing(draw)

    def _zone_added(self, zone: dict) -> None:
        self.zone_tab.add_zone(zone)
        self.inspector_tabs.select(self.zone_tab)

    def _emit(self, kind: str, payload: object) -> None:
        self.events.put((kind, payload))

    def _drain_events(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            self._handle_event(kind, payload)
        self.root.after(100, self._drain_events)

    def _handle_event(self, kind: str, payload: object) -> None:
        if kind == "devices":
            self._apply_devices(list(payload) if isinstance(payload, list) else [])
        elif kind == "device_error":
            self.refresh_button.configure(state="normal")
            if not self.running:
                self.progress.stop()
            self.device_detail_var.set(self.t("scan_failed", error=str(payload)))
            logger.error("ADB device scan failed: %s", payload)
        elif kind == "keyboard":
            self.keyboard_button.configure(state="normal")
            ime = str(payload)
            self.device_detail_var.set(self.t("keyboard_enabled", ime=ime) if ime else self.t("keyboard_missing"))
        elif kind == "keyboard_error":
            self.keyboard_button.configure(state="normal")
            messagebox.showerror(self.t("keyboard"), str(payload), parent=self.root)
        elif kind == "desktop_image" and isinstance(payload, Image.Image):
            self.screen.set_desktop_image(payload)
        elif kind == "audio":
            self.audio_status_var.set(str(payload))
        elif kind == "action" and isinstance(payload, dict):
            action = payload.get("action", {})
            step = int(payload.get("step", 0))
            if isinstance(action, dict):
                self.activity_tab.append(action, step)
                self.screen.mark_action(action, step)
        elif kind == "chat" and isinstance(payload, dict):
            self.chat_tab.append(str(payload.get("text", "")), int(payload.get("step", 0)))
            self.inspector_tabs.select(self.chat_tab)
        elif kind == "complete" and isinstance(payload, dict):
            success = bool(payload.get("success"))
            message = str(payload.get("message", ""))
            self._restore_desktop_window()
            self._set_running(False)
            self.status_var.set(self.t("task_complete") if success else self.t("task_failed", error=message))
            self.history_view.reload()
            if success:
                logger.info("Automation complete: %s", message)
            else:
                logger.error("Automation failed: %s", message)
        elif kind == "start_error":
            self._restore_desktop_window()
            self._set_running(False)
            error = self._localized_error(str(payload))
            self.status_var.set(self.t("start_failed", error=error))
            messagebox.showerror(self.t("start"), error, parent=self.root)
        elif kind == "desktop_stop":
            self.stop_task()
            self._restore_desktop_window()

    def _localized_error(self, value: str) -> str:
        if value == "missing_task":
            return self.t("missing_task")
        if value == "select_device":
            return self.t("select_device")
        if value.startswith("missing_api:"):
            return self.t("missing_api", provider=value.split(":", 1)[1])
        if value.startswith("missing_base:"):
            return self.t("missing_base", provider=value.split(":", 1)[1])
        return value

    def _update_target_status(self) -> None:
        if self.target == "android":
            device = self._selected_device_id()
            self.target_status_var.set(f"Android · {device or self.t('no_devices')}")
        else:
            mode = str(self.desktop_capture_spec.get("mode", "fullscreen"))
            self.target_status_var.set(f"Windows · {self.t(mode)}")

    def _start_desktop_stop_watcher(self) -> None:
        def watch() -> None:
            try:
                from ctypes import windll

                while self.running and self.target == "desktop":
                    if windll.user32.GetAsyncKeyState(0x1B) & 0x8000:
                        self._emit("desktop_stop", None)
                        return
                    threading.Event().wait(0.08)
            except Exception:
                logger.debug("Global desktop stop watcher unavailable", exc_info=True)

        threading.Thread(
            target=watch,
            name="UIV2DesktopStop",
            daemon=True,
        ).start()

    def _restore_desktop_window(self) -> None:
        if not self._desktop_window_hidden:
            return
        self._desktop_window_hidden = False
        try:
            self.root.deiconify()
            self.root.lift()
        except tk.TclError:
            logger.debug("Unable to restore desktop window", exc_info=True)

    def _open_settings(self) -> None:
        if self._settings_window is not None and self._settings_window.winfo_exists():
            self._settings_window.lift()
            return
        self._settings_window = SettingsWindow(self.root, self.t, self._settings_saved)

    def _settings_saved(self) -> None:
        self.status_var.set(self.t("settings_saved"))
        if self.target == "android":
            self.refresh_devices()
        self.model_var.set(default_model_for_backend(self._selected_backend()))

    def _language_changed(self, _event=None) -> None:
        label = self.language_var.get()
        language = next((key for key, value in LANGUAGES.items() if value == label), "en")
        self.language = language
        self.translator.set_language(language)
        update_ui_settings(language=language)
        self._update_texts()

    def _font_changed(self) -> None:
        try:
            size = max(9, min(16, int(self.font_var.get())))
        except (TypeError, ValueError, tk.TclError):
            return
        self.font_size = size
        apply_theme(self.root, size)
        update_ui_settings(font_size=size)
        self._configure_tk_fonts(self.root, size)

    def _configure_tk_fonts(self, widget, size: int) -> None:
        if isinstance(widget, tk.Text):
            family = MONO_FONT if widget in {getattr(self.skills_view, "editor", None), getattr(self.logs_view, "text", None)} else UI_FONT
            widget.configure(font=(family, size))
        elif isinstance(widget, tk.Listbox):
            widget.configure(font=(UI_FONT, size))
        for child in widget.winfo_children():
            self._configure_tk_fonts(child, size)

    def _update_texts(self) -> None:
        self.tagline_label.configure(text=self.t("app_tagline"))
        self.settings_button.configure(text=self.t("settings"))
        self.font_label.configure(text=self.t("font_size"))
        self.language_label.configure(text=self.t("language"))
        self.shortcut_label.configure(text=self.t("nav_shortcut"))
        for key, button in self.nav_buttons.items():
            button.configure(text=self.t(key))
        self.target_label.configure(text=self.t("target"))
        self.windows_button.configure(text=self.t("windows"))
        self.android_button.configure(text=self.t("android"))
        self.mode_label.configure(text=self.t("work_mode"))
        self.build_button.configure(text=self.t("build"))
        self.chat_button.configure(text=self.t("chat"))
        self.connection_title.configure(text=self.t("connection"))
        self.device_label.configure(text=self.t("device"))
        self.refresh_button.configure(text=self.t("refresh"))
        self.keyboard_button.configure(text=self.t("enable_keyboard"))
        self.audio_helper_button.configure(text=self.t("audio_helper"))
        self.fullscreen_button.configure(text=self.t("fullscreen"))
        self.region_button.configure(text=self.t("region"))
        self.window_button.configure(text=self.t("window"))
        self.model_title.configure(text=self.t("configuration"))
        self.backend_label.configure(text=self.t("backend"))
        self.model_label.configure(text=self.t("model"))
        self.task_title.configure(text=self.t("task"))
        self.execution_title.configure(text=self.t("execution"))
        self.steps_label.configure(text=self.t("max_steps"))
        self.confirm_check.configure(text=self.t("confirm_actions"))
        self.audio_check.configure(text=self.t("audio"))
        self.continuous_check.configure(text=self.t("continuous_audio"))
        self.duration_label.configure(text=self.t("audio_duration"))
        self.start_button.configure(text=self.t("start"))
        self.stop_button.configure(text=self.t("stop"))
        self.inspector_tabs.tab(self.activity_tab, text=self.t("activity"))
        self.inspector_tabs.tab(self.chat_tab, text=self.t("chat_output"))
        self.inspector_tabs.tab(self.zone_tab, text=self.t("zones"))
        self.activity_tab.update_texts()
        self.chat_tab.update_texts()
        self.zone_tab.update_texts()
        self.screen.update_texts()
        self.history_view.update_texts()
        self.skills_view.update_texts()
        self.logs_view.update_texts()
        self._update_mode_controls()
        self._update_target_status()
        if not self.running:
            self.global_status_var.set(self.t("ready"))

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-Return>", lambda _event: self.start_task())
        self.root.bind("<Escape>", lambda _event: self.stop_task())
        self.root.bind("<F5>", lambda _event: self.refresh_devices())
        self.root.bind("<Control-s>", self._save_context)

    def _save_context(self, _event=None) -> None:
        if self.current_view == "skills":
            self.skills_view.save_selected()
        elif self.current_view == "workspace":
            path = self.screen.save_image()
            if path:
                self.status_var.set(self.t("screen_saved", path=path))

    def _load_panel_state(self, state: dict) -> None:
        if state.get("model"):
            self.model_var.set(str(state["model"]))
        if state.get("task"):
            self.task_text.delete("1.0", tk.END)
            self.task_text.insert("1.0", str(state["task"]))
        self.steps_var.set(self._coerce_int(state.get("steps"), self.steps_var.get(), 1, 1000))
        self.confirm_var.set(bool(state.get("confirm", False)))
        self.audio_var.set(bool(state.get("audio_enabled", self.audio_var.get())))
        self.continuous_var.set(bool(state.get("continuous_audio", self.continuous_var.get())))
        self.duration_var.set(self._coerce_int(state.get("audio_duration"), self.duration_var.get(), 1, 30))

    @staticmethod
    def _coerce_int(value: object, default: int, minimum: int, maximum: int) -> int:
        """Read legacy numeric settings such as ``"3s"`` without aborting startup."""
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            digits = "".join(character for character in str(value or "") if character.isdigit())
            parsed = int(digits) if digits else int(default)
        return max(minimum, min(maximum, parsed))

    def _save_panel_state(self) -> None:
        settings = load_settings()
        settings["panel_state"] = {
            "backend": self._selected_backend(),
            "model": self.model_var.get().strip(),
            "task": self.task_text.get("1.0", "end-1c").strip(),
            "steps": self._coerce_int(self.steps_var.get(), 200, 1, 1000),
            "confirm": self.confirm_var.get(),
            "audio_enabled": self.audio_var.get(),
            "continuous_audio": self.continuous_var.get(),
            "audio_duration": self._coerce_int(self.duration_var.get(), 5, 1, 30),
        }
        settings.setdefault("ui", {})["last_view"] = self.current_view
        save_settings(settings)

    def _close(self) -> None:
        self._save_panel_state()
        self.bridge.stop()
        self.screen.close()
        logging.getLogger().removeHandler(self.log_handler)
        self.root.destroy()
