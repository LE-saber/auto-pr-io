"""VLM-driven screen automation module."""
from .clicker import AutoClicker, BackendType
from .executor import ActionExecutor

__all__ = ["AutoClicker", "BackendType", "ActionExecutor"]
