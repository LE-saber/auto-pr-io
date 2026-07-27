"""Realtime Android audio capture and local SenseVoice transcription."""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

HELPER_PACKAGE = "com.autopr.keyboardaudio"
HELPER_SERVICE = f"{HELPER_PACKAGE}/.AudioCaptureService"
HELPER_RECORD_ACTION = "com.autopr.keyboardaudio.START_RECORD"
HELPER_REMOTE_WAV = f"/sdcard/Android/data/{HELPER_PACKAGE}/files/recordings/latest.wav"
HELPER_REMOTE_RECORDINGS = f"/sdcard/Android/data/{HELPER_PACKAGE}/files/recordings"
HELPER_REMOTE_STATUS = f"/sdcard/Android/data/{HELPER_PACKAGE}/files/recordings/status.txt"


class ADBaudioCapture:
    """Capture Android device audio and transcribe it.

    The public interface for the automation loop is ``capture_and_transcribe``.
    VLM backends can request this through the ``listen_audio`` action.
    """

    def __init__(
        self,
        adb_path: str = "adb",
        device_id: str = "",
        whisper_mode: str = "sensevoice_streaming",
        whisper_api_key: str = "",
        whisper_api_base: str = "",
        whisper_api_model: str = "whisper-1",
        local_model: str = "iic/SenseVoiceSmall",
        duration_s: int = 5,
        archive_dir: str = "recordings",
        on_status: Optional[callable] = None,
    ):
        self.adb_path = adb_path or "adb"
        self.device_id = device_id.strip()
        self.whisper_mode = "sensevoice_streaming"
        self.whisper_api_key = whisper_api_key
        self.whisper_api_base = whisper_api_base or "https://api.openai.com/v1"
        self.whisper_api_model = whisper_api_model or "whisper-1"
        self.local_model = local_model or "iic/SenseVoiceSmall"
        self.duration_s = max(1, min(int(duration_s or 5), 300))
        self.archive_dir = archive_dir or "recordings"
        self._android_version: Optional[int] = None
        self._sensevoice_model = None
        self._model_lock = threading.Lock()
        self._on_status = on_status
        self.last_error = ""
        self.last_recording_path = ""
        self._continuous_thread: threading.Thread | None = None
        self._continuous_stop = threading.Event()
        self._continuous_lock = threading.Lock()
        self._continuous_transcripts: list[str] = []
        self._continuous_running = False

    def capture_and_transcribe(self, duration_s: int | None = None) -> str:
        """Record device audio for ``duration_s`` seconds and return transcript text."""
        if self.is_continuous_running():
            duration = max(1, min(int(duration_s or self.duration_s), 30))
            return self.wait_for_continuous_transcript(timeout_s=duration)

        android_ver = self._get_android_version()
        if android_ver < 13:
            logger.debug("Audio capture requires Android 13+, device has Android %d", android_ver)
            self._fail(f"Audio requires Android 13+; current Android {android_ver or '?'}")
            return ""

        duration = max(1, min(int(duration_s or self.duration_s), 300))
        try:
            if not self._helper_installed():
                raise RuntimeError(
                    "Realtime ASR requires AutoPr Keyboard Audio helper with chunk output installed."
                )
            return self._capture_streaming_chunks(duration)
        except Exception as exc:
            logger.warning("Realtime audio capture/transcription failed: %s", exc)
            self._fail(f"Realtime ASR failed: {exc}")
            return ""

    def prewarm_local_model(self) -> None:
        """Load the local streaming ASR model before the first audio action."""
        try:
            model_name = self._sensevoice_model_name()
            self._set_status(f"Prewarming realtime ASR {model_name}")
            self._ensure_sensevoice_model()
            self._set_status(f"Realtime ASR ready: {model_name}")
        except Exception as exc:
            logger.warning("ASR prewarm failed: %s", exc)
            self._fail(f"ASR prewarm failed: {exc}")

    def start_continuous_transcription(
        self,
        on_transcript: Optional[callable] = None,
        chunk_ms: int = 1000,
        duration_s: int = 21600,
    ) -> None:
        """Start long-running Android audio capture and transcribe chunks in the background."""
        if self.is_continuous_running():
            return
        android_ver = self._get_android_version()
        if android_ver < 13:
            self._fail(f"Audio requires Android 13+; current Android {android_ver or '?'}")
            return
        if not self._helper_installed():
            self._fail("AutoPr Keyboard Audio helper is not installed.")
            return

        self._continuous_stop.clear()
        with self._continuous_lock:
            self._continuous_transcripts.clear()
        self._continuous_thread = threading.Thread(
            target=self._continuous_loop,
            args=(on_transcript, max(500, min(int(chunk_ms or 1000), 10000)), max(1, int(duration_s or 21600))),
            name="AndroidContinuousASR",
            daemon=True,
        )
        self._continuous_thread.start()

    def stop_continuous_transcription(self) -> None:
        """Stop background Android recording/transcription if it is running."""
        self._continuous_stop.set()
        try:
            self._run(
                [
                    "shell",
                    "am",
                    "start-foreground-service",
                    "-n",
                    HELPER_SERVICE,
                    "-a",
                    "com.autopr.keyboardaudio.STOP_RECORD",
                ],
                timeout=5,
            )
        except Exception:
            pass
        thread = self._continuous_thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        self._continuous_running = False

    def is_continuous_running(self) -> bool:
        thread = self._continuous_thread
        return bool(self._continuous_running and thread and thread.is_alive())

    def wait_for_continuous_transcript(self, timeout_s: int = 5) -> str:
        """Return new continuous-ASR text, waiting briefly for a fresh chunk."""
        deadline = time.time() + max(1, timeout_s)
        start_len = len(self._continuous_transcripts)
        while time.time() < deadline:
            with self._continuous_lock:
                new_items = self._continuous_transcripts[start_len:]
            if new_items:
                return " ".join(new_items).strip()
            time.sleep(0.25)
        with self._continuous_lock:
            recent = self._continuous_transcripts[-3:]
        return " ".join(recent).strip()

    def consume_continuous_transcripts(self) -> list[str]:
        with self._continuous_lock:
            items = list(self._continuous_transcripts)
            self._continuous_transcripts.clear()
        return items

    def _record_remote(self, remote_path: str, duration_s: int) -> None:
        self._set_status(f"Recording device audio ({duration_s}s)")
        self._run(["shell", "rm", "-f", remote_path], timeout=5)
        result = self._run(
            ["shell", "screenrecord", "--audio", f"--time-limit={duration_s}", remote_path],
            timeout=duration_s + 10,
        )
        if result.returncode != 0:
            raise RuntimeError(self._completed_error(result) or "screenrecord failed")

    def _screenrecord_supports_audio(self) -> bool:
        try:
            result = self._run(["shell", "screenrecord", "--help"], text=True, timeout=5)
        except Exception:
            return False
        output = (result.stdout or "") + (result.stderr or "")
        return "--audio" in output

    def _record_with_helper(self, local_path: str, duration_s: int) -> None:
        if not self._helper_installed():
            raise RuntimeError(
                "ADB audio is unsupported on this device and AutoPr Keyboard Audio helper is not installed."
            )
        self._set_status(f"Recording via AutoPr helper ({duration_s}s)")
        result = self._run(
            [
                "shell",
                "am",
                "start-foreground-service",
                "-n",
                HELPER_SERVICE,
                "-a",
                HELPER_RECORD_ACTION,
                "--ei",
                "duration",
                str(duration_s),
            ],
            timeout=10,
        )
        if result.returncode != 0:
            logger.info("Direct helper service start failed, falling back to broadcast: %s", self._completed_error(result))
            self._run(
                [
                    "shell",
                    "am",
                    "broadcast",
                    "-a",
                    HELPER_RECORD_ACTION,
                    "--ei",
                    "duration",
                    str(duration_s),
                ],
                timeout=10,
            )
        time.sleep(duration_s + 1.0)
        result = self._run(["pull", HELPER_REMOTE_WAV, local_path], timeout=30)
        if result.returncode != 0:
            status = self._read_helper_status()
            raise RuntimeError(
                self._completed_error(result)
                or status
                or "AutoPr helper did not produce audio. Open its Android UI and grant internal audio capture."
            )

    def _capture_streaming_chunks(self, duration_s: int) -> str:
        """Capture helper-generated WAV chunks and transcribe them as they appear."""
        chunk_ms = 1000
        self._set_status(f"Streaming local ASR ({duration_s}s)")
        with tempfile.TemporaryDirectory(prefix="autopr_audio_stream_") as tmpdir:
            result = self._run(
                [
                    "shell",
                    "am",
                    "start-foreground-service",
                    "-n",
                    HELPER_SERVICE,
                    "-a",
                    HELPER_RECORD_ACTION,
                    "--ei",
                    "duration",
                    str(duration_s),
                    "--ei",
                    "chunk_ms",
                    str(chunk_ms),
                ],
                timeout=10,
            )
            if result.returncode != 0:
                raise RuntimeError(self._completed_error(result) or "AutoPr helper streaming start failed")

            transcripts: list[str] = []
            idx = 1
            deadline = time.time() + duration_s + 2.0
            while time.time() < deadline:
                remote = f"{HELPER_REMOTE_RECORDINGS}/chunk_{idx:04d}.wav"
                local_path = os.path.join(tmpdir, f"chunk_{idx:04d}.wav")
                pulled = self._run(["pull", remote, local_path], timeout=5)
                if pulled.returncode == 0 and os.path.exists(local_path) and os.path.getsize(local_path) > 44:
                    archived = self._archive_audio(local_path)
                    text = self._transcribe(archived or local_path)
                    if archived:
                        self._write_transcript_sidecar(archived, text)
                    if text and not self._is_duplicate_transcript(transcripts, text):
                        transcripts.append(text)
                        preview = text[:60] + ("..." if len(text) > 60 else "")
                        self._set_status(f"Streaming transcript: {preview}")
                    idx += 1
                    continue
                time.sleep(0.25)

            full_path = os.path.join(tmpdir, "latest.wav")
            full_pull = self._run(["pull", HELPER_REMOTE_WAV, full_path], timeout=30)
            if full_pull.returncode == 0 and os.path.exists(full_path) and os.path.getsize(full_path) > 44:
                self._archive_audio(full_path)
            if not transcripts and os.path.exists(full_path) and os.path.getsize(full_path) > 44:
                text = self._transcribe(full_path)
                if text:
                    transcripts.append(text)
            combined = " ".join(transcripts).strip()
            logger.info("Audio transcription (streaming): %s", combined[:160])
            if combined:
                self._set_status(f"Audio transcript: {combined[:60]}")
            else:
                self._set_status("Audio transcript empty")
            return combined

    def _continuous_loop(self, on_transcript: Optional[callable], chunk_ms: int, duration_s: int) -> None:
        chunk_seconds = max(1, chunk_ms // 1000)
        self._set_status("Continuous audio recording starting")
        result = self._run(
            [
                "shell",
                "am",
                "start-foreground-service",
                "-n",
                HELPER_SERVICE,
                "-a",
                HELPER_RECORD_ACTION,
                "--ei",
                "duration",
                str(duration_s),
                "--ei",
                "chunk_ms",
                str(chunk_ms),
            ],
            timeout=10,
        )
        if result.returncode != 0:
            self._fail(self._completed_error(result) or "Continuous audio start failed")
            return

        self._continuous_running = True
        idx = 1
        self._set_status("Continuous audio recording on")
        with tempfile.TemporaryDirectory(prefix="autopr_audio_continuous_") as tmpdir:
            while not self._continuous_stop.is_set():
                remote = f"{HELPER_REMOTE_RECORDINGS}/chunk_{idx:04d}.wav"
                local_path = os.path.join(tmpdir, f"chunk_{idx:04d}.wav")
                pulled = self._run(["pull", remote, local_path], timeout=5)
                if pulled.returncode == 0 and os.path.exists(local_path) and os.path.getsize(local_path) > 44:
                    archived = self._archive_audio(local_path)
                    text = self._transcribe(archived or local_path)
                    if archived:
                        self._write_transcript_sidecar(archived, text)
                    if text:
                        should_emit = False
                        with self._continuous_lock:
                            if not self._is_duplicate_transcript(self._continuous_transcripts, text):
                                self._continuous_transcripts.append(text)
                                should_emit = True
                        if should_emit:
                            preview = text[:60] + ("..." if len(text) > 60 else "")
                            self._set_status(f"Continuous transcript: {preview}")
                            if on_transcript:
                                try:
                                    on_transcript(text, archived or local_path, chunk_seconds)
                                except Exception:
                                    logger.warning("Continuous transcript callback failed", exc_info=True)
                    idx += 1
                    continue

                status = self._read_helper_status()
                if status.startswith("ERROR"):
                    self._fail(status)
                    break
                time.sleep(0.25)

            full_path = os.path.join(tmpdir, "continuous_latest.wav")
            if self._run(["pull", HELPER_REMOTE_WAV, full_path], timeout=15).returncode == 0:
                if os.path.exists(full_path) and os.path.getsize(full_path) > 44:
                    self._archive_audio(full_path)
        self._continuous_running = False
        self._set_status("Continuous audio recording stopped")

    @staticmethod
    def _is_duplicate_transcript(existing: list[str], text: str) -> bool:
        normalized = " ".join(text.lower().split())
        return any(normalized and normalized in " ".join(item.lower().split()) for item in existing[-3:])

    def _read_helper_status(self) -> str:
        result = self._run(["shell", "cat", HELPER_REMOTE_STATUS], text=True, timeout=5)
        if result.returncode == 0:
            return (result.stdout or "").strip()
        return ""

    def _helper_installed(self) -> bool:
        result = self._run(["shell", "pm", "path", HELPER_PACKAGE], text=True, timeout=5)
        return result.returncode == 0 and bool((result.stdout or "").strip())

    def _pull_remote(self, remote_path: str, local_path: str) -> None:
        self._set_status("Pulling audio from device")
        result = self._run(["pull", remote_path, local_path], timeout=30)
        if result.returncode != 0:
            raise RuntimeError(self._completed_error(result) or "adb pull failed")

    def _transcribe(self, file_path: str) -> str:
        self._set_status("Realtime ASR transcribing")
        return self._transcribe_sensevoice(file_path)

    def _transcribe_sensevoice(self, file_path: str) -> str:
        model = self._ensure_sensevoice_model()
        result = model.generate(
            input=file_path,
            language="auto",
            use_itn=True,
            batch_size_s=60,
        )
        text = self._clean_transcript(self._extract_sensevoice_text(result))
        logger.info("Audio transcription (realtime sensevoice): %s", text[:100])
        return text

    @staticmethod
    def _clean_transcript(text: str) -> str:
        text = str(text or "").strip()
        text = re.sub(r"<\|[^|]+?\|>", "", text)
        text = " ".join(text.split()).strip()
        if text.lower() in {"empty speech", "nospeech", "no speech"}:
            return ""
        return text

    def _ensure_sensevoice_model(self):
        with self._model_lock:
            if self._sensevoice_model is None:
                try:
                    from funasr import AutoModel
                except ImportError as exc:
                    raise RuntimeError(
                        "Local SenseVoice requires FunASR. Install local ASR dependencies "
                        "with Python 3.10-3.12 using `pip install funasr modelscope`; "
                        "Python 3.13 may fail because editdistance has no compatible wheel."
                    ) from exc
                model_name = self._sensevoice_model_name()
                self._set_status(f"Loading SenseVoice {model_name}")
                logger.info("Loading SenseVoice model '%s'", model_name)
                self._sensevoice_model = AutoModel(
                    model=model_name,
                    trust_remote_code=True,
                    vad_model="fsmn-vad",
                    vad_kwargs={"max_single_segment_time": 30000},
                    disable_update=True,
                )
            return self._sensevoice_model

    def _sensevoice_model_name(self) -> str:
        name = (self.local_model or "").strip()
        aliases = {"sensevoice-small", "sensevoicesmall", "sensevoice_small", "sensevoice"}
        if not name or name.lower() in aliases:
            return "iic/SenseVoiceSmall"
        return name

    @staticmethod
    def _extract_sensevoice_text(result) -> str:
        if isinstance(result, str):
            return result.strip()
        if isinstance(result, dict):
            value = result.get("text") or result.get("sentence_info") or ""
            if isinstance(value, str):
                return value.strip()
            if isinstance(value, list):
                return " ".join(
                    str(item.get("text", "") if isinstance(item, dict) else item).strip()
                    for item in value
                    if str(item).strip()
                ).strip()
        if isinstance(result, list):
            chunks = []
            for item in result:
                text = ADBaudioCapture._extract_sensevoice_text(item)
                if text:
                    chunks.append(text)
            return " ".join(chunks).strip()
        return str(result or "").strip()

    def _archive_audio(self, source_path: str) -> str:
        try:
            os.makedirs(self.archive_dir, exist_ok=True)
            suffix = os.path.splitext(source_path)[1] or ".wav"
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            device = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (self.device_id or "device"))
            dest = os.path.abspath(os.path.join(self.archive_dir, f"android_audio_{stamp}_{device}{suffix}"))
            shutil.copy2(source_path, dest)
            self.last_recording_path = dest
            logger.info("Audio recording archived: %s", dest)
            self._set_status(f"Audio saved: {dest}")
            return dest
        except Exception as exc:
            logger.warning("Audio archive failed: %s", exc)
            return ""

    @staticmethod
    def _write_transcript_sidecar(audio_path: str, text: str) -> None:
        try:
            with open(audio_path + ".txt", "w", encoding="utf-8") as handle:
                handle.write(text or "")
        except OSError:
            pass

    def _get_android_version(self) -> int:
        if self._android_version is not None:
            return self._android_version
        try:
            result = self._run(["shell", "getprop", "ro.build.version.release"], text=True, timeout=5)
            self._android_version = int(result.stdout.strip().split(".")[0])
        except Exception:
            self._android_version = 0
        return self._android_version

    def _set_status(self, msg: str) -> None:
        if self._on_status:
            try:
                self._on_status(msg)
            except Exception:
                pass

    def _fail(self, msg: str) -> None:
        self.last_error = msg
        self._set_status(msg)

    def _run(self, args: list[str], **kwargs) -> subprocess.CompletedProcess:
        command = [self.adb_path]
        if self.device_id:
            command.extend(["-s", self.device_id])
        command.extend(args)
        kwargs.setdefault("capture_output", True)
        return subprocess.run(command, **kwargs)

    @staticmethod
    def _completed_error(result: subprocess.CompletedProcess) -> str:
        stderr = result.stderr.decode("utf-8", errors="ignore") if isinstance(result.stderr, bytes) else result.stderr
        stdout = result.stdout.decode("utf-8", errors="ignore") if isinstance(result.stdout, bytes) else result.stdout
        return str(stderr or stdout or "").strip()
