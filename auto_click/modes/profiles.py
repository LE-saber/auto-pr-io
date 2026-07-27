"""Automation mode registry.

Mode profiles keep task-specific defaults out of the GUI and clicker loop.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModeProfile:
    backend: str
    label: str
    provider: str
    main_model: str
    fast_model: str = ""
    asr_mode: str = ""
    asr_model: str = ""
    target_context: str = "an Android device screen"
    default_task: str = ""
    default_steps: int = 200
    is_adb: bool = True
    normalized_coords: bool = True
    force_audio: bool = False
    skill_name: str = ""
    task_preamble: str = ""

    def build_task(self, task: str) -> str:
        raw_task = (task or "").strip() or self.default_task
        if not self.task_preamble:
            return raw_task
        return f"{self.task_preamble.strip()}\n\nUser task: {raw_task}"


CIDA_WORK_PROFILE = ModeProfile(
    backend="cida_work",
    label="CIDA Work Mode",
    provider="qwen_vl",
    main_model="qwen3-vl-plus",
    fast_model="glm-4.6v-flashx",
    asr_mode="sensevoice_streaming",
    asr_model="iic/SenseVoiceSmall",
    target_context="an Android CIDA/VocabGo exercise screen",
    default_task=(
        "Complete the current CIDA/VocabGo vocabulary exercise. Read the question "
        "format carefully, use audio transcription for listening questions, select "
        "the correct visible answer, and continue until the practice task is done."
    ),
    default_steps=200,
    is_adb=True,
    normalized_coords=True,
    force_audio=True,
    skill_name="cida-work",
    task_preamble=(
        "CIDA_WORK_MODE is active.\n"
        "- Use the cida-work skill as the primary task guide.\n"
        "- Main planner model role: Qwen3-VL-Plus/Qwen3-VL-32B should read the "
        "screen, understand the exercise format, plan the next action, and recover from mistakes.\n"
        "- Fast helper role: GLM-4.6V-FlashX is intended for cheap page-state checks "
        "and simple click loops; keep actions concise and deterministic.\n"
        "- ASR role: local FunASR/SenseVoice handles Chinese/English low-latency "
        "speech-to-text on this machine. Do not assume a cloud speech API. For listening "
        "questions, click play once if needed, then return listen_audio and use the transcript "
        "in the next step.\n"
        "- Do not return done merely because one answer was clicked. Return done only when "
        "the practice flow clearly ends or the requested task is complete."
    ),
)


MODE_PROFILES: dict[str, ModeProfile] = {
    CIDA_WORK_PROFILE.backend: CIDA_WORK_PROFILE,
}

ANDROID_MODE_LABELS = {
    profile.backend: profile.label for profile in MODE_PROFILES.values() if profile.is_adb
}
ADB_MODE_BACKENDS = {profile.backend for profile in MODE_PROFILES.values() if profile.is_adb}
NORMALIZED_MODE_BACKENDS = {
    profile.backend for profile in MODE_PROFILES.values() if profile.normalized_coords
}


def backend_profile(backend: str) -> ModeProfile | None:
    return MODE_PROFILES.get(backend)


def apply_task_profile(backend: str, task: str) -> str:
    profile = backend_profile(backend)
    return profile.build_task(task) if profile else task
