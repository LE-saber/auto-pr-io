"""Backend adapter used by the redesigned GUI.

The module contains no Tk widgets. It translates product-level GUI choices into
the existing AutoClicker, ADB, history, and settings contracts.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

from auto_click.modes.profiles import backend_profile
from settings_store import (
    get_adb_settings,
    get_audio_settings,
    get_oracle_settings,
    get_provider_settings,
    update_adb_device,
)

logger = logging.getLogger(__name__)


DESKTOP_BACKENDS = {
    "zhipu_desktop": "Zhipu GLM Vision",
    "volcengine_desktop": "ByteDance Doubao Vision",
    "qwen_desktop": "Qwen VL",
}

ANDROID_BACKENDS = {
    "cida_work": "CIDA Work",
    "glm_adb": "GLM Vision · glm-4.6v-flashx",
    "openai_adb": "OpenAI Computer Use",
    "adb_vlm": "Generic VLM coordinates",
    "deepseek_adb": "DeepSeek Vision",
    "autoglm_phone": "AutoGLM-Phone",
}

ADB_BACKENDS = {*ANDROID_BACKENDS, "observe_adb"}


def provider_for_backend(backend: str) -> str:
    desktop_providers = {
        "zhipu_desktop": "zhipu",
        "volcengine_desktop": "volcengine",
        "qwen_desktop": "qwen_vl",
    }
    if backend in desktop_providers:
        return desktop_providers[backend]
    if backend in {"openai", "openai_adb"}:
        return "openai"
    if backend in {"vlm_coords", "adb_vlm"}:
        return "vlm_coords"
    if backend == "glm_adb":
        return "zhipu"
    if backend == "observe_adb":
        return "qwen_vl"
    profile = backend_profile(backend)
    if profile:
        return profile.provider
    if backend == "deepseek_adb":
        return "deepseek_vision"
    return backend


def default_model_for_backend(backend: str) -> str:
    profile = backend_profile(backend)
    if profile:
        return profile.main_model
    fixed = {
        "zhipu_desktop": "glm-4.6v-flashx",
        "volcengine_desktop": "doubao-seed-2-0-lite-260215",
        "qwen_desktop": "qwen3-vl-plus",
        "glm_adb": "glm-4.6v-flashx",
        "deepseek_adb": "deepseek-vl2",
        "observe_adb": "qwen3-vl-plus",
        "autoglm_phone": "autoglm-phone",
        "openai": "gpt-5.5",
        "openai_adb": "gpt-5.5",
        "adb_vlm": "gpt-4o",
        "vlm_coords": "gpt-4o",
    }
    provider = provider_for_backend(backend)
    configured = get_provider_settings(provider).get("model", "")
    return configured or fixed.get(backend, "")


def backend_options(target: str, work_mode: str) -> dict[str, str]:
    if target == "android" and work_mode == "chat":
        return {"observe_adb": "Observe only · Qwen VL"}
    return dict(ANDROID_BACKENDS if target == "android" else DESKTOP_BACKENDS)


@dataclass
class RunRequest:
    target: str
    work_mode: str
    backend: str
    model: str
    task: str
    device_id: str = ""
    screenshot_b64: Optional[str] = None
    desktop_capture: Optional[dict] = None
    max_steps: int = 200
    confirm_actions: bool = False
    audio_enabled: bool = False
    continuous_audio: bool = False
    audio_duration: int = 5
    forbidden_rects: list[dict] = field(default_factory=list)


class BackendBridge:
    """Owns one AutoClicker run and emits thread-safe data events."""

    def __init__(
        self,
        emit: Callable[[str, object], None],
        screenshots: Callable[[], list[str]],
    ) -> None:
        self.emit = emit
        self.screenshots = screenshots
        self.clicker = None
        self.request: Optional[RunRequest] = None
        self.chat_messages: list[str] = []

    @staticmethod
    def scan_devices():
        from auto_click.adb import ADBController

        adb = get_adb_settings()
        return ADBController(adb_path=adb.get("path", "adb")).list_devices()

    @staticmethod
    def enable_keyboard(device_id: str) -> str:
        from auto_click.adb import ADBController

        adb = get_adb_settings()
        controller = ADBController(adb_path=adb.get("path", "adb"), device_id=device_id)
        controller.ensure_ready()
        return controller.ensure_adb_keyboard()

    @staticmethod
    def open_audio_helper(device_id: str) -> None:
        from auto_click.adb import ADBController

        adb = get_adb_settings()
        controller = ADBController(adb_path=adb.get("path", "adb"), device_id=device_id)
        controller.ensure_ready()
        controller._shell(["am", "start", "-n", "com.autopr.keyboardaudio/.MainActivity"])

    def start(self, request: RunRequest) -> None:
        self._validate(request)
        from auto_click.clicker import AutoClicker

        provider = provider_for_backend(request.backend)
        provider_settings = get_provider_settings(provider)
        profile = backend_profile(request.backend)
        audio_settings = get_audio_settings()
        api_key = provider_settings.get("api_key", "")
        api_base = provider_settings.get("api_base", "")
        audio_enabled = bool(profile.force_audio if profile else request.audio_enabled)

        self.request = request
        self.chat_messages.clear()
        if request.device_id:
            update_adb_device(request.device_id)
        adb_settings = get_adb_settings()
        self.clicker = AutoClicker(
            backend=request.backend,
            api_key=api_key or "EMPTY",
            api_base=api_base,
            model=request.model or default_model_for_backend(request.backend),
            desktop_capture=request.desktop_capture,
            adb_path=adb_settings.get("path", "adb"),
            device_id=request.device_id,
            audio_enabled=audio_enabled,
            continuous_audio=bool(audio_enabled and request.continuous_audio),
            whisper_mode="sensevoice_streaming",
            whisper_api_key="",
            whisper_api_base="",
            whisper_api_model="",
            local_whisper_model=audio_settings.get(
                "sensevoice_model",
                profile.asr_model if profile else "iic/SenseVoiceSmall",
            ),
            audio_duration_s=max(1, min(30, int(request.audio_duration))),
            on_audio_status=lambda text: self.emit("audio", text),
            forbidden_rects=list(request.forbidden_rects),
            max_steps=max(1, min(1000, int(request.max_steps))),
            confirm_before_execute=bool(request.confirm_actions),
            on_action=self._on_action,
            on_screenshot=(
                lambda image: self.emit("desktop_image", image)
                if request.target == "desktop"
                else None
            ),
            on_complete=self._on_complete,
            oracle_settings=get_oracle_settings(),
        )
        logger.info(
            "Starting automation backend=%s device=%s",
            request.backend,
            request.device_id or "desktop",
        )
        self.clicker.run_task(request.task, screenshot_b64=request.screenshot_b64)
        self.emit("started", request)

    def stop(self) -> None:
        if self.clicker is not None:
            self.clicker.stop()

    def _validate(self, request: RunRequest) -> None:
        if not request.task.strip():
            raise ValueError("missing_task")
        if request.target == "desktop" and request.backend not in DESKTOP_BACKENDS:
            raise ValueError(f"unsupported_desktop_backend:{request.backend}")
        if request.backend in ADB_BACKENDS and not request.device_id:
            raise ValueError("select_device")
        provider = provider_for_backend(request.backend)
        provider_settings = get_provider_settings(provider)
        api_key = provider_settings.get("api_key", "")
        api_base = provider_settings.get("api_base", "")
        if not api_key and request.backend not in {"vlm_coords", "adb_vlm"}:
            raise ValueError(f"missing_api:{provider}")
        if request.backend in {
            "vlm_coords", "adb_vlm", "glm_adb", "deepseek_adb",
            "cida_work", "observe_adb", *DESKTOP_BACKENDS,
        } and not api_base:
            raise ValueError(f"missing_base:{provider}")

    def _on_action(self, action: dict, step: int) -> None:
        if action.get("type") == "observation_note":
            text = str(action.get("text", "")).strip()
            if text:
                self.chat_messages.append(text)
                self.emit("chat", {"text": text, "step": step})
        self.emit("action", {"action": action, "step": step})

    def _on_complete(self, success: bool, message: str) -> None:
        request = self.request
        if request is not None:
            try:
                from auto_click.history import append_task_history

                append_task_history(
                    {
                        "success": success,
                        "message": message,
                        "backend": request.backend,
                        "model": request.model,
                        "task": request.task,
                        "chat_messages": list(self.chat_messages),
                        "screenshots": self.screenshots(),
                    }
                )
            except Exception:
                logger.debug("Failed to save task history", exc_info=True)
        self.emit("complete", {"success": success, "message": message})
