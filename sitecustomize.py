"""Project-local Python startup customizations."""
from __future__ import annotations

try:
    from tk_bootstrap import configure_tk_runtime

    configure_tk_runtime()
except Exception:
    # Never block Python startup; main.py will surface GUI errors if needed.
    pass
