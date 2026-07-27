"""Focused regression tests for the Windows desktop automation runtime."""
from __future__ import annotations

import base64
import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class DesktopActionExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        from auto_click.executor import ActionExecutor

        self.executor_type = ActionExecutor
        self.bounds = patch.object(
            ActionExecutor,
            "_virtual_screen_bounds",
            return_value=(-2000, -1000, 6000, 4000),
        )
        self.bounds.start()
        self.addCleanup(self.bounds.stop)

    def test_region_click_is_translated_but_callback_stays_local(self) -> None:
        seen: list[dict] = []
        executor = self.executor_type(forbidden_rects=[])
        executor.set_coordinate_frame(
            {
                "mode": "region",
                "left": 100,
                "top": 200,
                "width": 400,
                "height": 300,
                "source_width": 400,
                "source_height": 300,
            }
        )
        executor.set_confirm_callback(lambda action: seen.append(action) or True)

        with patch("auto_click.executor.pyautogui") as gui:
            executor.execute({"type": "click", "x": 10, "y": 20})

        self.assertEqual((10, 20), (seen[0]["x"], seen[0]["y"]))
        gui.click.assert_called_once_with(110, 220, button="left")

    def test_scaled_capture_coordinates_map_to_physical_frame(self) -> None:
        executor = self.executor_type()
        executor.set_coordinate_frame(
            {
                "mode": "window",
                "left": 100,
                "top": 200,
                "width": 200,
                "height": 100,
                "source_width": 100,
                "source_height": 50,
            }
        )

        with patch("auto_click.executor.pyautogui") as gui:
            executor.execute({"type": "move", "x": 50, "y": 25})

        gui.moveTo.assert_called_once_with(200, 250, duration=0.0)

    def test_forbidden_zone_is_checked_in_screenshot_coordinates(self) -> None:
        from auto_click.forbidden_zones import ForbiddenClickError

        executor = self.executor_type(
            forbidden_rects=[{"x1": 5, "y1": 5, "x2": 20, "y2": 20}]
        )
        executor.set_coordinate_frame(
            {
                "mode": "region",
                "left": 1200,
                "top": 700,
                "width": 200,
                "height": 200,
                "source_width": 200,
                "source_height": 200,
            }
        )

        with self.assertRaises(ForbiddenClickError):
            executor.execute({"type": "click", "x": 10, "y": 10})

    def test_drag_start_and_end_are_both_translated(self) -> None:
        executor = self.executor_type()
        executor.set_coordinate_frame(
            {
                "mode": "region",
                "left": 100,
                "top": 200,
                "width": 300,
                "height": 300,
                "source_width": 300,
                "source_height": 300,
            }
        )

        with patch("auto_click.executor.pyautogui") as gui:
            executor.execute(
                {
                    "type": "drag",
                    "x1": 10,
                    "y1": 20,
                    "x2": 30,
                    "y2": 40,
                }
            )

        gui.moveTo.assert_called_once_with(110, 220)
        gui.dragTo.assert_called_once_with(
            130,
            240,
            duration=0.3,
            button="left",
        )

    def test_unicode_text_uses_clipboard_paste(self) -> None:
        executor = self.executor_type()
        clipboard = SimpleNamespace(
            paste=MagicMock(return_value="before"),
            copy=MagicMock(),
        )
        with (
            patch.dict(sys.modules, {"pyperclip": clipboard}),
            patch("auto_click.executor.pyautogui") as gui,
            patch("auto_click.executor.time.sleep"),
        ):
            executor.execute({"type": "type", "text": "中文输入"})

        self.assertEqual("中文输入", clipboard.copy.call_args_list[0].args[0])
        self.assertEqual("before", clipboard.copy.call_args_list[-1].args[0])
        gui.hotkey.assert_called_once_with("ctrl", "v")
        gui.write.assert_not_called()


class DesktopCaptureLoopTests(unittest.TestCase):
    def test_clicker_refreshes_selected_capture_and_executor_frame(self) -> None:
        from auto_click.clicker import AutoClicker

        frame = {
            "mode": "region",
            "left": 300,
            "top": 400,
            "width": 80,
            "height": 60,
            "source_width": 80,
            "source_height": 60,
        }
        image = Image.new("RGB", (80, 60), "white")
        callback = MagicMock()
        clicker = AutoClicker(
            backend="zhipu_desktop",
            desktop_capture={
                "mode": "region",
                "left": 300,
                "top": 400,
                "width": 80,
                "height": 60,
            },
            on_screenshot=callback,
        )
        clicker._executor = MagicMock()

        with patch(
            "windows.capture.capture_desktop",
            return_value=(image, frame),
        ):
            encoded = clicker._capture_screenshot_b64()

        decoded = Image.open(io.BytesIO(base64.b64decode(encoded)))
        self.assertEqual((80, 60), decoded.size)
        clicker._executor.set_coordinate_frame.assert_called_once_with(frame)
        callback.assert_called_once()

    def test_normalized_desktop_model_action_becomes_screenshot_pixels(self) -> None:
        from auto_click.backends.vlm_coords import VLMCoordsBackend

        backend = VLMCoordsBackend(
            api_key="test",
            api_base="https://example.test/v1",
            model="test-model",
            target_context="a Windows desktop screenshot",
            coordinate_mode="normalized_1000",
            normalized_output_to_pixels=True,
        )
        converted = backend._convert_output_coordinates(
            {"type": "drag", "x1": 250, "y1": 250, "x2": 750, "y2": 750},
            (800, 600),
        )
        self.assertEqual(
            {"type": "drag", "x1": 200, "y1": 150, "x2": 600, "y2": 450},
            converted,
        )

    def test_unrelated_task_does_not_receive_arbitrary_skills(self) -> None:
        from auto_click.model_skills import ModelSkillLibrary

        library = ModelSkillLibrary()
        with patch.object(library, "_forced_skill_names", return_value=set()):
            context = library.relevant_context("zephyr quartz nebula")
        self.assertEqual("", context)


if __name__ == "__main__":
    unittest.main(verbosity=2)
