"""Main application window and panel orchestration."""
from __future__ import annotations

import base64
import io
import logging
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image

from auto_click.modes.profiles import ANDROID_MODE_LABELS

logger = logging.getLogger(__name__)


class MainWindow:
    DESKTOP_BACKENDS = {
        "openai": "OpenAI Computer Use",
        "vlm_coords": "Generic VLM coordinates",
    }
    ANDROID_BACKENDS = {
        **ANDROID_MODE_LABELS,
        "glm_adb": "GLM Vision (glm-4.6v-flashx)",
        "openai_adb": "OpenAI Computer Use",
        "adb_vlm": "Generic VLM coordinates",
        "deepseek_adb": "DeepSeek Vision",
        "autoglm_phone": "AutoGLM-Phone",
    }

    def __init__(self, root: tk.Tk):
        self.root = root
        self._current_image: Image.Image | None = None
        from settings_store import get_ui_settings

        ui_settings = get_ui_settings()
        self._language = ui_settings.get("language", "zh-CN")
        self._font_size = int(ui_settings.get("font_size", 10) or 10)
        self._mode_var = tk.StringVar(value="android")
        self._backend_var = tk.StringVar()
        self._build_mode_var = tk.StringVar(value="build")
        self._capture_mode_var = tk.StringVar(value="fullscreen")
        self._log_handler = self._install_log_handler()
        self._apply_font_size(self._font_size)
        self._build_menu()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_menu(self) -> None:
        from ui.i18n import t

        menubar = tk.Menu(self.root)
        self.root.configure(menu=menubar)
        self._menubar = menubar

        file_menu = tk.Menu(menubar, tearoff=0)
        self._file_menu = file_menu
        menubar.add_cascade(label=t(self._language, "file"), menu=file_menu)
        file_menu.add_command(label=t(self._language, "save_screenshot"), command=self._save_screenshot, accelerator="Ctrl+S")
        file_menu.add_separator()
        file_menu.add_command(label=t(self._language, "exit"), command=self._on_close, accelerator="Alt+F4")

        settings_menu = tk.Menu(menubar, tearoff=0)
        self._settings_menu = settings_menu
        menubar.add_cascade(label=t(self._language, "settings_menu"), menu=settings_menu)
        settings_menu.add_command(label=t(self._language, "api_adb_settings"), command=self._open_settings)
        settings_menu.add_command(label=t(self._language, "clear_result"), command=self._clear_results)
        self.root.bind("<Control-s>", lambda _event: self._save_screenshot())

    def _build_ui(self) -> None:
        from settings_store import load_settings
        from ui.auto_click_panel import AutoClickPanel
        from ui.chat_panel import ChatPanel
        from ui.image_preview import ImagePreviewPanel
        from ui.log_panel import LogPanel
        from ui.phone_screen_panel import PhoneScreenPanel
        from ui.result_panel import ResultPanel

        panel_state = load_settings().get("panel_state", {})
        initial_backend = panel_state.get("backend", "cida_work")
        if initial_backend == "observe_adb":
            self._build_mode_var.set("chat")
            initial_backend = "cida_work"
        self._mode_var.set("android" if initial_backend in self.ANDROID_BACKENDS else "desktop")

        self._status_var = tk.StringVar(value="Ready")
        self._build_top_nav()

        body = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)
        left_col = ttk.PanedWindow(body, orient=tk.VERTICAL)
        center_col = ttk.PanedWindow(body, orient=tk.VERTICAL)
        right_side = ttk.PanedWindow(body, orient=tk.VERTICAL)
        body.add(left_col, weight=6)
        body.add(center_col, weight=5)
        body.add(right_side, weight=3)
        self._body_pane = body
        self._left_pane = left_col
        self._center_pane = center_col
        self._right_pane = right_side
        self._build_connection_panel(right_side)

        from ui.i18n import t

        current_task = ttk.LabelFrame(left_col, text=t(self._language, "current_task"))
        self._current_task_frame = current_task
        left_col.add(current_task, weight=3)
        self.auto_click_panel = AutoClickPanel(
            current_task,
            get_screenshot_fn=self._current_image_b64,
            open_settings_fn=self._open_settings,
            forbidden_rects_fn=self._active_forbidden_rects,
            adb_parent=self._android_adb_host,
            show_backend_selector=False,
            on_history_update=lambda: self.result_panel.reload_history() if hasattr(self, "result_panel") else None,
            on_chat_message=self._on_chat_message,
        )
        self.auto_click_panel.pack(fill=tk.BOTH, expand=True)

        live_frame = ttk.LabelFrame(center_col, text=t(self._language, "live_screen"))
        self._live_frame = live_frame
        center_col.add(live_frame, weight=3)
        self.desktop_preview = ImagePreviewPanel(live_frame, language=self._language)
        self.phone_screen_panel = PhoneScreenPanel(live_frame)
        self.auto_click_panel.set_phone_screen_panel(self.phone_screen_panel)

        from ui.forbidden_zones_panel import ForbiddenZonesPanel

        self.forbidden_zones_panel = ForbiddenZonesPanel(
            right_side, on_change=self._apply_forbidden_zones, language=self._language
        )
        right_side.add(self.forbidden_zones_panel, weight=1)
        self.desktop_preview.set_forbidden_rect_callback(self._on_forbidden_rect_added)
        self.phone_screen_panel.set_forbidden_rect_callback(self._on_forbidden_rect_added)

        history_frame = ttk.LabelFrame(left_col, text=t(self._language, "history"))
        self._history_frame = history_frame
        left_col.add(history_frame, weight=2)
        self.result_panel = ResultPanel(history_frame, language=self._language)
        self.result_panel.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        skill_frame = ttk.LabelFrame(center_col, text=t(self._language, "skills"))
        self._skill_frame = skill_frame
        center_col.add(skill_frame, weight=2)
        self._build_skill_panel(skill_frame)

        chat_frame = ttk.LabelFrame(right_side, text="Chat 回复")
        self._chat_frame = chat_frame
        right_side.add(chat_frame, weight=2)
        self.chat_panel = ChatPanel(chat_frame)
        self.chat_panel.pack(fill=tk.BOTH, expand=True)

        log_frame = ttk.LabelFrame(right_side, text=t(self._language, "run_log"))
        self._log_frame = log_frame
        right_side.add(log_frame, weight=3)
        self.log_panel = LogPanel(log_frame, self._log_handler)
        self.log_panel.pack(fill=tk.BOTH, expand=True)

        status_bar = ttk.Frame(self.root, relief="flat")
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Label(status_bar, textvariable=self._status_var, font=("Segoe UI", 8), anchor="w").pack(
            side=tk.LEFT, padx=4
        )

        self._set_mode(self._mode_var.get(), initial_backend=initial_backend)
        self._apply_forbidden_zones()
        self._configure_widget_fonts(self.root, self._font_size)

    def _build_top_nav(self) -> None:
        from ui.i18n import LANGUAGES, t

        nav = ttk.Frame(self.root)
        nav.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(nav, text="Auto-GLMPhone Plus", padding=(16, 10), font=("Segoe UI", 10, "bold")).pack(
            side=tk.LEFT
        )
        self._subtitle_label = ttk.Label(nav, text=t(self._language, "app_subtitle"), padding=(8, 10))
        self._subtitle_label.pack(side=tk.LEFT)
        self._settings_btn = ttk.Button(nav, text=t(self._language, "settings"), command=self._open_settings)
        self._settings_btn.pack(side=tk.RIGHT, padx=(0, 8), pady=6)
        self._language_var = tk.StringVar(value=LANGUAGES.get(self._language, LANGUAGES["zh-CN"]))
        ttk.Combobox(
            nav,
            textvariable=self._language_var,
            values=list(LANGUAGES.values()),
            state="readonly",
            width=10,
        ).pack(side=tk.RIGHT, padx=(0, 8), pady=6)
        self._language_var.trace_add("write", lambda *_: self._on_language_changed())
        self._font_size_var = tk.IntVar(value=self._font_size)
        ttk.Spinbox(
            nav,
            from_=8,
            to=18,
            width=4,
            textvariable=self._font_size_var,
            command=self._on_font_size_changed,
        ).pack(side=tk.RIGHT, padx=(0, 8), pady=6)
        self._font_label = ttk.Label(nav, text=t(self._language, "font_size"))
        self._font_label.pack(side=tk.RIGHT)
        self._language_label = ttk.Label(nav, text=t(self._language, "language"))
        self._language_label.pack(side=tk.RIGHT, padx=(0, 4))

    def _build_connection_panel(self, parent: ttk.Frame) -> None:
        from ui.i18n import t

        frame = ttk.LabelFrame(parent, text=t(self._language, "connection"))
        self._connection_frame = frame
        parent.add(frame, weight=0)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        self._controller_label = ttk.Label(frame, text=t(self._language, "controller"))
        self._controller_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 2))
        self._desktop_btn = ttk.Button(frame, text=t(self._language, "desktop"), command=lambda: self._set_mode("desktop"))
        self._desktop_btn.grid(row=1, column=0, sticky="ew", padx=(8, 4), pady=2)
        self._android_btn = ttk.Button(frame, text=t(self._language, "android"), command=lambda: self._set_mode("android"))
        self._android_btn.grid(row=1, column=1, sticky="ew", padx=(4, 8), pady=2)

        self._build_mode_label = ttk.Label(frame, text=self._work_mode_label_text())
        self._build_mode_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 2))
        self._build_btn = ttk.Radiobutton(
            frame,
            text="Build",
            value="build",
            variable=self._build_mode_var,
            command=self._on_build_mode_changed,
        )
        self._build_btn.grid(row=3, column=0, sticky="ew", padx=(8, 4), pady=2)
        self._chat_btn = ttk.Radiobutton(
            frame,
            text="Chat",
            value="chat",
            variable=self._build_mode_var,
            command=self._on_build_mode_changed,
        )
        self._chat_btn.grid(row=3, column=1, sticky="ew", padx=(4, 8), pady=2)
        self._build_hint_var = tk.StringVar(value="")
        self._build_hint_label = ttk.Label(
            frame,
            textvariable=self._build_hint_var,
            wraplength=260,
            font=("Segoe UI", 8),
            foreground="#888888",
        )
        self._build_hint_label.grid(row=4, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 4))

        self._backend_label = ttk.Label(frame, text=t(self._language, "automation_backend"))
        self._backend_label.grid(
            row=5, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 2)
        )
        self._backend_cb = ttk.Combobox(frame, textvariable=self._backend_var, state="readonly")
        self._backend_cb.grid(row=6, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 8))
        self._backend_cb.bind("<<ComboboxSelected>>", self._on_backend_selected)

        self._desktop_capture_frame = ttk.LabelFrame(parent, text=t(self._language, "desktop_capture"))
        parent.add(self._desktop_capture_frame, weight=0)
        self._capture_radio_buttons = []
        for idx, (label, value, command) in enumerate(
            (
                (t(self._language, "fullscreen"), "fullscreen", self._capture_fullscreen),
                (t(self._language, "region"), "region", self._capture_region),
                (t(self._language, "window"), "window", self._capture_window),
            )
        ):
            rb = ttk.Radiobutton(
                self._desktop_capture_frame,
                text=label,
                value=value,
                variable=self._capture_mode_var,
                command=command,
            )
            rb.grid(row=0, column=idx, sticky="w", padx=(8 if idx == 0 else 4, 4), pady=8)
            self._capture_radio_buttons.append((rb, value))

        self._android_adb_host = ttk.Frame(parent)
        parent.add(self._android_adb_host, weight=0)

    def _build_skill_panel(self, parent: ttk.Frame) -> None:
        from ui.i18n import t

        parent.columnconfigure(0, weight=1, minsize=160)
        parent.columnconfigure(1, weight=3, minsize=300)
        parent.rowconfigure(1, weight=1)

        left_toolbar = ttk.Frame(parent)
        left_toolbar.grid(row=0, column=0, sticky="ew", padx=(8, 4), pady=(8, 4))
        self._skill_refresh_btn = ttk.Button(left_toolbar, text=t(self._language, "refresh"), command=self._refresh_skill_list)
        self._skill_refresh_btn.pack(side=tk.LEFT)
        self._skill_new_btn = ttk.Button(left_toolbar, text=t(self._language, "new"), command=self._new_skill)
        self._skill_new_btn.pack(side=tk.LEFT, padx=(4, 0))
        self._skill_copy_btn = ttk.Button(left_toolbar, text=t(self._language, "copy"), command=self._copy_skill)
        self._skill_copy_btn.pack(side=tk.LEFT, padx=(4, 0))
        self._skill_delete_btn = ttk.Button(left_toolbar, text=t(self._language, "delete"), command=self._delete_skill)
        self._skill_delete_btn.pack(side=tk.LEFT, padx=(4, 0))
        self._force_skill_var = tk.BooleanVar(value=False)
        self._skill_force_check = ttk.Checkbutton(
            left_toolbar,
            text=self._skill_force_text(),
            variable=self._force_skill_var,
            command=self._toggle_forced_skill,
        )
        self._skill_force_check.pack(side=tk.LEFT, padx=(8, 0))

        right_toolbar = ttk.Frame(parent)
        right_toolbar.grid(row=0, column=1, sticky="ew", padx=(4, 8), pady=(8, 4))
        self._skill_save_btn = ttk.Button(right_toolbar, text=t(self._language, "save_changes"), command=self._save_skill)
        self._skill_save_btn.pack(side=tk.RIGHT)
        self._skill_status_var = tk.StringVar(value=t(self._language, "skill_select_hint"))
        ttk.Label(right_toolbar, textvariable=self._skill_status_var).pack(side=tk.LEFT)

        list_frame = ttk.Frame(parent)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=(8, 4), pady=(0, 8))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        self._skill_list = tk.Listbox(list_frame, height=8, activestyle="dotbox", exportselection=False)
        self._skill_list.grid(row=0, column=0, sticky="nsew")
        self._skill_list.bind("<<ListboxSelect>>", self._on_skill_selected)
        list_scroll = ttk.Scrollbar(list_frame, command=self._skill_list.yview)
        list_scroll.grid(row=0, column=1, sticky="ns")
        self._skill_list.configure(yscrollcommand=list_scroll.set)

        editor_frame = ttk.Frame(parent)
        editor_frame.grid(row=1, column=1, sticky="nsew", padx=(4, 8), pady=(0, 8))
        editor_frame.rowconfigure(0, weight=1)
        editor_frame.columnconfigure(0, weight=1)
        self._skill_editor = tk.Text(
            editor_frame,
            wrap="word",
            undo=True,
            font=("Consolas", 9),
            bg="#0d1117",
            fg="#c9d1d9",
            insertbackground="white",
            relief="flat",
        )
        self._skill_editor.grid(row=0, column=0, sticky="nsew")
        editor_scroll = ttk.Scrollbar(editor_frame, command=self._skill_editor.yview)
        editor_scroll.grid(row=0, column=1, sticky="ns")
        self._skill_editor.configure(yscrollcommand=editor_scroll.set)

        self._skill_paths: dict[str, Path] = {}
        self._forced_skill_names: set[str] = set()
        self._refresh_skill_list()

    def _refresh_skill_list(self) -> None:
        self._skill_list.delete(0, tk.END)
        self._skill_paths = {}
        self._forced_skill_names = self._load_forced_skill_names()
        try:
            for path in sorted((Path.cwd() / "skills").glob("*.md")):
                self._skill_paths[path.name] = path
                self._skill_list.insert(tk.END, self._skill_display_name(path.name))
            if self._skill_list.size():
                self._skill_list.selection_set(0)
                self._load_skill_by_name(self._selected_skill_name())
        except Exception as exc:
            self._skill_list.insert(tk.END, f"Skill scan failed: {exc}")

    def _selected_skill_name(self) -> str:
        selected = self._skill_list.curselection()
        return self._plain_skill_name(self._skill_list.get(selected[0])) if selected else ""

    def _selected_skill_path(self) -> Path | None:
        name = self._selected_skill_name()
        return self._skill_paths.get(name)

    def _on_skill_selected(self, event=None) -> None:
        name = self._selected_skill_name()
        if name:
            self._load_skill_by_name(name)

    def _load_skill_by_name(self, name: str) -> None:
        path = self._skill_paths.get(name)
        if path is None:
            return
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Skill", str(exc))
            return
        self._skill_editor.delete("1.0", tk.END)
        self._skill_editor.insert("1.0", content)
        forced = name in self._forced_skill_names
        if hasattr(self, "_force_skill_var"):
            self._force_skill_var.set(forced)
        suffix = " | forced" if forced else ""
        self._skill_status_var.set(f"Editing: {name}{suffix}")

    def _save_skill(self) -> None:
        path = self._selected_skill_path()
        if path is None:
            messagebox.showwarning("Skill", "Select a skill first.")
            return
        try:
            path.write_text(self._skill_editor.get("1.0", tk.END).rstrip() + "\n", encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Skill", str(exc))
            return
        self._skill_status_var.set(f"Saved: {path.name}")
        logger.info("Skill saved: %s", path)

    def _copy_skill(self) -> None:
        path = self._selected_skill_path()
        if path is None:
            messagebox.showwarning("Skill", "Select a skill first.")
            return
        base = path.with_name(f"{path.stem}_copy.md")
        target = base
        counter = 2
        while target.exists():
            target = path.with_name(f"{path.stem}_copy{counter}.md")
            counter += 1
        try:
            target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Skill", str(exc))
            return
        self._refresh_skill_list()
        self._select_skill(target.name)
        self._skill_status_var.set(f"Copied: {target.name}")

    def _new_skill(self) -> None:
        skills_dir = Path.cwd() / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        target = skills_dir / "new_skill.md"
        counter = 2
        while target.exists():
            target = skills_dir / f"new_skill_{counter}.md"
            counter += 1
        title = target.stem.replace("_", " ").title()
        content = (
            f"# {title}\n\n"
            "Describe when the model should use this skill.\n\n"
            "Recommended action format:\n\n"
            "```json\n"
            "{\"type\":\"wait\",\"seconds\":1}\n"
            "```\n"
        )
        try:
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Skill", str(exc))
            return
        self._refresh_skill_list()
        self._select_skill(target.name)
        self._skill_status_var.set(f"Created: {target.name}")

    def _delete_skill(self) -> None:
        path = self._selected_skill_path()
        if path is None:
            messagebox.showwarning("Skill", "Select a skill first.")
            return
        if not messagebox.askyesno("Delete Skill", f"Delete {path.name}?"):
            return
        try:
            path.unlink()
        except OSError as exc:
            messagebox.showerror("Skill", str(exc))
            return
        if path.name in self._forced_skill_names:
            self._forced_skill_names.discard(path.name)
            self._save_forced_skill_names()
        self._skill_editor.delete("1.0", tk.END)
        self._refresh_skill_list()
        self._skill_status_var.set(f"Deleted: {path.name}")

    def _select_skill(self, name: str) -> None:
        for idx in range(self._skill_list.size()):
            if self._plain_skill_name(self._skill_list.get(idx)) == name:
                self._skill_list.selection_clear(0, tk.END)
                self._skill_list.selection_set(idx)
                self._skill_list.see(idx)
                self._load_skill_by_name(name)
                break

    def _toggle_forced_skill(self) -> None:
        name = self._selected_skill_name()
        if not name:
            return
        if self._force_skill_var.get():
            self._forced_skill_names.add(name)
        else:
            self._forced_skill_names.discard(name)
        self._save_forced_skill_names()
        selected = name
        self._refresh_skill_list()
        self._select_skill(selected)
        logger.info("Forced skills updated: %s", ", ".join(sorted(self._forced_skill_names)) or "none")

    @staticmethod
    def _plain_skill_name(value: str) -> str:
        if value.startswith("[x] ") or value.startswith("[ ] "):
            return value[4:]
        return value

    def _skill_display_name(self, name: str) -> str:
        return f"[x] {name}" if name in self._forced_skill_names else f"[ ] {name}"

    @staticmethod
    def _load_forced_skill_names() -> set[str]:
        try:
            from settings_store import get_skill_settings
        except Exception:
            return set()
        forced = get_skill_settings().get("forced", [])
        if not isinstance(forced, list):
            return set()
        return {str(name) for name in forced if str(name).strip()}

    def _save_forced_skill_names(self) -> None:
        try:
            from settings_store import update_forced_skills

            update_forced_skills(sorted(self._forced_skill_names))
        except Exception as exc:
            messagebox.showerror("Skill", str(exc))

    def _set_mode(self, mode: str, initial_backend: str | None = None) -> None:
        if not hasattr(self, "_backend_cb"):
            return
        self._mode_var.set(mode)
        if mode == "desktop":
            self._build_mode_var.set("build")
        options = self.DESKTOP_BACKENDS if mode == "desktop" else self.ANDROID_BACKENDS
        labels = list(options.values())
        self._backend_cb["values"] = labels

        backend = initial_backend if initial_backend in options else next(iter(options))
        self._backend_var.set(options[backend])
        if hasattr(self, "auto_click_panel"):
            self.auto_click_panel.set_backend(self._effective_backend(backend))
        self._sync_build_mode_ui()

        if mode == "desktop":
            self._pane_show(self._right_pane, self._desktop_capture_frame, before=self.forbidden_zones_panel)
            self._pane_hide(self._right_pane, self._android_adb_host)
            self.phone_screen_panel.pack_forget()
            self.desktop_preview.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
            self._set_status(self._txt("desktop_status"))
        else:
            self._pane_hide(self._right_pane, self._desktop_capture_frame)
            self._pane_show(self._right_pane, self._android_adb_host, before=self.forbidden_zones_panel)
            self.desktop_preview.pack_forget()
            self.phone_screen_panel.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
            self._set_status(self._txt("android_status"))
        self._apply_forbidden_zones()

    @staticmethod
    def _pane_hide(pane: ttk.PanedWindow, child: tk.Widget) -> None:
        try:
            pane.forget(child)
        except tk.TclError:
            pass

    @staticmethod
    def _pane_show(pane: ttk.PanedWindow, child: tk.Widget, before: tk.Widget | None = None) -> None:
        try:
            panes = pane.panes()
            if str(child) in panes:
                return
            if before is not None and str(before) in panes:
                pane.insert(panes.index(str(before)), child, weight=0)
            else:
                pane.add(child, weight=0)
        except tk.TclError:
            pass

    def _active_forbidden_rects(self) -> list[dict]:
        if hasattr(self, "forbidden_zones_panel"):
            return self.forbidden_zones_panel.current_rects()
        return []

    def _on_forbidden_rect_added(self, rect: dict) -> None:
        if hasattr(self, "forbidden_zones_panel"):
            self.forbidden_zones_panel.add_rect(rect)

    def _apply_forbidden_zones(self) -> None:
        if not hasattr(self, "forbidden_zones_panel"):
            return
        rects = self.forbidden_zones_panel.current_rects()
        draw_enabled = self.forbidden_zones_panel.draw_enabled()
        if hasattr(self, "desktop_preview"):
            self.desktop_preview.set_forbidden_rects(rects)
            self.desktop_preview.set_forbidden_selection_enabled(
                draw_enabled and self._mode_var.get() == "desktop"
            )
        if hasattr(self, "phone_screen_panel"):
            self.phone_screen_panel.set_forbidden_rects(rects)
            self.phone_screen_panel.set_forbidden_selection_enabled(
                draw_enabled and self._mode_var.get() == "android"
            )

    def _on_chat_message(self, text: str, action: dict) -> None:
        if hasattr(self, "chat_panel"):
            self.chat_panel.append_message(text, title="Observe")

    def _on_backend_selected(self, event=None) -> None:
        mode = self._mode_var.get()
        options = self.DESKTOP_BACKENDS if mode == "desktop" else self.ANDROID_BACKENDS
        selected = self._backend_var.get()
        backend = next((key for key, label in options.items() if label == selected), None)
        if backend and hasattr(self, "auto_click_panel"):
            self.auto_click_panel.set_backend(self._effective_backend(backend))

    def _effective_backend(self, selected_backend: str) -> str:
        if self._mode_var.get() == "android" and self._build_mode_var.get() == "chat":
            return "observe_adb"
        return selected_backend

    def _on_build_mode_changed(self) -> None:
        if self._mode_var.get() != "android" and self._build_mode_var.get() == "chat":
            self._build_mode_var.set("build")
        self._sync_build_mode_ui()
        self._on_backend_selected()

    def _sync_build_mode_ui(self) -> None:
        if not hasattr(self, "_backend_cb"):
            return
        android_mode = self._mode_var.get() == "android"
        chat_mode = android_mode and self._build_mode_var.get() == "chat"
        self._chat_btn.configure(state="normal" if android_mode else "disabled")
        self._build_btn.configure(state="normal")
        self._backend_cb.configure(state="disabled" if chat_mode else "readonly")
        self._backend_label.configure(
            text="Automation backend" if not chat_mode else "Automation backend (Build only)"
        )
        self._build_hint_var.set(
            "Chat 模式：只观察手机屏幕和音频，整理笔记/回答问题，不点击、不输入、不返回。"
            if chat_mode
            else "Build 模式：使用下方自动化后端控制设备。"
        )

    def _capture_fullscreen(self) -> None:
        self._capture_mode_var.set("fullscreen")
        try:
            from windows.capture import capture_fullscreen

            self._on_capture(capture_fullscreen())
        except Exception as exc:
            logger.exception("Fullscreen capture failed")
            messagebox.showerror("Capture failed", str(exc))

    def _capture_region(self) -> None:
        self._capture_mode_var.set("region")
        try:
            from windows.capture import RegionCaptureOverlay, capture_region

            root = self.root
            root.withdraw()

            def _on_region(x1, y1, x2, y2):
                root.deiconify()
                if x1 is None:
                    return
                try:
                    self._on_capture(capture_region(x1, y1, x2, y2))
                except Exception as exc:
                    logger.exception("Region capture failed")
                    messagebox.showerror("Capture failed", str(exc))

            RegionCaptureOverlay(root, callback=_on_region)
        except Exception as exc:
            self.root.deiconify()
            logger.exception("Region capture failed")
            messagebox.showerror("Capture failed", str(exc))

    def _capture_window(self) -> None:
        self._capture_mode_var.set("window")
        try:
            from windows.capture import capture_window
            from windows.window_selector import WindowSelector

            def _on_hwnd(hwnd):
                if hwnd is None:
                    return
                try:
                    self._on_capture(capture_window(hwnd))
                except Exception as exc:
                    logger.exception("Window capture failed")
                    messagebox.showerror("Capture failed", str(exc))

            WindowSelector(self.root, callback=_on_hwnd)
        except Exception as exc:
            logger.exception("Window selector failed")
            messagebox.showerror("Capture failed", str(exc))

    def _on_capture(self, image: Image.Image) -> None:
        self._current_image = image
        if hasattr(self, "desktop_preview"):
            self.desktop_preview.fit_image(image)
        self._set_status(f"Desktop screenshot updated: {image.width}x{image.height} px")
        logger.info("Desktop screenshot captured: %sx%s", image.width, image.height)

    def _save_screenshot(self) -> None:
        if self._current_image is None:
            messagebox.showwarning("Save failed", "No screenshot is available.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg"), ("All files", "*.*")],
            initialdir="Screenshots",
        )
        if path:
            self._current_image.save(path)
            self._set_status(f"Saved: {path}")
            logger.info("Screenshot saved: %s", path)

    def _clear_results(self) -> None:
        self.result_panel.clear()
        self._set_status("Result cleared")

    def _set_status(self, msg: str) -> None:
        self._status_var.set(msg)

    def _txt(self, key: str) -> str:
        from ui.i18n import t

        return t(self._language, key)

    def _skill_force_text(self) -> str:
        return {
            "zh-CN": "强制使用",
            "en": "Force use",
            "ja": "強制使用",
            "zh-TW": "強制使用",
        }.get(self._language, "Force use")

    def _work_mode_label_text(self) -> str:
        return {
            "zh-CN": "工作模式",
            "en": "Work mode",
            "ja": "作業モード",
            "zh-TW": "工作模式",
        }.get(self._language, "Work mode")

    def _on_font_size_changed(self) -> None:
        from settings_store import update_ui_settings

        try:
            size = int(self._font_size_var.get())
        except Exception:
            return
        self._font_size = max(8, min(size, 18))
        self._apply_font_size(self._font_size)
        self._configure_widget_fonts(self.root, self._font_size)
        update_ui_settings(font_size=self._font_size)

    def _apply_font_size(self, size: int) -> None:
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkTooltipFont"):
            try:
                tkfont.nametofont(name).configure(size=size, weight="bold")
            except tk.TclError:
                pass
        try:
            style = ttk.Style()
            style.configure(".", font=("Segoe UI", size, "bold"))
            style.configure("TLabelframe.Label", font=("Segoe UI", size, "bold"))
        except tk.TclError:
            pass

    def _configure_widget_fonts(self, widget, size: int) -> None:
        for child in widget.winfo_children():
            try:
                current = child.cget("font")
                family = "Consolas" if "Text" in child.winfo_class() or "Listbox" in child.winfo_class() else "Segoe UI"
                if current:
                    child.configure(font=(family, size, "bold"))
            except Exception:
                pass
            self._configure_widget_fonts(child, size)

    def _on_language_changed(self) -> None:
        from settings_store import update_ui_settings
        from ui.i18n import LANGUAGES

        label = self._language_var.get()
        language = next((key for key, value in LANGUAGES.items() if value == label), "zh-CN")
        if language == self._language:
            return
        self._language = language
        update_ui_settings(language=language)
        self._refresh_language()

    def _refresh_language(self) -> None:
        from ui.i18n import t

        self._subtitle_label.configure(text=t(self._language, "app_subtitle"))
        if hasattr(self, "_menubar"):
            self._menubar.entryconfigure(0, label=t(self._language, "file"))
            self._menubar.entryconfigure(1, label=t(self._language, "settings_menu"))
            self._file_menu.entryconfigure(0, label=t(self._language, "save_screenshot"))
            self._file_menu.entryconfigure(2, label=t(self._language, "exit"))
            self._settings_menu.entryconfigure(0, label=t(self._language, "api_adb_settings"))
            self._settings_menu.entryconfigure(1, label=t(self._language, "clear_result"))
        self._settings_btn.configure(text=t(self._language, "settings"))
        self._font_label.configure(text=t(self._language, "font_size"))
        self._language_label.configure(text=t(self._language, "language"))
        self._current_task_frame.configure(text=t(self._language, "current_task"))
        self._live_frame.configure(text=t(self._language, "live_screen"))
        self._history_frame.configure(text=t(self._language, "history"))
        self._skill_frame.configure(text=t(self._language, "skills"))
        self._log_frame.configure(text=t(self._language, "run_log"))
        self._connection_frame.configure(text=t(self._language, "connection"))
        self._controller_label.configure(text=t(self._language, "controller"))
        self._desktop_btn.configure(text=t(self._language, "desktop"))
        self._android_btn.configure(text=t(self._language, "android"))
        if hasattr(self, "_build_mode_label"):
            self._build_mode_label.configure(text=self._work_mode_label_text())
            self._build_btn.configure(text="Build")
            self._chat_btn.configure(text="Chat")
        if hasattr(self, "_backend_label"):
            self._backend_label.configure(text=t(self._language, "automation_backend"))
        self._desktop_capture_frame.configure(text=t(self._language, "desktop_capture"))
        for rb, value in getattr(self, "_capture_radio_buttons", []):
            rb.configure(text=t(self._language, value))
        if hasattr(self, "_skill_refresh_btn"):
            self._skill_refresh_btn.configure(text=t(self._language, "refresh"))
            self._skill_new_btn.configure(text=t(self._language, "new"))
            self._skill_copy_btn.configure(text=t(self._language, "copy"))
            self._skill_delete_btn.configure(text=t(self._language, "delete"))
            self._skill_save_btn.configure(text=t(self._language, "save_changes"))
            self._skill_force_check.configure(text=self._skill_force_text())
        if hasattr(self, "forbidden_zones_panel"):
            self.forbidden_zones_panel.set_language(self._language)
        if hasattr(self, "result_panel"):
            self.result_panel.set_language(self._language)
        if hasattr(self, "desktop_preview"):
            self.desktop_preview.set_language(self._language)
        self._set_status(
            t(self._language, "desktop_status")
            if self._mode_var.get() == "desktop"
            else t(self._language, "android_status")
        )
        if hasattr(self, "_backend_cb"):
            self._sync_build_mode_ui()

    def _open_settings(self) -> None:
        from ui.settings_dialog import SettingsDialog

        SettingsDialog(self.root, on_save=self._on_settings_saved)

    def _on_settings_saved(self) -> None:
        self._set_status("Settings saved")
        logger.info("Settings saved")
        if hasattr(self, "auto_click_panel"):
            self.auto_click_panel.reload_settings()

    def _install_log_handler(self):
        from ui.log_panel import TkLogHandler

        handler = TkLogHandler()
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)
        return handler

    def _on_close(self) -> None:
        if hasattr(self, "auto_click_panel"):
            try:
                self.auto_click_panel.save_panel_state()
            except Exception:
                pass
        self.root.destroy()

    def _current_image_b64(self) -> str:
        if self._current_image is None:
            raise RuntimeError(self._txt("desktop_status"))
        image = self._current_image
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")
