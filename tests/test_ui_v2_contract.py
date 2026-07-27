"""Contract tests for the independently redesigned GUI."""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class NewGUIContractTests(unittest.TestCase):
    def test_entrypoint_uses_only_new_application_shell(self) -> None:
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("from ui_v2 import MainWindow", source)
        self.assertNotIn("from ui.main_window", source)
        self.assertNotIn("sv_ttk", source)

    def test_new_gui_does_not_import_legacy_ui_package(self) -> None:
        for path in (ROOT / "ui_v2").glob("*.py"):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse(
                        node.module == "ui" or str(node.module).startswith("ui."),
                        f"{path.name} imports legacy frontend module {node.module}",
                    )
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertFalse(
                            alias.name == "ui" or alias.name.startswith("ui."),
                            f"{path.name} imports legacy frontend module {alias.name}",
                        )

    def test_all_literal_translation_keys_have_english_fallback(self) -> None:
        from ui_v2.i18n import EN

        used: set[str] = set()
        for path in (ROOT / "ui_v2").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                if not isinstance(node.func, ast.Attribute) or node.func.attr != "t":
                    continue
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    used.add(first.value)
        self.assertEqual(set(), used - set(EN), f"Missing translation keys: {sorted(used - set(EN))}")

    def test_translator_never_falls_back_to_simplified_chinese(self) -> None:
        from ui_v2.i18n import Translator

        expected = {
            "en": "Workspace",
            "ja": "ワークスペース",
            "zh-TW": "工作臺",
        }
        for language, workspace in expected.items():
            translator = Translator(language)
            self.assertEqual(workspace, translator("workspace"))
            self.assertEqual("unregistered_key", translator("unregistered_key"))

    def test_backend_routes_match_existing_clicker_contract(self) -> None:
        from ui_v2.backend import (
            DESKTOP_BACKENDS,
            backend_options,
            provider_for_backend,
        )

        self.assertEqual({"observe_adb"}, set(backend_options("android", "chat")))
        self.assertIn("cida_work", backend_options("android", "build"))
        self.assertEqual(
            {"zhipu_desktop", "volcengine_desktop", "qwen_desktop"},
            set(DESKTOP_BACKENDS),
        )
        self.assertEqual(set(DESKTOP_BACKENDS), set(backend_options("desktop", "build")))
        self.assertEqual("zhipu", provider_for_backend("zhipu_desktop"))
        self.assertEqual("volcengine", provider_for_backend("volcengine_desktop"))
        self.assertEqual("qwen_vl", provider_for_backend("qwen_desktop"))
        self.assertEqual("qwen_vl", provider_for_backend("cida_work"))
        self.assertEqual("zhipu", provider_for_backend("glm_adb"))

    def test_desktop_providers_are_prominent_in_settings(self) -> None:
        from ui_v2.settings import PROVIDERS

        self.assertEqual(
            ["zhipu", "volcengine", "qwen_vl"],
            [provider for provider, _label in PROVIDERS[:3]],
        )

    def test_backend_validation_requires_expected_settings(self) -> None:
        from ui_v2.backend import BackendBridge, RunRequest

        bridge = BackendBridge(lambda *_: None, lambda: [])
        request = RunRequest(
            target="android",
            work_mode="build",
            backend="cida_work",
            model="qwen3-vl-plus",
            task="complete exercise",
            device_id="serial",
        )
        with patch("ui_v2.backend.get_provider_settings", return_value={"api_key": "key", "api_base": "https://example.test/v1"}):
            bridge._validate(request)

    def test_skill_filename_accepts_cjk_and_rejects_windows_separators(self) -> None:
        from ui_v2.views import SkillsView

        self.assertEqual("听力练习.md", SkillsView._safe_filename("听力练习"))
        self.assertEqual("quiz-name.md", SkillsView._safe_filename("quiz/name"))

    def test_legacy_numeric_settings_are_migrated(self) -> None:
        from ui_v2.app import MainWindow

        self.assertEqual(3, MainWindow._coerce_int("3s", 5, 1, 30))
        self.assertEqual(1000, MainWindow._coerce_int("9000", 200, 1, 1000))
        self.assertEqual(5, MainWindow._coerce_int("invalid", 5, 1, 30))


if __name__ == "__main__":
    unittest.main(verbosity=2)
