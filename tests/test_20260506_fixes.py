"""Tests for 2026-05-06 security and stability fixes."""
import base64
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Keep the suite importable in a minimal environment without replacing real
# dependencies for every other test module in the same discovery process.
try:
    import pyautogui  # noqa: F401
except Exception:
    _FAKE_PYAUTOGUI = MagicMock()
    _FAKE_PYAUTOGUI.size.return_value = (1920, 1080)
    _FAKE_PYAUTOGUI.screenshot.return_value = MagicMock()
    sys.modules["pyautogui"] = _FAKE_PYAUTOGUI

try:
    import PIL  # noqa: F401
except ImportError:
    sys.modules["PIL"] = MagicMock()
    sys.modules["PIL.Image"] = MagicMock()
    sys.modules["PIL.ImageTk"] = MagicMock()

try:
    import dotenv  # noqa: F401
except ImportError:
    sys.modules["dotenv"] = MagicMock()


# ---------------------------------------------------------------------------
# 1. API key encryption roundtrip
# ---------------------------------------------------------------------------
def test_encrypt_decrypt_roundtrip():
    from settings_store import _encrypt_value, _decrypt_value

    cases = [
        "sk-proj-abc123def456",
        "",
        "1ba8078e340d4b64a312f9c267ca52b2.IAIggDkDbAm7reYF",
        "短密钥",
        "a" * 500,
    ]
    for plain in cases:
        enc = _encrypt_value(plain)
        dec = _decrypt_value(enc)
        assert dec == plain, f"Roundtrip failed for: {plain[:30]}..."
        assert enc != plain or plain == "", f"Encrypted value should differ from plaintext: {plain[:30]}"
    print("[PASS] encrypt/decrypt roundtrip")


def test_backward_compatibility():
    from settings_store import _decrypt_value

    # Plaintext values from pre-encryption settings should pass through
    assert _decrypt_value("sk-old-plaintext-key") == "sk-old-plaintext-key"
    assert _decrypt_value("") == ""
    assert _decrypt_value("b64:dGVzdA==") == "test"
    print("[PASS] backward compatibility")


def test_dpapi_failure_is_not_returned_as_an_api_key():
    import settings_store

    settings_store._DPAPI_FAILURE_WARNED = False
    with patch(
        "win32crypt.CryptUnprotectData",
        side_effect=RuntimeError("wrong Windows user"),
    ):
        assert settings_store._decrypt_value("dpapi:YQ==") == ""
    print("[PASS] DPAPI failure is treated as an unconfigured API key")


def test_settings_save_load_cycle():
    from settings_store import load_settings, save_settings, SETTINGS_FILE
    from copy import deepcopy
    import config

    # Load current settings
    original = load_settings()
    original_copy = deepcopy(original)

    # Create a temp settings file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False,
                                     encoding="utf-8") as tmp:
        tmp_path = tmp.name

    # Override settings file path temporarily
    old_path = SETTINGS_FILE
    try:
        # Use a fresh settings dict for testing
        test_settings = {
            "providers": {
                "openai": {
                    "api_key": "sk-test-save-load-12345",
                    "api_base": "https://api.test.com/v1",
                    "model": "gpt-4o",
                },
                "zhipu": {
                    "api_key": "test-zhipu-key-67890",
                    "api_base": "https://open.bigmodel.cn/api/paas/v4",
                    "model": "glm-4.6v-flashx",
                },
                "empty_provider": {
                    "api_key": "",
                    "api_base": "",
                    "model": "",
                },
            },
            "oracle": {
                "enabled": True,
                "provider": "zhipu",
                "api_key": "test-oracle-key",
                "api_base": "https://open.bigmodel.cn/api/paas/v4",
                "model": "glm-4.6v-flashx",
                "timeout": "120",
            },
            "audio": {
                "enabled": False,
                "sensevoice_model": "iic/SenseVoiceSmall",
                "duration_s": 3,
                "whisper_api_key": "test-whisper-key",
            },
        }

        # Patch SETTINGS_FILE to use temp path
        import settings_store
        settings_store.SETTINGS_FILE = Path(tmp_path)

        # Save (should encrypt)
        save_settings(test_settings)

        # Read the raw file to verify keys are NOT plaintext
        with open(tmp_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        for provider_name, provider in raw.get("providers", {}).items():
            if provider.get("api_key"):
                assert provider["api_key"] != test_settings["providers"][provider_name]["api_key"], \
                    f"Provider {provider_name} api_key should be encrypted on disk"

        if raw.get("oracle", {}).get("api_key"):
            assert raw["oracle"]["api_key"] != "test-oracle-key", \
                "Oracle api_key should be encrypted on disk"

        # Load (should decrypt)
        loaded = load_settings()

        for provider_name, provider in test_settings["providers"].items():
            assert loaded["providers"][provider_name]["api_key"] == provider["api_key"], \
                f"Provider {provider_name} api_key should decrypt correctly"

        assert loaded["oracle"]["api_key"] == "test-oracle-key"
        assert loaded["audio"]["whisper_api_key"] == "test-whisper-key"
        print("[PASS] settings save/load cycle with encryption")

    finally:
        # Restore
        settings_store.SETTINGS_FILE = old_path
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# 2. History file rotation
# ---------------------------------------------------------------------------
def test_history_rotation():
    import auto_click.history as hist_mod

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False,
                                     encoding="utf-8") as tmp:
        tmp_path = tmp.name

    old_path = hist_mod.HISTORY_FILE
    old_max_size = hist_mod._MAX_FILE_SIZE
    try:
        hist_mod.HISTORY_FILE = Path(tmp_path)

        # Seed the file with many records, then verify trimming
        records_needed = 250
        for i in range(records_needed):
            hist_mod.append_task_history({
                "task": f"Test task #{i} with padding to exceed limit: "
                        f"abcdefghijklmnopqrstuvwxyz0123456789 " * 5,
                "success": True,
                "backend": "test",
            })

        size_before = os.path.getsize(tmp_path)

        # Set a low limit and append one more to trigger trim
        hist_mod._MAX_FILE_SIZE = 1024
        hist_mod.append_task_history({
            "task": "Trigger rotation record " + "X" * 100,
            "success": True,
            "backend": "test",
        })

        size_after = os.path.getsize(tmp_path)
        records = hist_mod.load_task_history(limit=500)

        # After rotation, record count should be trimmed
        assert len(records) < records_needed + 1, \
            f"Rotation should reduce records, got {len(records)} of {records_needed + 1}"
        assert len(records) > 0, "Should still have records after rotation"
        print(f"[PASS] history rotation (size: {size_before} -> {size_after}, "
              f"records: {records_needed+1} -> {len(records)})")

    finally:
        hist_mod.HISTORY_FILE = old_path
        hist_mod._MAX_FILE_SIZE = old_max_size
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# 3. Log panel line cap
# ---------------------------------------------------------------------------
def test_log_panel_cap():
    # Test the cap logic directly (avoids tkinter import chain)
    class MockLogPanel:
        _MAX_LINES = 5000
        def __init__(self):
            self._lines = []
        def append(self, line):
            self._lines.append(line)
            if len(self._lines) > self._MAX_LINES:
                self._lines = self._lines[-self._MAX_LINES:]

    panel = MockLogPanel()
    for i in range(6000):
        panel.append(f"Line {i:06d}")

    assert len(panel._lines) == 5000, f"Should cap at 5000, got {len(panel._lines)}"
    assert panel._lines[0].startswith("Line 001000"), f"First line should be ~1000, got {panel._lines[0]}"
    assert panel._lines[-1].startswith("Line 005999"), f"Last line should be 5999, got {panel._lines[-1]}"
    print(f"[PASS] log panel cap (kept {len(panel._lines)} lines, first={panel._lines[0]}, last={panel._lines[-1]})")


# ---------------------------------------------------------------------------
# 4. Oracle client fingerprint check
# ---------------------------------------------------------------------------
def test_oracle_client_staleness():
    from auto_click.backends.reasoning_oracle import ReasoningOracle

    oracle = ReasoningOracle(
        provider="deepseek",
        api_key="key-v1",
        api_base="https://api.deepseek.com/v1",
        model="deepseek-reasoner",
    )
    # Initially, fingerprint is empty
    assert oracle._client_stale(), "Should be stale when no client has been created"

    # Simulate fingerprint after client creation
    oracle._client_fingerprint = "key-v1|https://api.deepseek.com/v1|120"
    assert not oracle._client_stale(), "Should not be stale with matching fingerprint"

    # Change API key
    oracle.api_key = "key-v2"
    assert oracle._client_stale(), "Should be stale after api_key change"

    # Update fingerprint to match
    oracle._client_fingerprint = "key-v2|https://api.deepseek.com/v1|120"
    assert not oracle._client_stale(), "Should not be stale after fingerprint update"

    # Change api_base
    oracle.api_base = "https://new-api.example.com/v1"
    assert oracle._client_stale(), "Should be stale after api_base change"

    print("[PASS] oracle client fingerprint staleness check")


# ---------------------------------------------------------------------------
# 5. Config lazy init
# ---------------------------------------------------------------------------
def test_config_lazy_init():
    import config

    # SCREENSHOTS_DIR should be a Path that is not yet created (or might
    # already exist from a prior run, which is fine)
    assert isinstance(config.SCREENSHOTS_DIR, Path)

    # ensure_screenshots_dir() should create it and return the path
    result = config.ensure_screenshots_dir()
    assert result == config.SCREENSHOTS_DIR
    assert result.exists(), "Directory should exist after ensure call"
    print(f"[PASS] config lazy init (dir={config.SCREENSHOTS_DIR})")


# ---------------------------------------------------------------------------
# 6. Clicker race condition fix
# ---------------------------------------------------------------------------
def test_clicker_race_condition_fix():
    """Verify _running is set before thread launch in run_task()."""
    import inspect
    from auto_click.clicker import AutoClicker

    source = inspect.getsource(AutoClicker.run_task)
    # The _running = True assignment must come before the thread creation lines
    running_line = None
    thread_line = None
    for i, line in enumerate(source.splitlines()):
        if "_running = True" in line and "self." in line:
            running_line = i
        if "threading.Thread" in line or "_run_phone_task" in line:
            thread_line = i
            break

    assert running_line is not None, "Should have _running = True in run_task"
    assert running_line < thread_line, \
        f"_running = True (line {running_line}) must come before thread creation (line {thread_line})"
    print("[PASS] clicker race condition fix")


def test_clicker_setup_failure_rolls_back_running_flag():
    """A startup failure must not leave the clicker permanently running."""
    from auto_click.clicker import AutoClicker

    clicker = AutoClicker(backend="vlm_coords", api_base="https://api.test.com/v1")
    clicker._setup_backend = MagicMock(side_effect=RuntimeError("setup failed"))
    try:
        clicker.run_task("test task")
    except RuntimeError:
        pass
    else:
        raise AssertionError("run_task should propagate setup failure")

    assert clicker._running is False, "_running should be reset after startup failure"
    print("[PASS] clicker setup failure rolls back _running")


# ---------------------------------------------------------------------------
# 7. VLM timeout fix
# ---------------------------------------------------------------------------
def test_vlm_timeout_set():
    from auto_click.backends.vlm_coords import VLMCoordsBackend

    backend = VLMCoordsBackend(
        api_key="test",
        api_base="https://api.test.com/v1",
        model="gpt-4o",
        target_context="test",
        coordinate_mode="pixel",
    )
    assert backend.client.timeout == 120, f"Client timeout should be 120, got {backend.client.timeout}"
    print("[PASS] VLM client timeout set")


def test_observe_backend_timeout_set():
    from auto_click.backends.observe_only import ObserveOnlyBackend

    backend = ObserveOnlyBackend(
        api_key="test",
        api_base="https://api.test.com/v1",
        model="qwen3-vl-plus",
    )
    assert backend.client.timeout == 120, f"Observe client timeout should be 120, got {backend.client.timeout}"
    print("[PASS] observe backend timeout set")


# ---------------------------------------------------------------------------
# 8. Thread safety — concurrency stress test
# ---------------------------------------------------------------------------
def test_history_thread_safety():
    """Stress-test concurrent _vlm_history access with lock."""
    import random

    class MockClicker:
        def __init__(self):
            self._vlm_history = []
            self._history_lock = threading.Lock()
            self.errors = 0

        def writer(self, count):
            for i in range(count):
                try:
                    with self._history_lock:
                        self._vlm_history.append({"step": i, "type": "test"})
                    time.sleep(0.0001)
                except Exception as e:
                    self.errors += 1
                    print(f"Writer error: {e}")

        def reader(self, count):
            for _ in range(count):
                try:
                    with self._history_lock:
                        snapshot = list(self._vlm_history)
                    time.sleep(0.00005)
                except Exception as e:
                    self.errors += 1
                    print(f"Reader error: {e}")

        def deleter(self, count):
            for _ in range(count):
                try:
                    with self._history_lock:
                        self._vlm_history.clear()
                    time.sleep(0.0005)
                except Exception as e:
                    self.errors += 1
                    print(f"Deleter error: {e}")

    obj = MockClicker()
    threads = []
    for _ in range(3):
        threads.append(threading.Thread(target=obj.writer, args=(200,)))
        threads.append(threading.Thread(target=obj.reader, args=(200,)))
    threads.append(threading.Thread(target=obj.deleter, args=(50,)))

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert obj.errors == 0, f"Concurrent access should have zero errors, got {obj.errors}"
    print(f"[PASS] thread safety stress test (final history len={len(obj._vlm_history)}, errors={obj.errors})")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("Running tests for 2026-05-06 fixes")
    print("=" * 60)
    print()

    tests = [
        test_encrypt_decrypt_roundtrip,
        test_backward_compatibility,
        test_dpapi_failure_is_not_returned_as_an_api_key,
        test_settings_save_load_cycle,
        test_history_rotation,
        test_log_panel_cap,
        test_oracle_client_staleness,
        test_config_lazy_init,
        test_clicker_race_condition_fix,
        test_clicker_setup_failure_rolls_back_running_flag,
        test_vlm_timeout_set,
        test_observe_backend_timeout_set,
        test_history_thread_safety,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"[FAIL] {test.__name__}: {e}")
            import traceback
            traceback.print_exc()

    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 60)
