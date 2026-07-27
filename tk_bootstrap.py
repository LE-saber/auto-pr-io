"""Bootstrap Tcl/Tk paths before tkinter is imported."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def configure_tk_runtime() -> None:
    """Point tkinter at a usable Tcl/Tk runtime.

    Some Windows setups have another Tcl DLL earlier on PATH or a Python install
    whose Tcl library cannot be resolved from its original C: path. Prefer the
    active Python runtime first so a separate Python 3.10-3.12 venv does not load
    a mismatched project-local Tcl patch version.
    """
    runtime_dir = Path(__file__).resolve().parent / ".runtime"
    bundled_tcl = runtime_dir / "tcl"
    bundled_tcl_8614 = runtime_dir / "tcl-8.6.14"
    python_tcl_candidates = [
        Path(sys.base_prefix) / "Library" / "lib",
        Path(sys.base_prefix) / "tcl",
    ]
    bundled_candidates = (
        [bundled_tcl]
        if sys.version_info >= (3, 13)
        else [bundled_tcl_8614, bundled_tcl]
    )
    candidates = [*python_tcl_candidates, *bundled_candidates]
    selected_base = None
    for base in candidates:
        tcl_dir = base / "tcl8.6"
        tk_dir = base / "tk8.6"
        if (tcl_dir / "init.tcl").exists() and tk_dir.exists():
            os.environ["TCL_LIBRARY"] = tcl_dir.as_posix()
            os.environ["TK_LIBRARY"] = tk_dir.as_posix()
            selected_base = base
            break

    dll_dirs = [
        selected_base / "bin" if selected_base else None,
        Path(sys.base_prefix) / "Library" / "bin",
        Path(sys.base_prefix) / "DLLs",
        Path(sys.base_prefix),
    ]
    existing_dll_dirs = [dll_dir for dll_dir in dll_dirs if dll_dir and dll_dir.exists()]
    if existing_dll_dirs:
        os.environ["PATH"] = (
            os.pathsep.join(str(dll_dir) for dll_dir in existing_dll_dirs)
            + os.pathsep
            + os.environ.get("PATH", "")
        )
    for dll_dir in existing_dll_dirs:
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(str(dll_dir))
            except OSError:
                pass
