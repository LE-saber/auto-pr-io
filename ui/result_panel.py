"""Task history panel with details, screenshots, and deletion."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageTk


class ResultPanel(ttk.LabelFrame):
    def __init__(self, master, language: str = "zh-CN", **kwargs):
        from ui.i18n import t

        self._language = language
        super().__init__(master, text=t(language, "history_records"), **kwargs)
        self._records: list[dict] = []
        self._last_result = ""
        self._photo = None
        self._build_ui()
        self.reload_history()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1, minsize=230)
        self.columnconfigure(1, weight=2, minsize=300)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=(4, 0))
        from ui.i18n import t

        self._refresh_btn = ttk.Button(toolbar, text=t(self._language, "refresh_history"), command=self.reload_history, width=10)
        self._refresh_btn.pack(side=tk.LEFT, padx=2)
        self._delete_btn = ttk.Button(toolbar, text=t(self._language, "delete_record"), command=self.delete_selected, width=10)
        self._delete_btn.pack(side=tk.LEFT, padx=2)
        self._copy_btn = ttk.Button(toolbar, text=t(self._language, "copy_details"), command=self._copy_last, width=10)
        self._copy_btn.pack(side=tk.LEFT, padx=2)

        left = ttk.Frame(self)
        left.grid(row=1, column=0, sticky="nsew", padx=(4, 2), pady=4)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self._list = tk.Listbox(left, exportselection=False)
        self._list.grid(row=0, column=0, sticky="nsew")
        self._list.bind("<<ListboxSelect>>", self._on_select)
        list_scroll = ttk.Scrollbar(left, command=self._list.yview)
        list_scroll.grid(row=0, column=1, sticky="ns")
        self._list.configure(yscrollcommand=list_scroll.set)

        right = ttk.Frame(self)
        right.grid(row=1, column=1, sticky="nsew", padx=(2, 4), pady=4)
        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=2)
        right.columnconfigure(0, weight=1)

        detail_frame = ttk.Frame(right)
        detail_frame.grid(row=0, column=0, sticky="nsew")
        detail_frame.rowconfigure(0, weight=1)
        detail_frame.columnconfigure(0, weight=1)
        self._text = tk.Text(
            detail_frame,
            wrap="word",
            state="disabled",
            font=("Consolas", 10),
            bg="#0d1117",
            fg="#c9d1d9",
            insertbackground="white",
            relief="flat",
        )
        self._text.grid(row=0, column=0, sticky="nsew")
        text_scroll = ttk.Scrollbar(detail_frame, command=self._text.yview)
        text_scroll.grid(row=0, column=1, sticky="ns")
        self._text.configure(yscrollcommand=text_scroll.set)

        shot = ttk.LabelFrame(right, text=t(self._language, "related_screenshots"))
        self._shot_frame = shot
        shot.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        shot.rowconfigure(0, weight=1)
        shot.columnconfigure(0, weight=1)
        self._shot_label = ttk.Label(shot, anchor="center")
        self._shot_label.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self._shot_var = tk.StringVar()
        self._shot_cb = ttk.Combobox(shot, textvariable=self._shot_var, state="readonly")
        self._shot_cb.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 4))
        self._shot_cb.bind("<<ComboboxSelected>>", self._on_screenshot_selected)

    def reload_history(self) -> None:
        from auto_click.history import load_task_history

        self._records = load_task_history()
        self._list.delete(0, tk.END)
        if not self._records:
            self._show_text(self._t("no_history"))
            self._show_screenshots([])
            return
        for record in reversed(self._records):
            status = self._t("success") if record.get("success") else self._t("failed")
            title = f"{record.get('time', '')} | {status} | {record.get('model') or record.get('backend', '')}"
            self._list.insert(tk.END, title)
        self._list.selection_set(0)
        self._show_record(self._record_for_list_index(0))

    def delete_selected(self) -> None:
        record = self._selected_record()
        if not record:
            return
        if not messagebox.askyesno(self._t("delete_record"), self._t("delete_record") + "?"):
            return
        from auto_click.history import delete_task_history

        delete_task_history(record_id=str(record.get("id", "")), index=record.get("_index"))
        self.reload_history()

    def show_result(self, text: str) -> None:
        self._last_result = text
        self._show_text(text)

    def show_error(self, text: str) -> None:
        self._show_text(f"[ERROR] {text}")

    def clear(self) -> None:
        self._show_text("")

    def _on_select(self, event=None) -> None:
        record = self._selected_record()
        if record:
            self._show_record(record)

    def _selected_record(self) -> dict | None:
        selected = self._list.curselection()
        if not selected:
            return None
        return self._record_for_list_index(selected[0])

    def _record_for_list_index(self, index: int) -> dict:
        return list(reversed(self._records))[index]

    def _show_record(self, record: dict) -> None:
        screenshots = record.get("screenshots") or []
        detail = [
            f"{self._t('time')}: {record.get('time', '')}",
            f"{self._t('status')}: {self._t('success') if record.get('success') else self._t('failed')}",
            f"Backend: {record.get('backend', '')}",
            f"Model: {record.get('model', '')}",
            "",
            f"{self._t('task_question')}:",
            str(record.get("task", "")),
            "",
            f"{self._t('result')}:",
            str(record.get("message", "")),
            "",
            f"{self._t('screenshot_count')}: {len(screenshots)}",
        ]
        self._last_result = "\n".join(detail)
        self._show_text(self._last_result)
        self._show_screenshots(screenshots)

    def _show_text(self, text: str) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", tk.END)
        self._text.insert("1.0", text)
        self._text.configure(state="disabled")

    def _show_screenshots(self, paths: list[str]) -> None:
        existing = [path for path in paths if Path(path).exists()]
        self._shot_cb["values"] = existing
        if existing:
            self._shot_var.set(existing[-1])
            self._load_screenshot(existing[-1])
        else:
            self._shot_var.set("")
            self._photo = None
            self._shot_label.configure(image="", text=self._t("no_screenshots"))

    def _on_screenshot_selected(self, event=None) -> None:
        if self._shot_var.get():
            self._load_screenshot(self._shot_var.get())

    def _load_screenshot(self, path: str) -> None:
        try:
            image = Image.open(path)
            image.thumbnail((520, 260), Image.LANCZOS)
            self._photo = ImageTk.PhotoImage(image)
            self._shot_label.configure(image=self._photo, text="")
        except Exception as exc:
            self._photo = None
            self._shot_label.configure(image="", text=f"Screenshot load failed: {exc}")

    def _copy_last(self) -> None:
        if self._last_result:
            self.clipboard_clear()
            self.clipboard_append(self._last_result)

    def _t(self, key: str) -> str:
        from ui.i18n import t

        return t(self._language, key)

    def set_language(self, language: str) -> None:
        self._language = language
        self.configure(text=self._t("history_records"))
        self._refresh_btn.configure(text=self._t("refresh_history"))
        self._delete_btn.configure(text=self._t("delete_record"))
        self._copy_btn.configure(text=self._t("copy_details"))
        self._shot_frame.configure(text=self._t("related_screenshots"))
        self.reload_history()
