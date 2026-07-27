"""
auto-pr-io — VLM Screen Analyzer
Entry point: python main.py
"""
import sys
import logging

from tk_bootstrap import configure_tk_runtime

configure_tk_runtime()

import tkinter as tk

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("auto-pr-io")


def _configure_windows_dpi() -> None:
    """Keep Tk, MSS, and pyautogui in the same physical-pixel coordinate space."""
    try:
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            from ctypes import windll

            windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main():
    _configure_windows_dpi()
    root = tk.Tk()
    try:
        from config import APP_TITLE, WINDOW_WIDTH, WINDOW_HEIGHT
        root.title(APP_TITLE)
        root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
    except Exception as e:
        logger.warning(f"Config load error: {e}")
        root.title("auto-pr-io")
        root.geometry("1400x850")

    from ui_v2 import MainWindow
    MainWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
