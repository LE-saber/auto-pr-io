"""Adapter for the Open-AutoGLM phone automation framework."""
from __future__ import annotations

import logging
import multiprocessing
import multiprocessing.queues
import os
import pathlib
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 0.3   # seconds between stop checks while waiting for subprocess


# ---------------------------------------------------------------------------
# Top-level worker — must live at module level so multiprocessing "spawn"
# (default on Windows) can pickle and import it in the child process.
# ---------------------------------------------------------------------------

def _phone_agent_worker(
    result_queue: multiprocessing.Queue,
    api_key: str,
    api_base: str,
    model: str,
    device_id: Optional[str],
    task: str,
    adb_exe: str,
) -> None:
    """Runs inside a child process.  Puts ("ok", result) or ("error", msg)."""
    # Inject ADB path into the child's environment
    if adb_exe and adb_exe != "adb":
        adb_dir = str(pathlib.Path(adb_exe).parent)
        if adb_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = adb_dir + os.pathsep + os.environ.get("PATH", "")

    try:
        from phone_agent import PhoneAgent
        from phone_agent.agent import AgentConfig
        from phone_agent.model import ModelConfig
    except ModuleNotFoundError as exc:
        result_queue.put(("error", (
            "AutoGLM-Phone requires the Open-AutoGLM package. Install it from "
            "https://github.com/zai-org/Open-AutoGLM, configure ADB/HDC, then retry."
        )))
        return

    try:
        model_config = ModelConfig(
            base_url=api_base,
            api_key=api_key or "EMPTY",
            model_name=model,
        )
        agent_config = AgentConfig(device_id=device_id, lang="cn", verbose=True)
        agent = PhoneAgent(model_config=model_config, agent_config=agent_config)
        result = agent.run(task)
        result_queue.put(("ok", str(result or "")))
    except Exception as exc:  # noqa: BLE001
        result_queue.put(("error", str(exc)))


# ---------------------------------------------------------------------------

class AutoGLMPhoneBackend:
    """Run phone tasks through the optional Open-AutoGLM package.

    This backend targets Android/HarmonyOS devices controlled by ADB/HDC.

    Stop mechanism
    --------------
    PhoneAgent.run() is a blocking third-party call that cannot be interrupted
    from within the same process.  We therefore run each task in a **child
    process** via multiprocessing.  When stop() is called, we call
    proc.terminate() which sends SIGTERM (Windows: TerminateProcess) to the
    child, immediately killing it along with any in-flight LLM HTTP requests.
    This is the only reliable way to stop an uncooperative blocking call.
    """

    def __init__(
        self,
        api_key: str = "",
        api_base: str = "",
        model: str = "autoglm-phone",
        device_id: str | None = None,
        adb_exe: str = "adb",
        on_action: Optional[Callable[[dict, int], None]] = None,
    ):
        self.api_key = api_key
        self.api_base = api_base or "https://open.bigmodel.cn/api/paas/v4"
        self.model = model or "autoglm-phone"
        self.device_id = device_id
        self.adb_exe = adb_exe or "adb"
        self.on_action = on_action
        self._proc: Optional[multiprocessing.Process] = None
        self._stopped = False

    def stop(self) -> None:
        """Immediately terminate the child process running the phone agent."""
        self._stopped = True
        proc = self._proc
        if proc is not None and proc.is_alive():
            logger.info("[AutoGLM-Phone] stop() — terminating child process (pid=%s)", proc.pid)
            proc.terminate()
            try:
                proc.join(timeout=3)
            except Exception:
                pass
            if proc.is_alive():
                proc.kill()   # SIGKILL fallback
                proc.join(timeout=2)

    def reset(self) -> None:
        self._stopped = False
        self._proc = None

    def run_task(self, task: str) -> str:
        """Run *task* on the phone.  Returns result string, or raises on error.

        The phone agent runs in a child process so that stop() can terminate it
        immediately (killing all in-flight network / LLM requests).
        """
        self._stopped = False

        if self.on_action:
            self.on_action({"type": "phone_task", "task": task}, 1)

        # Use "spawn" context so the child process starts clean on all platforms.
        ctx = multiprocessing.get_context("spawn")
        result_queue: multiprocessing.Queue = ctx.Queue()

        self._proc = ctx.Process(
            target=_phone_agent_worker,
            args=(
                result_queue,
                self.api_key,
                self.api_base,
                self.model,
                self.device_id,
                task,
                self.adb_exe,
            ),
            daemon=True,
        )
        self._proc.start()
        logger.info("[AutoGLM-Phone] Child process started (pid=%s) for task: %s", self._proc.pid, task[:60])

        # Poll until the child finishes or stop is requested
        while self._proc.is_alive():
            if self._stopped:
                logger.info("[AutoGLM-Phone] Already stopped — child was terminated")
                return "__STOPPED__"
            self._proc.join(timeout=_POLL_INTERVAL)

        # Child finished normally — read result
        try:
            status, value = result_queue.get(timeout=2)
        except Exception:
            return ""

        if status == "error":
            raise RuntimeError(value)
        return value
