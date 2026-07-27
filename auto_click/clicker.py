"""
AutoClicker — VLM-driven screen automation entry point.

Supports Windows and Android automation backends:
  - "openai"        : OpenAI Computer Use on the Windows desktop
  - "vlm_coords"    : Generic VLM JSON coordinate extraction on Windows
  - "openai_adb"    : OpenAI Computer Use on an Android device through adb
  - "adb_vlm"       : Generic VLM JSON coordinate extraction through adb
  - "autoglm_phone" : Open-AutoGLM phone automation through ADB/HDC
"""
from __future__ import annotations

import base64
import io
import logging
import threading
import time
from typing import Callable, Literal, Optional

import pyautogui
from PIL import Image

from auto_click.modes.profiles import (
    ADB_MODE_BACKENDS,
    NORMALIZED_MODE_BACKENDS,
    apply_task_profile,
    backend_profile,
)

logger = logging.getLogger(__name__)

BackendType = Literal[
    "openai",
    "openai_adb",
    "adb_vlm",
    "glm_adb",
    "deepseek_adb",
    "cida_work",
    "observe_adb",
    "autoglm_phone",
    "anthropic",
    "vlm_coords",
    "zhipu_desktop",
    "volcengine_desktop",
    "qwen_desktop",
]


class AutoClicker:
    """High-level orchestrator for VLM-driven screen automation."""

    def __init__(
        self,
        backend: BackendType = "openai",
        api_key: str = "",
        api_base: str = "",
        model: str = "",
        oracle_settings: Optional[dict] = None,
        display_width: int = 1366,
        display_height: int = 768,
        desktop_capture: Optional[dict] = None,
        adb_path: str = "adb",
        device_id: str = "",
        audio_enabled: bool = False,
        whisper_mode: str = "sensevoice_streaming",
        whisper_api_key: str = "",
        whisper_api_base: str = "",
        whisper_api_model: str = "whisper-1",
        local_whisper_model: str = "iic/SenseVoiceSmall",
        audio_duration_s: int = 5,
        continuous_audio: bool = False,
        on_audio_status: Optional[Callable[[str], None]] = None,
        forbidden_rects: Optional[list[dict]] = None,
        max_steps: int = 20,
        confirm_before_execute: bool = True,
        on_action: Optional[Callable[[dict, int], None]] = None,
        on_screenshot: Optional[Callable[[Image.Image], None]] = None,
        on_complete: Optional[Callable[[bool, str], None]] = None,
    ):
        self.backend_name = backend
        self.api_key = api_key
        self.api_base = api_base
        self.model = model
        self._oracle_settings = oracle_settings or {}
        self.adb_path = adb_path
        self.device_id = device_id
        self.audio_enabled = audio_enabled
        self.whisper_mode = "sensevoice_streaming"
        self.whisper_api_key = whisper_api_key
        self.whisper_api_base = whisper_api_base
        self.whisper_api_model = whisper_api_model
        self.local_whisper_model = local_whisper_model or "iic/SenseVoiceSmall"
        self.audio_duration_s = audio_duration_s
        self.continuous_audio = bool(continuous_audio)
        self.on_audio_status = on_audio_status
        self.forbidden_rects = forbidden_rects or []
        self._forbidden_prompt_rects = self.forbidden_rects
        self._forbidden_prompt_space = "screen pixels"
        try:
            screen_width, screen_height = pyautogui.size()
        except Exception:
            screen_width, screen_height = display_width, display_height
        self.display_width = int(screen_width or display_width)
        self.display_height = int(screen_height or display_height)
        self.desktop_capture = dict(desktop_capture or {})
        self.max_steps = max_steps
        self.confirm_before_execute = confirm_before_execute
        self.on_action = on_action
        self.on_screenshot = on_screenshot
        self.on_complete = on_complete

        self._backend = None
        self._executor = None
        self._adb_controller = None
        self._oracle = None
        self._audio_capture = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._run_lock = threading.Lock()
        self._step_counter = 0
        self._last_click_point: Optional[tuple[int, int]] = None
        self._same_click_count = 0
        self._auto_audio_triggered = False
        self._audio_listen_count = 0
        self._continuous_audio_lock = threading.Lock()
        self._continuous_audio_segments: list[str] = []
        self._vlm_history: list[dict] = []
        self._history_lock = threading.Lock()
        self._asr_speech_active = False
        self._asr_last_text_at = 0.0
        self._asr_gate_started_at = 0.0
        self._asr_silence_timeout_s = 2.0
        self._asr_max_hold_s = 8.0

    def run_task(self, task: str, screenshot_b64: Optional[str] = None,
                 blocking: bool = False) -> None:
        """Start automation for *task* in a background thread (default)."""
        with self._run_lock:
            if self._running:
                logger.warning("AutoClicker already running — ignoring new task")
                return
            self._running = True
        try:
            task = apply_task_profile(self.backend_name, task)
            self._setup_backend()
            if self._oracle is None:
                self._setup_oracle()
            if self.backend_name == "autoglm_phone":
                if blocking:
                    self._run_phone_task(task)
                else:
                    self._thread = threading.Thread(
                        target=self._run_phone_task, args=(task,), daemon=True
                    )
                    self._thread.start()
                return

            self._setup_executor()
            if screenshot_b64 is None or self.desktop_capture:
                screenshot_b64 = self._capture_screenshot_b64()
            if self.backend_name == "observe_adb":
                if blocking:
                    self._run_observe_loop(task, screenshot_b64)
                else:
                    self._thread = threading.Thread(
                        target=self._run_observe_loop, args=(task, screenshot_b64), daemon=True
                    )
                    self._thread.start()
                return
            if blocking:
                self._run_loop(task, screenshot_b64)
            else:
                self._thread = threading.Thread(
                    target=self._run_loop, args=(task, screenshot_b64), daemon=True
                )
                self._thread.start()
        except Exception:
            with self._run_lock:
                self._running = False
            raise

    def stop(self) -> None:
        self._running = False
        if self._audio_capture is not None:
            try:
                self._audio_capture.stop_continuous_transcription()
            except Exception:
                logger.debug("Failed to stop continuous audio", exc_info=True)
        if self._backend is not None and hasattr(self._backend, "stop"):
            self._backend.stop()

    def reset(self) -> None:
        if self._backend is not None:
            self._backend.reset()

    def click_at(self, x: int, y: int, button: str = "left") -> None:
        """Direct click without VLM (simple Phase-1 helper)."""
        pyautogui.click(x, y, button=button)
        logger.info("click_at(%d, %d, %s)", x, y, button)

    # ------------------------------------------------------------------
    def _setup_backend(self):
        if self.backend_name in {"openai", "openai_adb"}:
            from auto_click.backends.openai_cua import OpenAICUABackend
            kw = dict(api_key=self.api_key,
                      api_base=self.api_base,
                      display_width=self.display_width,
                      display_height=self.display_height,
                      target_context=(
                          "Android device screen"
                          if self.backend_name == "openai_adb"
                          else "Windows desktop"
                      ))
            if self.model:
                kw["model"] = self.model
            self._backend = OpenAICUABackend(**kw)
        elif self.backend_name == "autoglm_phone":
            from auto_click.backends.autoglm_phone import AutoGLMPhoneBackend
            self._backend = AutoGLMPhoneBackend(
                api_key=self.api_key,
                api_base=self.api_base,
                model=self.model or "autoglm-phone",
                device_id=self.device_id or None,
                adb_exe=self.adb_path,
                on_action=self.on_action,
            )
        elif self.backend_name == "anthropic":
            from auto_click.backends.anthropic_cu import AnthropicCUBackend
            kw = dict(api_key=self.api_key,
                      display_width=self.display_width,
                      display_height=self.display_height)
            if self.model:
                kw["model"] = self.model
            self._backend = AnthropicCUBackend(**kw)
        elif self.backend_name == "observe_adb":
            from auto_click.backends.observe_only import ObserveOnlyBackend
            if not self.api_base:
                raise ValueError("observe_adb backend requires api_base")
            self._backend = ObserveOnlyBackend(
                api_key=self.api_key,
                api_base=self.api_base,
                model=self.model or "qwen3-vl-plus",
                target_context="an Android phone screen with optional live audio transcription",
            )
        elif self.backend_name in {
            "vlm_coords", "adb_vlm", "glm_adb", "deepseek_adb", "cida_work",
            "zhipu_desktop", "volcengine_desktop", "qwen_desktop",
        }:
            from auto_click.backends.vlm_coords import VLMCoordsBackend
            if not self.api_base:
                raise ValueError(f"{self.backend_name} backend requires api_base")
            profile = backend_profile(self.backend_name)
            desktop_defaults = {
                "zhipu_desktop": "glm-4.6v-flashx",
                "volcengine_desktop": "doubao-seed-2-0-lite-260215",
                "qwen_desktop": "qwen3-vl-plus",
            }
            default_model = (
                profile.main_model
                if profile
                else desktop_defaults.get(self.backend_name, "gpt-4o")
            )
            self._backend = VLMCoordsBackend(
                api_key=self.api_key,
                api_base=self.api_base,
                model=self.model or default_model,
                target_context=(
                    profile.target_context
                    if profile
                    else "an Android device screen"
                    if self.backend_name in {"adb_vlm", "glm_adb", "deepseek_adb"}
                    else "a Windows desktop"
                ),
                coordinate_mode=(
                    "normalized_1000"
                    if self.backend_name in {
                        *self._NORMALIZED_COORD_BACKENDS,
                        "zhipu_desktop",
                        "volcengine_desktop",
                        "qwen_desktop",
                    }
                    else "pixel"
                ),
                normalized_output_to_pixels=self.backend_name in {
                    "zhipu_desktop",
                    "volcengine_desktop",
                    "qwen_desktop",
                },
            )
        else:
            raise ValueError(f"Unknown backend: {self.backend_name!r}")

    def _setup_oracle(self):
        if not self._oracle_settings.get("enabled"):
            return
        from auto_click.backends.reasoning_oracle import ReasoningOracle
        from settings_store import get_provider_settings

        provider = self._oracle_settings.get("provider", "zhipu")
        provider_settings = get_provider_settings(provider)
        api_key = (
            self._oracle_settings.get("api_key", "")
            or provider_settings.get("api_key", "")
        )
        api_base = (
            self._oracle_settings.get("api_base", "")
            or provider_settings.get("api_base", "")
        )
        model = (
            self._oracle_settings.get("model", "")
            or provider_settings.get("model", "")
        )

        self._oracle = ReasoningOracle(
            provider=provider,
            api_key=api_key,
            api_base=api_base,
            model=model,
            timeout=int(self._oracle_settings.get("timeout", 120) or 120),
        )
        logger.info("[Oracle] Initialized: %s/%s", self._oracle.provider, self._oracle.model)

    # Backends that drive an Android device via ADB (not autoglm_phone which
    # manages its own ADB connection internally).
    _ADB_BACKENDS = {"openai_adb", "adb_vlm", "glm_adb", "deepseek_adb", *ADB_MODE_BACKENDS}
    _OBSERVE_ADB_BACKENDS = {"observe_adb"}

    # Backends whose VLM returns coordinates in a 1000×1000 normalised space
    _NORMALIZED_COORD_BACKENDS = {"glm_adb", "deepseek_adb", *NORMALIZED_MODE_BACKENDS}

    def _setup_executor(self):
        if self.backend_name in self._OBSERVE_ADB_BACKENDS:
            self._setup_observe_tools()
            return
        if self.backend_name in self._ADB_BACKENDS:
            from auto_click.adb import ADBActionExecutor, ADBController
            self._adb_controller = ADBController(
                adb_path=self.adb_path,
                device_id=self.device_id,
            )
            self._adb_controller.ensure_ready()
            ime_id = self._adb_controller.ensure_adb_keyboard()
            if ime_id:
                logger.info("ADB Keyboard ready: %s", ime_id)
            else:
                logger.info("ADB Keyboard unavailable; text actions will use adb input text fallback")
            coord_scale_x = coord_scale_y = 1.0
            if self.backend_name in self._NORMALIZED_COORD_BACKENDS:
                try:
                    sw, sh = self._adb_controller.screen_size()
                    coord_scale_x = sw / 1000.0
                    coord_scale_y = sh / 1000.0
                    logger.info(
                        "Screen size %dx%d → coord scale (%.3f, %.3f)",
                        sw, sh, coord_scale_x, coord_scale_y,
                    )
                except Exception as exc:
                    logger.warning("Could not get screen size for coord scaling: %s", exc)
            self._prepare_forbidden_prompt_rects(coord_scale_x, coord_scale_y)
            self._executor = ADBActionExecutor(
                controller=self._adb_controller,
                confirm_before_execute=self.confirm_before_execute,
                coord_scale_x=coord_scale_x,
                coord_scale_y=coord_scale_y,
                forbidden_rects=self.forbidden_rects,
            )
            if self.audio_enabled and self.backend_name in {*self._ADB_BACKENDS, "autoglm_phone"}:
                from auto_click.audio import ADBaudioCapture
                self._audio_capture = ADBaudioCapture(
                    adb_path=self.adb_path,
                    device_id=self.device_id,
                    whisper_mode=self.whisper_mode,
                    whisper_api_key=self.whisper_api_key,
                    whisper_api_base=self.whisper_api_base,
                    whisper_api_model=self.whisper_api_model,
                    local_model=self.local_whisper_model,
                    duration_s=self.audio_duration_s,
                    on_status=self.on_audio_status,
                )
                logger.info(
                    "Audio capture enabled: mode=%s model=%s duration=%ss",
                    self.whisper_mode,
                    self.local_whisper_model,
                    self.audio_duration_s,
                )
                threading.Thread(
                    target=self._audio_capture.prewarm_local_model,
                    name="RealtimeASRPrewarm",
                    daemon=True,
                ).start()
            elif self.backend_name in {*self._ADB_BACKENDS, "autoglm_phone"}:
                logger.info("Audio capture disabled")
        else:
            from auto_click.executor import ActionExecutor
            self._prepare_forbidden_prompt_rects(1.0, 1.0)
            if self.desktop_capture:
                self._forbidden_prompt_space = "screenshot pixel coordinates"
            self._executor = ActionExecutor(
                confirm_before_execute=self.confirm_before_execute,
                bounds_check=True,
                forbidden_rects=self.forbidden_rects,
            )
        self._step_counter = 0
        if self.on_action:
            def _confirm(action: dict) -> bool:
                self._step_counter += 1
                self.on_action(action, self._step_counter)
                return True
            self._executor.set_confirm_callback(_confirm)

    def _setup_observe_tools(self) -> None:
        from auto_click.adb import ADBController

        self._adb_controller = ADBController(
            adb_path=self.adb_path,
            device_id=self.device_id,
        )
        self._adb_controller.ensure_ready()
        self._prepare_forbidden_prompt_rects(1.0, 1.0)
        self._executor = None
        if self.audio_enabled:
            from auto_click.audio import ADBaudioCapture

            self._audio_capture = ADBaudioCapture(
                adb_path=self.adb_path,
                device_id=self.device_id,
                whisper_mode=self.whisper_mode,
                whisper_api_key=self.whisper_api_key,
                whisper_api_base=self.whisper_api_base,
                whisper_api_model=self.whisper_api_model,
                local_model=self.local_whisper_model,
                duration_s=self.audio_duration_s,
                on_status=self.on_audio_status,
            )
            logger.info(
                "Observe-only audio enabled: mode=%s model=%s duration=%ss",
                self.whisper_mode,
                self.local_whisper_model,
                self.audio_duration_s,
            )
            threading.Thread(
                target=self._audio_capture.prewarm_local_model,
                name="ObserveASRPrewarm",
                daemon=True,
            ).start()
        else:
            logger.info("Observe-only audio disabled")
        self._step_counter = 0

    def _run_loop(self, task: str, initial_screenshot_b64: str):
        self._running = True
        history = None
        prev_response_id = None
        screenshot_b64 = initial_screenshot_b64
        step = 0
        oracle_context = ""
        audio_context = ""
        completed = False
        self._last_click_point = None
        self._same_click_count = 0
        self._auto_audio_triggered = False
        self._audio_listen_count = 0
        self._asr_speech_active = False
        self._asr_last_text_at = 0.0
        self._asr_gate_started_at = 0.0
        with self._continuous_audio_lock:
            self._continuous_audio_segments.clear()
        if self._audio_capture is not None and self.continuous_audio:
            self._audio_capture.start_continuous_transcription(
                on_transcript=self._on_continuous_audio_transcript,
                chunk_ms=1000,
            )
        try:
            while self._running and step < self.max_steps:
                step += 1
                logger.info("Step %d/%d", step, self.max_steps)

                continuous_audio_context = self._consume_continuous_audio_context()
                if continuous_audio_context:
                    audio_context = (audio_context + "\n" + continuous_audio_context).strip()
                    self._mark_asr_speech_activity(continuous_audio_context)
                if self._should_hold_for_asr_silence():
                    logger.info("ASR speech active; waiting for %.1fs silence before continuing", self._asr_silence_timeout_s)
                    if self.on_audio_status:
                        self.on_audio_status("ASR heard speech; waiting for the phrase to finish")
                    time.sleep(0.5)
                    screenshot_b64 = self._capture_screenshot_b64()
                    continue
                task_with_oracle = self._task_with_oracle_context(task, oracle_context, audio_context)
                if self.backend_name in {"openai", "openai_adb"}:
                    actions, prev_response_id = self._backend.get_next_action(
                        task_with_oracle, screenshot_b64, prev_response_id)
                elif self.backend_name == "anthropic":
                    actions, history = self._backend.get_next_action(
                        task_with_oracle, screenshot_b64, history)
                else:
                    with self._history_lock:
                        history_snapshot = list(self._vlm_history)
                    action = self._backend.get_next_action(
                        task_with_oracle, screenshot_b64,
                        action_history=history_snapshot)
                    if not self._running:
                        logger.info("Automation stopped while waiting for VLM response")
                        break
                    with self._history_lock:
                        self._vlm_history.append(action)
                    actions = [action]

                done = False
                for action in actions:
                    if not self._running:
                        break
                    atype = action.get("type", "")
                    if atype == "done":
                        done = True
                        break
                    if atype == "ask_oracle":
                        oracle_context = self._handle_oracle_action(
                            action, task_with_oracle, oracle_context, screenshot_b64
                        )
                        break
                    if atype in {"listen_audio", "analyze_audio", "transcribe_audio", "listen"}:
                        audio_context = self._handle_audio_action(action, audio_context)
                        break
                    if atype == "screenshot":
                        screenshot_b64 = self._capture_screenshot_b64()
                        continue
                    try:
                        self._executor.execute(action)
                    except Exception as exc:
                        from auto_click.forbidden_zones import ForbiddenClickError

                        if not isinstance(exc, ForbiddenClickError):
                            raise
                        logger.info("Action blocked and fed back to VLM: %s", exc)
                        blocked_action = {
                            "type": "blocked_click",
                            "reason": str(exc),
                            "original_action": action,
                        }
                        with self._history_lock:
                            self._vlm_history.append(blocked_action)
                        if self.on_action:
                            self.on_action(blocked_action, self._step_counter + 1)
                        screenshot_b64 = self._capture_screenshot_b64()
                        break
                    screenshot_b64 = self._capture_screenshot_b64()
                    auto_audio_reason = self._auto_audio_reason(action, task)
                    if auto_audio_reason:
                        logger.info("Auto audio capture triggered: %s", auto_audio_reason)
                        audio_context = self._handle_audio_action(
                            {
                                "type": "listen_audio",
                                "duration": max(5, self.audio_duration_s),
                                "question": auto_audio_reason,
                            },
                            audio_context,
                        )
                        break

                if done:
                    completed = True
                    break

            if not self._running and not done:
                if self.on_complete:
                    self.on_complete(False, "Stopped by user")
                return
            msg = "Task completed" if completed else f"Reached max {self.max_steps} steps"
            if self.on_complete:
                self.on_complete(completed, msg)
        except Exception as e:
            logger.exception("AutoClicker error")
            if self.on_complete:
                self.on_complete(False, str(e))
        finally:
            if self._audio_capture is not None:
                try:
                    self._audio_capture.stop_continuous_transcription()
                except Exception:
                    logger.debug("Failed to stop continuous audio", exc_info=True)
            self._running = False
            with self._history_lock:
                self._vlm_history.clear()

    def _run_observe_loop(self, task: str, initial_screenshot_b64: str) -> None:
        self._running = True
        screenshot_b64 = initial_screenshot_b64
        audio_context = ""
        notes: list[str] = []
        step = 0
        if self._audio_capture is not None and self.continuous_audio:
            self._audio_capture.start_continuous_transcription(
                on_transcript=self._on_continuous_audio_transcript,
                chunk_ms=1000,
            )
        try:
            while self._running and step < self.max_steps:
                step += 1
                logger.info("Observe step %d/%d", step, self.max_steps)
                continuous_audio_context = self._consume_continuous_audio_context()
                if continuous_audio_context:
                    audio_context = (audio_context + "\n" + continuous_audio_context).strip()
                    audio_context = self._trim_context(audio_context, 6000)

                previous_notes = self._trim_context("\n\n".join(notes[-6:]), 4000)
                observation = self._backend.observe(
                    task=task,
                    screenshot_b64=screenshot_b64,
                    audio_context=audio_context,
                    previous_notes=previous_notes,
                )
                notes.append(observation)
                if self.on_action:
                    self.on_action(
                        {
                            "type": "observation_note",
                            "text": observation,
                            "audio_context": audio_context[-1000:],
                        },
                        step,
                    )
                if not self._running:
                    break
                time.sleep(max(2, min(self.audio_duration_s, 8)))
                screenshot_b64 = self._capture_screenshot_b64()

            if self.on_complete:
                if self._running:
                    self.on_complete(True, "Observation finished")
                else:
                    self.on_complete(True, "Observation stopped")
        except Exception as e:
            logger.exception("Observe-only mode error")
            if self.on_complete:
                self.on_complete(False, str(e))
        finally:
            if self._audio_capture is not None:
                try:
                    self._audio_capture.stop_continuous_transcription()
                except Exception:
                    logger.debug("Failed to stop continuous audio", exc_info=True)
            self._running = False

    def _task_with_oracle_context(self, task: str, oracle_context: str, audio_context: str = "") -> str:
        if (
            self._oracle is None
            and not oracle_context
            and not audio_context
            and self._audio_capture is None
            and not self.forbidden_rects
        ):
            return task
        parts = [task]
        if self._forbidden_prompt_rects:
            zones = "; ".join(
                f"#{idx} [{int(r.get('x1', 0))},{int(r.get('y1', 0))},"
                f"{int(r.get('x2', 0))},{int(r.get('y2', 0))}]"
                for idx, r in enumerate(self._forbidden_prompt_rects, start=1)
            )
            parts.append(
                f"Forbidden click zones are active in {self._forbidden_prompt_space}. "
                f"Never click inside these rectangles: {zones}. If a desired target is inside one, "
                "choose a nearby allowed point or another UI path."
            )
        if audio_context:
            parts.append(
                "IMPORTANT AUDIO TRANSCRIPT AVAILABLE:\n"
                f"{audio_context}\n\n"
                "Use the transcript above now to choose the next UI action. Do not request "
                "listen_audio again unless the transcript explicitly says audio is unavailable "
                "or the user task clearly requires a new, different audio segment."
            )
        if self._oracle is not None:
            parts.append(
                "A reasoning oracle is available. If a step requires hard reasoning, "
                "return a JSON action with type ask_oracle, a question field, and an "
                "optional context field. The oracle answer will be added to the next step."
            )
        if self._audio_capture is not None:
            if self.continuous_audio:
                parts.append(
                "Continuous audio transcription is enabled from the start of the task. "
                    "If a listening/playback question appears, click the play/speaker button once, "
                    "then wait or continue using any transcript injected into this context. "
                    "Do not wait until playback finishes before asking for audio; audio is already being recorded. "
                    "Do not choose an answer or submit a listening/speech question until a real ASR transcript "
                    "has appeared in IMPORTANT AUDIO TRANSCRIPT AVAILABLE."
                )
            else:
                parts.append(
                    "A speech transcription tool is available. If the task depends on audio, "
                    "voice messages, spoken instructions, video sound, or a listening test, "
                    'return {"type":"listen_audio","duration":5,"question":"what to listen for"} '
                    "and the transcript will be added to the next step. Do not repeatedly click "
                    "a play/speaker/voice button when you need to hear content; click it once if "
                    "necessary, then request listen_audio."
                )
        if oracle_context:
            parts.append(f"Reasoning oracle answers so far:\n{oracle_context}")
        return "\n\n".join(parts)

    def _handle_audio_action(self, action: dict, audio_context: str) -> str:
        if self._audio_capture is None:
            logger.warning("listen_audio requested but audio capture is not enabled")
            if self.on_audio_status:
                self.on_audio_status("Audio tool unavailable: enable Audio Capture in Android settings.")
            return audio_context + "\nAudio tool unavailable: enable Audio Capture in Android settings."
        duration = action.get("duration", action.get("seconds", self.audio_duration_s))
        try:
            duration = int(duration)
        except (TypeError, ValueError):
            duration = self.audio_duration_s
        duration = max(1, min(max(duration, self.audio_duration_s), 30))
        question = str(action.get("question") or action.get("context") or "").strip()
        if self._audio_listen_count >= 2 and self._has_valid_audio_context(audio_context):
            transcript = "[audio skipped: existing transcript is already available; use it for the next action]"
            logger.info("Skipping repeated listen_audio because a transcript is already available")
        else:
            self._audio_listen_count += 1
            transcript = self._audio_capture.capture_and_transcribe(duration_s=duration)
        if not transcript:
            reason = getattr(self._audio_capture, "last_error", "") or "no speech detected or transcription failed"
            transcript = f"[audio unavailable: {reason}]"
        transcript_action = {
            "type": "audio_transcript",
            "duration": duration,
            "question": question,
            "text": transcript,
            "recording": getattr(self._audio_capture, "last_recording_path", ""),
        }
        with self._history_lock:
            self._vlm_history.append(transcript_action)
        logger.info("Audio transcript injected into VLM context: %s", transcript[:160])
        if self.on_action:
            self.on_action(
                transcript_action,
                self._step_counter + 1,
            )
        entry = f"- duration={duration}s"
        if question:
            entry += f", question={question}"
        entry += f": {transcript}"
        return (audio_context + "\n" + entry).strip()

    def _on_continuous_audio_transcript(self, text: str, recording: str = "", duration: int = 1) -> None:
        text = (text or "").strip()
        if not text:
            return
        entry = f"- continuous_audio {duration}s: {text}"
        with self._continuous_audio_lock:
            self._continuous_audio_segments.append(entry)
        action = {
            "type": "audio_transcript",
            "duration": duration,
            "question": "continuous Android audio",
            "text": text,
            "recording": recording,
        }
        with self._history_lock:
            self._vlm_history.append(action)
        logger.info("Continuous audio transcript injected into VLM context: %s", text[:160])
        if self.on_action:
            self.on_action(action, self._step_counter + 1)

    def _consume_continuous_audio_context(self) -> str:
        items: list[str] = []
        with self._continuous_audio_lock:
            items.extend(self._continuous_audio_segments)
            self._continuous_audio_segments.clear()
        if self._audio_capture is not None:
            try:
                for text in self._audio_capture.consume_continuous_transcripts():
                    text = str(text or "").strip()
                    if text:
                        items.append(f"- continuous_audio cached: {text}")
                        logger.info("Consumed cached continuous ASR transcript: %s", text[:160])
            except Exception:
                logger.debug("Failed to consume cached continuous ASR transcripts", exc_info=True)
        if not items:
            return ""
        return "\n".join(items)

    @staticmethod
    def _trim_context(text: str, max_chars: int) -> str:
        text = (text or "").strip()
        if len(text) <= max_chars:
            return text
        return text[-max_chars:].lstrip()

    def _mark_asr_speech_activity(self, audio_context: str) -> None:
        if not self._has_valid_audio_context(audio_context):
            return
        now = time.time()
        if not self._asr_speech_active:
            self._asr_gate_started_at = now
            logger.info("ASR speech detected; opening short audio gate")
        self._asr_speech_active = True
        self._asr_last_text_at = now

    def _should_hold_for_asr_silence(self) -> bool:
        if not self._asr_speech_active:
            return False
        now = time.time()
        silence_s = now - self._asr_last_text_at
        held_s = now - self._asr_gate_started_at
        if silence_s < self._asr_silence_timeout_s and held_s < self._asr_max_hold_s:
            return True
        self._asr_speech_active = False
        logger.info(
            "ASR phrase window closed after %.1fs silence / %.1fs hold; continuing automation",
            silence_s,
            held_s,
        )
        if self.on_audio_status:
            self.on_audio_status("ASR phrase ready; continuing")
        return False

    @staticmethod
    def _has_valid_audio_context(audio_context: str) -> bool:
        lines = [line.strip() for line in str(audio_context or "").splitlines() if line.strip()]
        for line in lines:
            lowered = line.lower()
            if "[audio unavailable:" in lowered or "[audio skipped:" in lowered:
                continue
            if lowered.startswith("audio tool unavailable"):
                continue
            if ":" in line:
                payload = line.split(":", 1)[1].strip()
            else:
                payload = line
            if payload and not payload.startswith("["):
                return True
        return False

    def _auto_audio_reason(self, action: dict, task: str) -> str:
        """Trigger audio capture when the VLM keeps clicking audio UI instead of using the tool."""
        if self._audio_capture is None or self._auto_audio_triggered:
            return ""
        atype = str(action.get("type", "")).lower()
        if atype not in {"click", "double_click"}:
            self._same_click_count = 0
            self._last_click_point = None
            return ""
        try:
            point = (int(action.get("x")), int(action.get("y")))
        except (TypeError, ValueError):
            return ""

        if self._last_click_point is not None:
            lx, ly = self._last_click_point
            if abs(point[0] - lx) <= 15 and abs(point[1] - ly) <= 15:
                self._same_click_count += 1
            else:
                self._same_click_count = 1
        else:
            self._same_click_count = 1
        self._last_click_point = point

        if self._same_click_count >= 2:
            self._auto_audio_triggered = True
            return "The model clicked the same area repeatedly; capture current Android audio before deciding the next action."

        if self._task_mentions_audio(task):
            self._auto_audio_triggered = True
            return "The user task appears to depend on audio; capture the sound after the current click."
        return ""

    @staticmethod
    def _task_mentions_audio(task: str) -> bool:
        text = task.lower()
        hints = (
            "语音", "声音", "音频", "听", "播放", "录音", "朗读", "听力",
            "voice", "audio", "listen", "listening", "sound", "spoken", "speech",
        )
        return any(hint in text for hint in hints)

    def _prepare_forbidden_prompt_rects(self, x_scale: float, y_scale: float) -> None:
        if not self.forbidden_rects:
            self._forbidden_prompt_rects = []
            return
        if self.backend_name in self._NORMALIZED_COORD_BACKENDS and x_scale and y_scale:
            self._forbidden_prompt_space = "the same normalized 1000x1000 coordinate system used by your actions"
            self._forbidden_prompt_rects = [
                {
                    "x1": int(float(rect.get("x1", 0)) / x_scale),
                    "y1": int(float(rect.get("y1", 0)) / y_scale),
                    "x2": int(float(rect.get("x2", 0)) / x_scale),
                    "y2": int(float(rect.get("y2", 0)) / y_scale),
                }
                for rect in self.forbidden_rects
            ]
        else:
            self._forbidden_prompt_space = "real screen pixel coordinates"
            self._forbidden_prompt_rects = self.forbidden_rects

    def _handle_oracle_action(
        self,
        action: dict,
        task_with_oracle: str,
        oracle_context: str,
        screenshot_b64: str = "",
    ) -> str:
        question = str(action.get("question") or action.get("text") or "").strip()
        context = str(action.get("context") or task_with_oracle)
        if not question:
            question = "What should be done next to complete the task?"
        if self._oracle is None:
            answer = "[Oracle disabled]"
            logger.warning("[Oracle] ask_oracle action requested but oracle is not enabled")
        else:
            answer = self._oracle.ask(question, context=context, image_b64=screenshot_b64)
        if str(answer).upper().startswith("ERROR:"):
            raise RuntimeError(str(answer))
        entry = f"Question: {question}\nAnswer: {answer}"
        return f"{oracle_context}\n\n{entry}".strip()

    def _run_phone_task(self, task: str) -> None:
        """Entry point for autoglm_phone backend.

        Single owner of on_complete: helpers return (success, msg) tuples so
        this method is the only place the callback is ever invoked.
        """
        self._running = True
        success, msg = False, "Unknown error"
        try:
            if self._oracle is not None:
                success, msg = self._run_phone_oracle_loop(task)
            else:
                success, msg = self._run_phone_single(task)
        except Exception as e:
            logger.exception("AutoGLM-Phone task failed")
            success, msg = False, str(e)
        finally:
            self._running = False
            if self.on_complete:
                self.on_complete(success, msg)

    # ------------------------------------------------------------------
    # Phone helpers — return (success, message), never call on_complete
    # ------------------------------------------------------------------

    def _phone_run_with_stop(self, micro_task: str) -> str:
        """Call backend.run_task in a daemon thread; return result string or raise.

        Returns the sentinel ``"__STOPPED__"`` (without raising) when a stop
        is requested mid-run so callers can distinguish stop from empty result.
        """
        import threading
        result_box: list = [None]
        error_box:  list = [None]

        def _worker() -> None:
            try:
                result_box[0] = self._backend.run_task(micro_task)
            except Exception as exc:  # noqa: BLE001
                error_box[0] = exc

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        while t.is_alive():
            if not self._running:
                logger.info("[Phone] Stop requested — abandoning micro-task")
                return "__STOPPED__"
            t.join(timeout=0.3)

        if error_box[0] is not None:
            raise error_box[0]
        return str(result_box[0] or "")

    def _run_phone_single(self, task: str) -> tuple:
        """Single-shot phone task with stop support. Returns (success, msg)."""
        result = self._phone_run_with_stop(task)
        if result == "__STOPPED__":
            return False, "Stopped by user"
        return True, result or "Phone task completed"

    def _run_phone_oracle_loop(self, task: str) -> tuple:
        """Multi-step loop: screenshot → oracle → phone agent → repeat.

        The oracle analyses each screenshot, extracts the current question /
        required action, and produces a precise answer.  The phone agent then
        performs exactly that one action (fill answer + submit).  The loop
        continues until the oracle says DONE or max_steps is reached.

        Returns (success, message). Never calls on_complete directly.
        This is the recommended mode for quiz / exam automation scenarios.
        """
        step = 0
        oracle_history: list[str] = []

        while self._running and step < self.max_steps:
            step += 1
            logger.info("[Phone Oracle Loop] Step %d/%d", step, self.max_steps)

            # ── 1. Capture current screen ──────────────────────────────────
            screenshot_b64 = self._capture_screenshot_b64()

            # ── 2. Ask oracle to read the screen and decide what to do ─────
            history_block = (
                "\n\nSteps completed so far:\n" + "\n".join(oracle_history)
                if oracle_history else ""
            )
            oracle_prompt = (
                f"Overall task: {task}\n"
                f"{history_block}\n\n"
                "Look at the current phone screen screenshot carefully.\n"
                "• If you see a question, problem, or fill-in-the-blank that needs answering, "
                "reply with ONLY the exact answer text to type — nothing else.\n"
                "• If the task is fully complete (no more questions, success screen, etc.), "
                "reply with exactly: DONE\n"
                "• If you see an error or unexpected state, describe it briefly starting with ERROR:\n"
                "Do NOT include any explanation, labels, or punctuation beyond the answer itself."
            )

            oracle_answer = self._oracle.ask(
                oracle_prompt, context=task, image_b64=screenshot_b64
            ).strip()
            logger.info("[Phone Oracle Loop] Oracle → %s", oracle_answer[:120])

            # ── 3. Handle oracle response ──────────────────────────────────
            if not oracle_answer or oracle_answer.upper().startswith("DONE"):
                logger.info("[Phone Oracle Loop] Oracle says DONE at step %d", step)
                return True, f"All questions answered ({step - 1} steps)"

            if oracle_answer.upper().startswith("ERROR:"):
                logger.warning("[Phone Oracle Loop] Oracle reported error: %s", oracle_answer)
                return False, oracle_answer

            # Log the oracle-derived action for the UI
            if self.on_action:
                self.on_action(
                    {"type": "oracle_answer", "question_step": step, "answer": oracle_answer},
                    step,
                )

            oracle_history.append(f"[{step}] Answered: {oracle_answer[:80]}")

            # ── 4. Build a precise micro-task for the phone agent ──────────
            micro_task = (
                f"On the current screen there is an input field or answer box. "
                f"Type the following answer exactly as written, then tap the Submit / "
                f"Next / Confirm button:\n\n{oracle_answer}"
            )

            # ── 5. Run phone agent for this micro-task ─────────────────────
            result = self._phone_run_with_stop(micro_task)

            if result == "__STOPPED__":
                return False, "Stopped by user"

            if self.on_action:
                self.on_action(
                    {"type": "phone_step", "step": step, "result": result[:80]},
                    step,
                )

        if not self._running:
            return False, "Stopped by user"
        return False, f"Reached max {self.max_steps} steps without completing"

    def _capture_screenshot_b64(self) -> str:
        if self.backend_name in {*self._ADB_BACKENDS, *self._OBSERVE_ADB_BACKENDS, "autoglm_phone"}:
            if self._adb_controller is None:
                from auto_click.adb import ADBController
                self._adb_controller = ADBController(
                    adb_path=self.adb_path,
                    device_id=self.device_id,
                )
            return self._adb_controller.screenshot_b64()

        try:
            if self.desktop_capture:
                from windows.capture import capture_desktop

                screenshot, frame = capture_desktop(self.desktop_capture, save=False)
                if self._executor is not None and hasattr(
                    self._executor,
                    "set_coordinate_frame",
                ):
                    self._executor.set_coordinate_frame(frame)
            else:
                screenshot = pyautogui.screenshot()
            screenshot = screenshot.convert("RGB")
            if self.on_screenshot:
                self.on_screenshot(screenshot.copy())
            buf = io.BytesIO()
            screenshot.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode()
        except Exception as exc:
            logger.exception("Desktop screenshot capture failed")
            raise RuntimeError(f"Desktop screenshot capture failed: {exc}") from exc
