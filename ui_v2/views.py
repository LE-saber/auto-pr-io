"""Focused utility views used by the redesigned application shell."""
from __future__ import annotations

import logging
import queue
import re
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Callable, Optional

from PIL import Image, ImageTk

import config
from settings_store import (
    get_forbidden_zone_settings,
    get_skill_settings,
    load_settings,
    save_settings,
    update_forced_skills,
)
from ui_v2.theme import COLORS, MONO_FONT, text_widget_options


class UILogHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: queue.Queue[str] = queue.Queue()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.put(self.format(record))
        except Exception:
            self.handleError(record)


class ActivityView(ttk.Frame):
    def __init__(self, master, translate: Callable[..., str]) -> None:
        super().__init__(master, style="Inspector.TFrame", padding=10)
        self.t = translate
        self.tree = ttk.Treeview(self, columns=("step", "action", "detail"), show="headings", selectmode="browse")
        self.tree.heading("step", text=self.t("step"))
        self.tree.heading("action", text=self.t("action"))
        self.tree.heading("detail", text=self.t("detail"))
        self.tree.column("step", width=46, stretch=False, anchor="center")
        self.tree.column("action", width=82, stretch=False)
        self.tree.column("detail", width=150)
        scroll = ttk.Scrollbar(self, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def append(self, action: dict, step: int) -> None:
        action_type = str(action.get("type", "action"))
        detail = self._detail(action)
        self.tree.insert("", tk.END, values=(step, action_type, detail))
        children = self.tree.get_children()
        if len(children) > 1000:
            self.tree.delete(*children[:200])
        self.tree.yview_moveto(1.0)

    @staticmethod
    def _detail(action: dict) -> str:
        action_type = action.get("type", "")
        if action_type in {"click", "double_click", "tap"}:
            return f"({action.get('x', '?')}, {action.get('y', '?')})"
        if action_type == "type":
            return str(action.get("text", ""))[:100]
        if action_type in {"wait", "listen_audio"}:
            return str(action.get("reason") or action.get("question") or action.get("seconds", ""))[:100]
        if action_type == "scroll":
            return f"{action.get('direction', '')} {action.get('amount', '')}".strip()
        if action_type == "observation_note":
            return str(action.get("text", ""))[:100]
        if action_type == "blocked_click":
            return str(action.get("reason", ""))[:100]
        return str({k: v for k, v in action.items() if k != "type"})[:120]

    def clear(self) -> None:
        self.tree.delete(*self.tree.get_children())

    def update_texts(self) -> None:
        self.tree.heading("step", text=self.t("step"))
        self.tree.heading("action", text=self.t("action"))
        self.tree.heading("detail", text=self.t("detail"))


class ChatView(ttk.Frame):
    def __init__(self, master, translate: Callable[..., str], font_size: int) -> None:
        super().__init__(master, style="Inspector.TFrame", padding=10)
        self.t = translate
        toolbar = ttk.Frame(self, style="Inspector.TFrame")
        toolbar.pack(fill=tk.X, pady=(0, 8))
        self.copy_button = ttk.Button(toolbar, text=self.t("copy"), style="Compact.TButton", command=self.copy_all)
        self.copy_button.pack(side=tk.RIGHT)
        self.clear_button = ttk.Button(toolbar, text=self.t("clear"), style="Compact.TButton", command=self.clear)
        self.clear_button.pack(side=tk.RIGHT, padx=(0, 6))
        body = ttk.Frame(self, style="Inspector.TFrame")
        body.pack(fill=tk.BOTH, expand=True)
        self.text = tk.Text(body, width=30, wrap="word", state="disabled", **text_widget_options(font_size))
        scroll = ttk.Scrollbar(body, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def append(self, text: str, step: int = 0) -> None:
        self.text.configure(state="normal")
        if self.text.index("end-1c") != "1.0":
            self.text.insert(tk.END, "\n\n")
        prefix = f"[{step}]  " if step else ""
        self.text.insert(tk.END, prefix + text.strip())
        self.text.configure(state="disabled")
        self.text.see(tk.END)

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", tk.END)
        self.text.configure(state="disabled")

    def copy_all(self) -> None:
        value = self.text.get("1.0", "end-1c")
        if value:
            self.clipboard_clear()
            self.clipboard_append(value)

    def update_texts(self) -> None:
        self.copy_button.configure(text=self.t("copy"))
        self.clear_button.configure(text=self.t("clear"))


class ZoneView(ttk.Frame):
    def __init__(self, master, translate: Callable[..., str], on_change: Callable[[list[dict], bool], None]) -> None:
        super().__init__(master, style="Inspector.TFrame", padding=10)
        self.t = translate
        self.on_change = on_change
        self.data = get_forbidden_zone_settings()
        self.presets: dict[str, list[dict]] = {
            str(name): list(rects) for name, rects in self.data.get("presets", {}).items() if isinstance(rects, list)
        }
        self.current: list[dict] = []
        self.preset_var = tk.StringVar(value=self.data.get("selected", ""))
        self.draw_var = tk.BooleanVar(value=False)

        ttk.Label(self, text=self.t("preset"), style="Muted.TLabel").pack(anchor="w")
        row = ttk.Frame(self, style="Inspector.TFrame")
        row.pack(fill=tk.X, pady=(4, 8))
        self.combo = ttk.Combobox(row, textvariable=self.preset_var, state="readonly")
        self.combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.combo.bind("<<ComboboxSelected>>", lambda _event: self._load_selected())
        self.new_button = ttk.Button(row, text=self.t("new"), style="Compact.TButton", command=self.new_preset)
        self.new_button.pack(side=tk.LEFT, padx=(6, 0))

        actions = ttk.Frame(self, style="Inspector.TFrame")
        actions.pack(fill=tk.X, pady=(0, 8))
        self.save_button = ttk.Button(actions, text=self.t("save"), style="Compact.TButton", command=self.save_current)
        self.save_button.pack(side=tk.LEFT)
        self.delete_button = ttk.Button(actions, text=self.t("delete"), style="Danger.TButton", command=self.delete_preset)
        self.delete_button.pack(side=tk.LEFT, padx=(6, 0))
        self.clear_button = ttk.Button(actions, text=self.t("clear"), style="Compact.TButton", command=self.clear_zones)
        self.clear_button.pack(side=tk.LEFT, padx=(6, 0))

        self.draw_check = ttk.Checkbutton(self, text=self.t("draw"), variable=self.draw_var, command=self._emit)
        self.draw_check.pack(anchor="w", pady=(4, 4))
        self.info_var = tk.StringVar()
        ttk.Label(self, textvariable=self.info_var, style="Muted.TLabel", wraplength=280).pack(anchor="w", fill=tk.X)
        self._refresh_combo()
        self._load_selected()

    def _refresh_combo(self) -> None:
        self.combo.configure(values=sorted(self.presets))

    def _load_selected(self) -> None:
        self.current = list(self.presets.get(self.preset_var.get(), []))
        self._emit()

    def add_zone(self, zone: dict) -> None:
        self.current.append(dict(zone))
        self._emit()

    def current_zones(self) -> list[dict]:
        return list(self.current)

    def new_preset(self) -> None:
        name = simpledialog.askstring(self.t("new_preset_name"), self.t("enter_name"), parent=self.winfo_toplevel())
        if not name:
            return
        name = name.strip()
        if not name:
            return
        self.presets.setdefault(name, [])
        self.preset_var.set(name)
        self.current = list(self.presets[name])
        self._refresh_combo()
        self.save_current()

    def save_current(self) -> None:
        name = self.preset_var.get().strip()
        if not name:
            self.new_preset()
            return
        self.presets[name] = list(self.current)
        self._save_all()
        self._emit()

    def delete_preset(self) -> None:
        name = self.preset_var.get().strip()
        if not name or not messagebox.askyesno(self.t("delete"), self.t("confirm_delete"), parent=self.winfo_toplevel()):
            return
        self.presets.pop(name, None)
        next_name = sorted(self.presets)[0] if self.presets else ""
        self.preset_var.set(next_name)
        self.current = list(self.presets.get(next_name, []))
        self._refresh_combo()
        self._save_all()
        self._emit()

    def clear_zones(self) -> None:
        self.current.clear()
        self._emit()

    def _save_all(self) -> None:
        settings = load_settings()
        settings["forbidden_zones"] = {"selected": self.preset_var.get(), "presets": self.presets}
        save_settings(settings)

    def _emit(self) -> None:
        self.info_var.set(self.t("zone_count", count=len(self.current)))
        self.on_change(list(self.current), self.draw_var.get())

    def update_texts(self) -> None:
        self.new_button.configure(text=self.t("new"))
        self.save_button.configure(text=self.t("save"))
        self.delete_button.configure(text=self.t("delete"))
        self.clear_button.configure(text=self.t("clear"))
        self.draw_check.configure(text=self.t("draw"))
        self._emit()


class HistoryView(ttk.Frame):
    def __init__(self, master, translate: Callable[..., str], font_size: int) -> None:
        super().__init__(master, style="App.TFrame", padding=16)
        self.t = translate
        self.records: list[dict] = []
        self._photo: Optional[ImageTk.PhotoImage] = None
        header = ttk.Frame(self, style="App.TFrame")
        header.pack(fill=tk.X, pady=(0, 12))
        self.title_label = ttk.Label(header, text=self.t("history_records"), style="Heading.TLabel")
        self.title_label.pack(side=tk.LEFT)
        self.refresh_button = ttk.Button(header, text=self.t("refresh"), style="Compact.TButton", command=self.reload)
        self.refresh_button.pack(side=tk.RIGHT)
        self.delete_button = ttk.Button(header, text=self.t("delete_record"), style="Danger.TButton", command=self.delete_selected)
        self.delete_button.pack(side=tk.RIGHT, padx=(0, 6))

        pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True)
        left = ttk.Frame(pane, style="App.TFrame", width=520)
        right = ttk.Frame(pane, style="App.TFrame", width=650)
        pane.add(left, weight=4)
        pane.add(right, weight=6)

        self.tree = ttk.Treeview(left, columns=("time", "status", "backend", "task"), show="headings", selectmode="browse")
        for key, width in (("time", 145), ("status", 75), ("backend", 110), ("task", 260)):
            self.tree.heading(key, text=self.t(key if key != "backend" else "backend"))
            self.tree.column(key, width=width, stretch=key == "task")
        scroll = ttk.Scrollbar(left, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._show_selected())

        self.detail = tk.Text(right, height=12, wrap="word", state="disabled", **text_widget_options(font_size))
        self.detail.pack(fill=tk.X, pady=(0, 10))
        bottom = ttk.PanedWindow(right, orient=tk.HORIZONTAL)
        bottom.pack(fill=tk.BOTH, expand=True)
        self.shot_list = tk.Listbox(bottom, width=34, background=COLORS["surface"], foreground=COLORS["text"], selectbackground=COLORS["accent_dark"], highlightthickness=1, highlightbackground=COLORS["border"], relief="flat", font=(MONO_FONT, max(8, font_size - 1)))
        self.shot_list.bind("<<ListboxSelect>>", lambda _event: self._load_selected_shot())
        self.shot_canvas = tk.Canvas(bottom, background=COLORS["bg"], highlightthickness=1, highlightbackground=COLORS["border"])
        bottom.add(self.shot_list, weight=2)
        bottom.add(self.shot_canvas, weight=5)
        self.shot_canvas.bind("<Configure>", lambda _event: self._load_selected_shot())
        self.reload()

    def reload(self) -> None:
        from auto_click.history import load_task_history

        self.records = list(reversed(load_task_history(limit=500)))
        self.tree.delete(*self.tree.get_children())
        for index, record in enumerate(self.records):
            status = self.t("success") if record.get("success") else self.t("failed")
            task = str(record.get("task", "")).replace("\n", " ")
            self.tree.insert("", tk.END, iid=str(index), values=(record.get("time", ""), status, record.get("backend", ""), task[:140]))
        if self.records:
            self.tree.selection_set("0")
            self._show_selected()
        else:
            self._show_detail(self.t("no_history"))
            self.shot_list.delete(0, tk.END)
            self.shot_canvas.delete("all")

    def _selected_record(self) -> Optional[dict]:
        selected = self.tree.selection()
        if not selected:
            return None
        try:
            return self.records[int(selected[0])]
        except (IndexError, ValueError):
            return None

    def _show_selected(self) -> None:
        record = self._selected_record()
        if record is None:
            return
        lines = [
            f"{self.t('time')}: {record.get('time', '')}",
            f"{self.t('status')}: {self.t('success') if record.get('success') else self.t('failed')}",
            f"{self.t('backend')}: {record.get('backend', '')}",
            f"{self.t('model')}: {record.get('model', '')}",
            "",
            f"{self.t('task')}:\n{record.get('task', '')}",
            "",
            f"{self.t('result')}:\n{record.get('message', '')}",
        ]
        chat = record.get("chat_messages") or []
        if chat:
            lines.extend(["", f"{self.t('chat_output')}:\n" + "\n\n".join(map(str, chat))])
        self._show_detail("\n".join(lines))
        self.shot_list.delete(0, tk.END)
        for path in record.get("screenshots") or []:
            self.shot_list.insert(tk.END, str(path))
        if self.shot_list.size():
            self.shot_list.selection_set(0)
            self._load_selected_shot()
        else:
            self.shot_canvas.delete("all")

    def _show_detail(self, value: str) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", tk.END)
        self.detail.insert("1.0", value)
        self.detail.configure(state="disabled")

    def _load_selected_shot(self) -> None:
        selected = self.shot_list.curselection()
        if not selected:
            return
        path = Path(self.shot_list.get(selected[0]))
        self.shot_canvas.delete("all")
        try:
            image = Image.open(path).convert("RGB")
        except OSError:
            return
        cw, ch = max(100, self.shot_canvas.winfo_width()), max(100, self.shot_canvas.winfo_height())
        image.thumbnail((cw - 16, ch - 16), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(image)
        self.shot_canvas.create_image(cw // 2, ch // 2, image=self._photo)

    def delete_selected(self) -> None:
        record = self._selected_record()
        if record is None or not messagebox.askyesno(self.t("delete_record"), self.t("confirm_delete"), parent=self.winfo_toplevel()):
            return
        from auto_click.history import delete_task_history

        delete_task_history(record_id=str(record.get("id", "")), index=record.get("_index"))
        self.reload()

    def update_texts(self) -> None:
        self.title_label.configure(text=self.t("history_records"))
        self.refresh_button.configure(text=self.t("refresh"))
        self.delete_button.configure(text=self.t("delete_record"))
        for key in ("time", "status", "backend", "task"):
            self.tree.heading(key, text=self.t(key))
        self.reload()


class SkillsView(ttk.Frame):
    def __init__(self, master, translate: Callable[..., str], font_size: int) -> None:
        super().__init__(master, style="App.TFrame", padding=16)
        self.t = translate
        self.skills_dir = Path(config.BASE_DIR) / "skills"
        self.skills_dir.mkdir(exist_ok=True)
        self.paths: dict[str, Path] = {}
        self.forced = set(get_skill_settings().get("forced", []))

        header = ttk.Frame(self, style="App.TFrame")
        header.pack(fill=tk.X, pady=(0, 12))
        self.title_label = ttk.Label(header, text=self.t("skill_library"), style="Heading.TLabel")
        self.title_label.pack(side=tk.LEFT)
        self.save_button = ttk.Button(header, text=self.t("save_changes"), style="Accent.TButton", command=self.save_selected)
        self.save_button.pack(side=tk.RIGHT)
        self.delete_button = ttk.Button(header, text=self.t("delete_skill"), style="Danger.TButton", command=self.delete_selected)
        self.delete_button.pack(side=tk.RIGHT, padx=(0, 6))
        self.copy_button = ttk.Button(header, text=self.t("copy_skill"), command=self.copy_selected)
        self.copy_button.pack(side=tk.RIGHT, padx=(0, 6))
        self.new_button = ttk.Button(header, text=self.t("new_skill"), command=self.new_skill)
        self.new_button.pack(side=tk.RIGHT, padx=(0, 6))

        pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True)
        left = ttk.Frame(pane, style="App.TFrame", width=280)
        right = ttk.Frame(pane, style="App.TFrame", width=800)
        pane.add(left, weight=2)
        pane.add(right, weight=7)
        self.listbox = tk.Listbox(left, background=COLORS["surface"], foreground=COLORS["text"], selectbackground=COLORS["accent_dark"], highlightthickness=1, highlightbackground=COLORS["border"], relief="flat", font=("Segoe UI", font_size))
        self.listbox.pack(fill=tk.BOTH, expand=True)
        self.listbox.bind("<<ListboxSelect>>", lambda _event: self.load_selected())
        self.force_var = tk.BooleanVar(value=False)
        self.force_check = ttk.Checkbutton(left, text=self.t("force_skill"), variable=self.force_var, command=self._toggle_forced)
        self.force_check.pack(anchor="w", pady=(10, 0))

        editor_frame = ttk.Frame(right, style="App.TFrame")
        editor_frame.pack(fill=tk.BOTH, expand=True)
        self.editor = tk.Text(editor_frame, wrap="word", undo=True, **text_widget_options(font_size, mono=True))
        scroll = ttk.Scrollbar(editor_frame, command=self.editor.yview)
        self.editor.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.status_var = tk.StringVar(value=self.t("no_skill"))
        ttk.Label(right, textvariable=self.status_var, style="Muted.TLabel").pack(fill=tk.X, pady=(8, 0))
        self.reload()

    def reload(self, select: str = "") -> None:
        self.paths = {path.name: path for path in sorted(self.skills_dir.glob("*.md"), key=lambda p: p.name.lower())}
        self.listbox.delete(0, tk.END)
        for name in self.paths:
            marker = "[x] " if name in self.forced else "[ ] "
            self.listbox.insert(tk.END, marker + name)
        if self.paths:
            names = list(self.paths)
            index = names.index(select) if select in names else 0
            self.listbox.selection_set(index)
            self.listbox.see(index)
            self.load_selected()

    def _selected_name(self) -> str:
        selected = self.listbox.curselection()
        if not selected:
            return ""
        return re.sub(r"^\[[ x]\]\s+", "", self.listbox.get(selected[0]))

    def load_selected(self) -> None:
        name = self._selected_name()
        path = self.paths.get(name)
        if path is None:
            return
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror(self.t("skills"), str(exc), parent=self.winfo_toplevel())
            return
        self.editor.delete("1.0", tk.END)
        self.editor.insert("1.0", content)
        self.force_var.set(name in self.forced)
        self.status_var.set(self.t("editing", name=name))

    def save_selected(self) -> None:
        name = self._selected_name()
        path = self.paths.get(name)
        if path is None:
            return
        path.write_text(self.editor.get("1.0", "end-1c").rstrip() + "\n", encoding="utf-8")
        self.status_var.set(self.t("saved", name=name))

    def new_skill(self) -> None:
        name = simpledialog.askstring(self.t("new_skill"), self.t("new_skill_name"), parent=self.winfo_toplevel())
        if not name:
            return
        filename = self._safe_filename(name)
        path = self.skills_dir / filename
        counter = 2
        while path.exists():
            path = self.skills_dir / f"{Path(filename).stem}-{counter}.md"
            counter += 1
        title = path.stem.replace("-", " ").strip().title() or "New Skill"
        path.write_text(f"# {title}\n\nDescribe when and how the model should use this skill.\n", encoding="utf-8")
        self.reload(path.name)

    def copy_selected(self) -> None:
        source = self.paths.get(self._selected_name())
        if source is None:
            return
        target = source.with_name(f"{source.stem}-copy{source.suffix}")
        counter = 2
        while target.exists():
            target = source.with_name(f"{source.stem}-copy-{counter}{source.suffix}")
            counter += 1
        shutil.copy2(source, target)
        self.reload(target.name)

    def delete_selected(self) -> None:
        name = self._selected_name()
        path = self.paths.get(name)
        if path is None or not messagebox.askyesno(self.t("delete_skill"), self.t("confirm_delete"), parent=self.winfo_toplevel()):
            return
        path.unlink()
        self.forced.discard(name)
        update_forced_skills(sorted(self.forced))
        self.editor.delete("1.0", tk.END)
        self.reload()

    def _toggle_forced(self) -> None:
        name = self._selected_name()
        if not name:
            return
        if self.force_var.get():
            self.forced.add(name)
        else:
            self.forced.discard(name)
        update_forced_skills(sorted(self.forced))
        self.reload(name)

    @staticmethod
    def _safe_filename(value: str) -> str:
        stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", value.strip()).strip("-.") or "new-skill"
        return stem if stem.lower().endswith(".md") else stem + ".md"

    def update_texts(self) -> None:
        self.title_label.configure(text=self.t("skill_library"))
        self.save_button.configure(text=self.t("save_changes"))
        self.delete_button.configure(text=self.t("delete_skill"))
        self.copy_button.configure(text=self.t("copy_skill"))
        self.new_button.configure(text=self.t("new_skill"))
        self.force_check.configure(text=self.t("force_skill"))


class LogsView(ttk.Frame):
    MAX_LINES = 5000

    def __init__(self, master, translate: Callable[..., str], handler: UILogHandler, font_size: int) -> None:
        super().__init__(master, style="App.TFrame", padding=16)
        self.t = translate
        self.handler = handler
        self.lines: list[str] = []
        header = ttk.Frame(self, style="App.TFrame")
        header.pack(fill=tk.X, pady=(0, 12))
        self.title_label = ttk.Label(header, text=self.t("run_log"), style="Heading.TLabel")
        self.title_label.pack(side=tk.LEFT)
        self.clear_button = ttk.Button(header, text=self.t("clear"), style="Compact.TButton", command=self.clear)
        self.clear_button.pack(side=tk.RIGHT)

        toolbar = ttk.Frame(self, style="App.TFrame")
        toolbar.pack(fill=tk.X, pady=(0, 8))
        self.level_label = ttk.Label(toolbar, text=self.t("level"), style="Muted.TLabel")
        self.level_label.pack(side=tk.LEFT)
        self.level_var = tk.StringVar(value="ALL")
        level = ttk.Combobox(toolbar, textvariable=self.level_var, values=["ALL", "DEBUG", "INFO", "WARNING", "ERROR"], state="readonly", width=10)
        level.pack(side=tk.LEFT, padx=(6, 14))
        level.bind("<<ComboboxSelected>>", lambda _event: self.render())
        self.preset_label = ttk.Label(toolbar, text=self.t("log_preset"), style="Muted.TLabel")
        self.preset_label.pack(side=tk.LEFT)
        self.preset_var = tk.StringVar(value=self.t("all"))
        self.preset = ttk.Combobox(toolbar, textvariable=self.preset_var, state="readonly", width=18)
        self.preset.pack(side=tk.LEFT, padx=(6, 14))
        self.preset.bind("<<ComboboxSelected>>", lambda _event: self._apply_preset())
        self.filter_label = ttk.Label(toolbar, text=self.t("filter"), style="Muted.TLabel")
        self.filter_label.pack(side=tk.LEFT)
        self.filter_var = tk.StringVar()
        entry = ttk.Entry(toolbar, textvariable=self.filter_var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))
        self.filter_var.trace_add("write", lambda *_: self.render())

        body = ttk.Frame(self, style="App.TFrame")
        body.pack(fill=tk.BOTH, expand=True)
        self.text = tk.Text(body, wrap="none", state="disabled", **text_widget_options(font_size, mono=True))
        yscroll = ttk.Scrollbar(body, command=self.text.yview)
        xscroll = ttk.Scrollbar(body, orient=tk.HORIZONTAL, command=self.text.xview)
        self.text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        xscroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.text.pack(fill=tk.BOTH, expand=True)
        self.update_texts()
        self.after(150, self._drain)

    def _presets(self) -> dict[str, str]:
        return {
            self.t("all"): "",
            self.t("sensevoice"): "(realtime sensevoice):",
            self.t("click_coords"): "__click__",
            self.t("vlm_responses"): "VLM response",
            self.t("adb_actions"): "Executing adb action",
        }

    def _apply_preset(self) -> None:
        self.filter_var.set(self._presets().get(self.preset_var.get(), ""))

    def _drain(self) -> None:
        changed = False
        while True:
            try:
                line = self.handler.records.get_nowait()
            except queue.Empty:
                break
            self.lines.append(line)
            changed = True
        if len(self.lines) > self.MAX_LINES:
            self.lines = self.lines[-self.MAX_LINES:]
        if changed:
            self.render()
        self.after(150, self._drain)

    def _matches(self, line: str) -> bool:
        level = self.level_var.get()
        if level != "ALL" and f"[{level}]" not in line:
            return False
        needle = self.filter_var.get().strip()
        if not needle:
            return True
        if needle == "__click__":
            return bool(re.search(r"\bclick\b|Executing adb action: .*'type': 'click'|\(\d+,\s*\d+\)", line, re.I))
        return needle.lower() in line.lower()

    def render(self) -> None:
        value = "\n".join(line for line in self.lines if self._matches(line))
        self.text.configure(state="normal")
        self.text.delete("1.0", tk.END)
        if value:
            self.text.insert("1.0", value + "\n")
        self.text.configure(state="disabled")
        self.text.see(tk.END)

    def clear(self) -> None:
        self.lines.clear()
        self.render()

    def update_texts(self) -> None:
        self.title_label.configure(text=self.t("run_log"))
        self.clear_button.configure(text=self.t("clear"))
        self.level_label.configure(text=self.t("level"))
        self.preset_label.configure(text=self.t("log_preset"))
        self.filter_label.configure(text=self.t("filter"))
        values = list(self._presets())
        self.preset.configure(values=values)
        if self.preset_var.get() not in values:
            self.preset_var.set(values[0])
