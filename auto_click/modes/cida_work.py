"""CIDA/VocabGo exercise automation profile."""
from __future__ import annotations

from auto_click.modes.profiles import CIDA_WORK_PROFILE

CIDA_BACKEND = CIDA_WORK_PROFILE.backend
CIDA_MAIN_MODEL = CIDA_WORK_PROFILE.main_model
CIDA_FAST_MODEL = CIDA_WORK_PROFILE.fast_model
CIDA_ASR_MODE = CIDA_WORK_PROFILE.asr_mode
CIDA_ASR_MODEL = CIDA_WORK_PROFILE.asr_model


DEFAULT_TASK = CIDA_WORK_PROFILE.default_task


def is_cida_backend(backend: str) -> bool:
    return backend == CIDA_BACKEND


def build_task(task: str) -> str:
    """Add CIDA-specific operating rules to the user task."""
    return CIDA_WORK_PROFILE.build_task(task)
