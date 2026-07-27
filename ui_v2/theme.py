"""Graphite product theme for the redesigned Tk interface."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


COLORS = {
    "bg": "#0B0D10",
    "nav": "#0E1115",
    "surface": "#12161B",
    "surface_2": "#181D23",
    "surface_3": "#20262E",
    "border": "#2A323B",
    "text": "#E8EDF2",
    "muted": "#9AA5B1",
    "faint": "#697582",
    "accent": "#35B8AC",
    "accent_hover": "#45C7BB",
    "accent_dark": "#173E3B",
    "info": "#6EA8FE",
    "success": "#53B987",
    "warning": "#D9A441",
    "error": "#E06C75",
}

UI_FONT = "Segoe UI"
MONO_FONT = "Cascadia Mono"


def apply_theme(root: tk.Misc, font_size: int = 10) -> ttk.Style:
    """Apply a deterministic ttk theme without relying on the legacy UI theme."""
    style = ttk.Style(root)
    style.theme_use("clam")
    base = max(9, min(16, int(font_size)))

    root.configure(background=COLORS["bg"])
    root.option_add("*Font", (UI_FONT, base))
    root.option_add("*Menu.background", COLORS["surface"])
    root.option_add("*Menu.foreground", COLORS["text"])
    root.option_add("*Menu.activeBackground", COLORS["surface_3"])
    root.option_add("*Menu.activeForeground", COLORS["text"])

    style.configure(".", background=COLORS["surface"], foreground=COLORS["text"], font=(UI_FONT, base))
    style.configure("TFrame", background=COLORS["surface"])
    style.configure("App.TFrame", background=COLORS["bg"])
    style.configure("Nav.TFrame", background=COLORS["nav"])
    style.configure("Header.TFrame", background=COLORS["surface"])
    style.configure("Inspector.TFrame", background=COLORS["surface_2"])
    style.configure("TLabel", background=COLORS["surface"], foreground=COLORS["text"])
    style.configure("Nav.TLabel", background=COLORS["nav"], foreground=COLORS["text"])
    style.configure("Heading.TLabel", font=(UI_FONT, base + 1, "bold"))
    style.configure("Title.TLabel", background=COLORS["nav"], font=(UI_FONT, base + 2, "bold"))
    style.configure("Muted.TLabel", foreground=COLORS["muted"])
    style.configure("NavMuted.TLabel", background=COLORS["nav"], foreground=COLORS["muted"])
    style.configure("Success.TLabel", foreground=COLORS["success"])
    style.configure("Warning.TLabel", foreground=COLORS["warning"])
    style.configure("Error.TLabel", foreground=COLORS["error"])
    style.configure("Status.TLabel", background=COLORS["nav"], foreground=COLORS["muted"], font=(UI_FONT, max(8, base - 1)))

    style.configure(
        "TButton", background=COLORS["surface_3"], foreground=COLORS["text"],
        bordercolor=COLORS["border"], lightcolor=COLORS["surface_3"],
        darkcolor=COLORS["surface_3"], padding=(10, 7), relief="flat",
    )
    style.map(
        "TButton",
        background=[("pressed", COLORS["border"]), ("active", "#29313A"), ("disabled", COLORS["surface_2"])],
        foreground=[("disabled", COLORS["faint"])],
        bordercolor=[("focus", COLORS["accent"])],
    )
    style.configure("Compact.TButton", padding=(8, 4))
    style.configure("Accent.TButton", background=COLORS["accent"], foreground="#071310", bordercolor=COLORS["accent"], font=(UI_FONT, base, "bold"))
    style.map("Accent.TButton", background=[("active", COLORS["accent_hover"]), ("pressed", "#2F9E95"), ("disabled", "#275B57")])
    style.configure("Danger.TButton", background="#3B2328", foreground="#F4C8CC", bordercolor="#6E343D")
    style.map("Danger.TButton", background=[("active", "#503038"), ("pressed", "#2D1B1F")])
    style.configure("Nav.TButton", background=COLORS["nav"], foreground=COLORS["muted"], bordercolor=COLORS["nav"], anchor="w", padding=(14, 10))
    style.map("Nav.TButton", background=[("active", COLORS["surface_2"])], foreground=[("active", COLORS["text"])])
    style.configure("NavActive.TButton", background=COLORS["accent_dark"], foreground=COLORS["text"], bordercolor=COLORS["accent_dark"], anchor="w", padding=(14, 10), font=(UI_FONT, base, "bold"))
    style.configure("Segment.TButton", background=COLORS["surface_2"], foreground=COLORS["muted"], bordercolor=COLORS["border"], padding=(12, 6))
    style.configure("SegmentActive.TButton", background=COLORS["accent_dark"], foreground=COLORS["accent_hover"], bordercolor=COLORS["accent"], padding=(12, 6), font=(UI_FONT, base, "bold"))

    field_options = dict(fieldbackground=COLORS["surface_2"], foreground=COLORS["text"], bordercolor=COLORS["border"], insertcolor=COLORS["text"], padding=6)
    style.configure("TEntry", **field_options)
    style.configure("TCombobox", **field_options, arrowcolor=COLORS["muted"])
    style.map("TCombobox", fieldbackground=[("readonly", COLORS["surface_2"])], selectbackground=[("readonly", COLORS["surface_2"])], selectforeground=[("readonly", COLORS["text"])])
    style.configure("TSpinbox", **field_options, arrowcolor=COLORS["muted"])
    style.configure("TCheckbutton", background=COLORS["surface"], foreground=COLORS["text"], indicatorbackground=COLORS["surface_2"], indicatorforeground=COLORS["accent"], padding=(0, 3))
    style.map("TCheckbutton", background=[("active", COLORS["surface"])] , indicatorbackground=[("selected", COLORS["accent_dark"]), ("active", COLORS["surface_3"])])

    style.configure("TSeparator", background=COLORS["border"])
    style.configure("TPanedwindow", background=COLORS["border"], sashwidth=5, sashrelief="flat")
    style.configure("TNotebook", background=COLORS["surface_2"], borderwidth=0)
    style.configure("TNotebook.Tab", background=COLORS["surface_2"], foreground=COLORS["muted"], padding=(12, 8), borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", COLORS["surface_3"]), ("active", COLORS["surface_3"])], foreground=[("selected", COLORS["text"])])
    style.configure("Treeview", background=COLORS["surface"], fieldbackground=COLORS["surface"], foreground=COLORS["text"], bordercolor=COLORS["border"], rowheight=base * 2 + 8)
    style.map("Treeview", background=[("selected", COLORS["accent_dark"])], foreground=[("selected", COLORS["text"])])
    style.configure("Treeview.Heading", background=COLORS["surface_2"], foreground=COLORS["muted"], bordercolor=COLORS["border"], font=(UI_FONT, base, "bold"), padding=(8, 6))
    style.map("Treeview.Heading", background=[("active", COLORS["surface_3"])])
    style.configure("Vertical.TScrollbar", background=COLORS["surface_3"], troughcolor=COLORS["surface"], bordercolor=COLORS["surface"])
    style.configure("Horizontal.TScrollbar", background=COLORS["surface_3"], troughcolor=COLORS["surface"], bordercolor=COLORS["surface"])
    style.configure("TProgressbar", background=COLORS["accent"], troughcolor=COLORS["surface_2"], bordercolor=COLORS["surface_2"])
    return style


def text_widget_options(font_size: int = 10, mono: bool = False) -> dict[str, object]:
    return {
        "background": COLORS["surface"],
        "foreground": COLORS["text"],
        "insertbackground": COLORS["text"],
        "selectbackground": COLORS["accent_dark"],
        "selectforeground": COLORS["text"],
        "highlightbackground": COLORS["border"],
        "highlightcolor": COLORS["accent"],
        "highlightthickness": 1,
        "relief": "flat",
        "font": (MONO_FONT if mono else UI_FONT, font_size),
    }
