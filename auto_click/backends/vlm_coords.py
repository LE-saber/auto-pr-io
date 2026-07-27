"""Generic OpenAI-compatible VLM backend that returns one JSON action."""
from __future__ import annotations

import base64
import io
import json
import logging
import re

from openai import OpenAI
from PIL import Image

logger = logging.getLogger(__name__)


class VLMCoordsBackend:
    """Fallback for models that can inspect screenshots but do not own a tool loop."""

    def __init__(
        self,
        api_key: str,
        api_base: str,
        model: str,
        target_context: str = "a Windows desktop",
        coordinate_mode: str = "pixel",
        normalized_output_to_pixels: bool = False,
    ):
        self.client = OpenAI(api_key=api_key or "unused", base_url=api_base, timeout=120)
        self.model = model
        self.target_context = target_context
        self.coordinate_mode = coordinate_mode
        self.normalized_output_to_pixels = normalized_output_to_pixels
        from auto_click.model_skills import ModelSkillLibrary

        self.skill_library = ModelSkillLibrary()

    def reset(self) -> None:
        pass

    def get_next_action(
        self,
        task: str,
        screenshot_b64: str,
        action_history: list[dict] | None = None,
    ) -> dict:
        history = self._compact_history(action_history or [])
        screenshot_size = self._screenshot_size(screenshot_b64)
        prompt = self._build_prompt(task, history, screenshot_size)
        content = self._request_action(prompt, screenshot_b64)
        try:
            action = self._parse_action(content)
            return self._convert_output_coordinates(action, screenshot_size)
        except ValueError as exc:
            logger.warning("VLM action parse failed, retrying with stricter prompt: %s", exc)
            retry_prompt = (
                self._build_prompt(
                    task,
                    self._compact_history(action_history or [], for_retry=True),
                    screenshot_size,
                )
                + "\n\nYour previous answer was invalid. Return exactly one non-empty JSON object now. "
                + 'Do not return "{}". Example: {"type":"click","x":500,"y":500}. '
                + 'Never write coordinates as {"x":750,910}; use {"x":750,"y":910}.'
            )
            content = self._request_action(retry_prompt, screenshot_b64)
            try:
                action = self._parse_action(content)
                return self._convert_output_coordinates(action, screenshot_size)
            except ValueError as retry_exc:
                logger.error("VLM action parse failed after retry: %s", retry_exc)
                return {"type": "wait", "seconds": 1, "reason": "invalid_vlm_response"}

    def _build_prompt(
        self,
        task: str,
        history: str,
        screenshot_size: tuple[int, int] | None = None,
    ) -> str:
        skill_context = self.skill_library.relevant_context(
            f"{self.target_context}\n{task}\n{history}"
        )
        if skill_context:
            skill_names = re.findall(r"^Skill: (.+)$", skill_context, flags=re.M)
            logger.info(
                "VLM skills injected: %s (%d chars)",
                ", ".join(skill_names) if skill_names else "unknown",
                len(skill_context),
            )
        skill_block = f"\nRelevant skills:\n{skill_context}\n" if skill_context else ""
        coordinate_instruction = (
            (
                "Coordinates must be integer screenshot pixel coordinates. "
                + (
                    f"The screenshot is exactly {screenshot_size[0]}x{screenshot_size[1]} pixels; "
                    f"valid x is 0..{screenshot_size[0] - 1} and valid y is 0..{screenshot_size[1] - 1}. "
                    if screenshot_size
                    else ""
                )
            )
            if self.coordinate_mode == "pixel"
            else (
                "Coordinates must use a normalized 1000x1000 coordinate system: "
                "top-left is x=0,y=0; bottom-right is x=1000,y=1000. "
                "The runtime will map these normalized coordinates to the exact supplied screenshot."
            )
        )
        phone_instruction = ""
        if "Android" in self.target_context:
            phone_instruction = (
                "This is an Android phone controlled through ADB. Choose the next UI action from the screenshot. "
                "If the task is unclear but the UI is visible, return a safe wait or screenshot action instead of an empty object. "
                "You can use back/home for Android navigation. "
            )
        desktop_instruction = ""
        if "Windows" in self.target_context:
            desktop_instruction = (
                "The supplied image is the exact desktop target: it may be a full monitor, a cropped region, "
                "or one window. Coordinates are always relative to this image, with its top-left at (0,0). "
                "Never add a monitor, window, or crop offset yourself. "
                "For scroll actions, amount is a small wheel-notch count from 1 to 8, not a pixel distance. "
            )
        scroll_amount = 5 if "Windows" in self.target_context else 300
        return (
            f"You are controlling {self.target_context} by returning exactly one JSON action. "
            f"{phone_instruction}{desktop_instruction}"
            "Allowed actions: click, double_click, move, drag, type, key, scroll, wait, screenshot, done, ask_oracle, enable_keyboard, listen_audio. "
            "For click actions include exactly two integer fields named x and y. "
            "Never put two numbers after x; invalid: {\"type\":\"click\",\"x\":750,910}. "
            "Valid: {\"type\":\"click\",\"x\":750,\"y\":910}. "
            "For type include text. For key include keys as an array, for example {\"type\":\"key\",\"keys\":[\"ENTER\"]}. "
            "For scroll include x, y, direction and amount. "
            "For drag include screenshot-relative start and end coordinates as x1, y1, x2, y2. "
            f"{coordinate_instruction} "
            "If the goal requires hearing audio, a voice message, spoken instructions, a listening question, "
            "or the content behind a speaker/play button, do not guess from the image and do not keep tapping "
            "the same play button. If audio is already playing, return listen_audio. If playback must be started, "
            "click the play/speaker button once, then return listen_audio on the next step. "
            "For any listening/speech-to-text question, you must obtain and use an ASR transcript before selecting "
            "an answer, filling text, or submitting. If no transcript is available yet, return wait or listen_audio. "
            "When an audio_transcript appears in the recent action summary or task context, use that transcript "
            "to answer the visible question or choose the closest visible option. Do not return done unless the "
            "screen clearly shows the task is complete. "
            "The JSON object must always contain a non-empty type field. Never return {}. "
            "Valid examples: "
            "{\"type\":\"click\",\"x\":500,\"y\":500}; "
            "{\"type\":\"type\",\"text\":\"hello\"}; "
            "{\"type\":\"enable_keyboard\"}; "
            "{\"type\":\"listen_audio\",\"duration\":5,\"question\":\"what is being said\"}; "
            f'{{"type":"scroll","x":500,"y":700,"direction":"down","amount":{scroll_amount}}}; '
            "{\"type\":\"drag\",\"x1\":200,\"y1\":300,\"x2\":600,\"y2\":300,\"duration\":0.5}; "
            "{\"type\":\"wait\",\"seconds\":1}; "
            "{\"type\":\"done\"}. "
            "If you see a complex mathematical, logical, or reasoning problem on screen "
            "(competition math, olympiad problems, proofs, complex derivations) that you "
            "cannot solve reliably, return: "
            '{"type": "ask_oracle", "question": "<full problem description>"}. '
            "The oracle answer will be injected into the next step as context. "
            "Output only one valid JSON object. Do not output explanations, markdown, code fences, or an empty object.\n"
            "Return JSON only, no markdown.\n"
            f"{skill_block}"
            f"Task: {task}\n"
            f"Recent action summary: {history}\n"
            f"FINAL COORDINATE CONTRACT (overrides examples in skills): {coordinate_instruction}"
        )

    @staticmethod
    def _screenshot_size(screenshot_b64: str) -> tuple[int, int] | None:
        try:
            with Image.open(io.BytesIO(base64.b64decode(screenshot_b64))) as image:
                return int(image.width), int(image.height)
        except Exception:
            logger.debug("Unable to read screenshot dimensions", exc_info=True)
            return None

    def _convert_output_coordinates(
        self,
        action: dict,
        screenshot_size: tuple[int, int] | None,
    ) -> dict:
        if (
            self.coordinate_mode != "normalized_1000"
            or not self.normalized_output_to_pixels
            or screenshot_size is None
        ):
            return action

        width, height = screenshot_size
        converted = dict(action)
        pairs = (
            ("x", "y"),
            ("x1", "y1"),
            ("x2", "y2"),
            ("from_x", "from_y"),
            ("to_x", "to_y"),
        )
        for x_field, y_field in pairs:
            if x_field not in action or y_field not in action:
                continue
            converted[x_field] = self._normalized_axis(action[x_field], width)
            converted[y_field] = self._normalized_axis(action[y_field], height)

        path = action.get("path")
        if isinstance(path, list):
            converted["path"] = [
                {
                    **point,
                    "x": self._normalized_axis(point["x"], width),
                    "y": self._normalized_axis(point["y"], height),
                }
                for point in path
                if isinstance(point, dict) and "x" in point and "y" in point
            ]
        logger.info(
            "Converted normalized VLM action to screenshot pixels: %s -> %s",
            action,
            converted,
        )
        return converted

    @staticmethod
    def _normalized_axis(value: object, size: int) -> int:
        normalized = max(0.0, min(1000.0, float(value)))
        return min(size - 1, max(0, round(normalized / 1000.0 * size)))

    def _request_action(self, prompt: str, screenshot_b64: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a strict JSON action generator for GUI automation.",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"},
                        },
                    ],
                },
            ],
            temperature=0.1,
            max_tokens=1024,
            timeout=120,
        )
        choice = response.choices[0]
        content = choice.message.content or "{}"
        logger.info(
            "VLM response finish_reason=%s content=%s",
            getattr(choice, "finish_reason", ""),
            content[:500],
        )
        return content

    @staticmethod
    def _compact_history(action_history: list[dict], for_retry: bool = False) -> str:
        if not action_history:
            return (
                "retry after invalid JSON; choose one valid next action from the screenshot"
                if for_retry
                else "none"
            )
        items: list[str] = []
        for action in action_history[-8:]:
            atype = str(action.get("type", "?"))
            if atype == "audio_transcript":
                text = str(action.get("text", "")).strip()
                if len(text) > 220:
                    text = text[:220] + "..."
                items.append(f"audio_transcript: {text}")
            elif atype in {"click", "double_click"}:
                items.append(f"{atype}({action.get('x')},{action.get('y')})")
            elif atype == "type":
                text = str(action.get("text", ""))
                items.append(f"type({text[:80]!r})")
            elif atype in {"listen_audio", "analyze_audio", "transcribe_audio", "listen"}:
                items.append(f"listen_audio({action.get('duration', action.get('seconds', ''))}s)")
            elif atype in {"wait", "scroll", "key", "done", "ask_oracle"}:
                items.append(atype)
            else:
                items.append(atype)
        if for_retry:
            items.append("previous response was invalid JSON; return only one corrected JSON object")
        return "; ".join(items)

    @staticmethod
    def _parse_action(content: str) -> dict:
        text = content.strip()
        if text.startswith("```"):
            match = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
            if match:
                text = match.group(1).strip()
        if not text.startswith(("{", "[")):
            match = re.search(r"(\{.*\}|\[.*\])", text, re.S)
            if match:
                text = match.group(1).strip()
        text = VLMCoordsBackend._repair_common_json_coordinate_errors(text)
        action = json.loads(text)
        if isinstance(action, list):
            if not action:
                raise ValueError("VLM action response was an empty list.")
            action = action[0]
        if not isinstance(action, dict):
            raise ValueError("VLM action response must be a JSON object.")
        if "type" not in action and "action" in action:
            action["type"] = action.pop("action")
        if "type" not in action and "action_type" in action:
            action["type"] = action.pop("action_type")
        if "type" not in action and "element" in action:
            action["type"] = "click"
        if "type" not in action and "target" in action:
            action["type"] = "click"
        if "type" in action and isinstance(action["type"], str):
            action["type"] = action["type"].strip().lower()
        if action.get("type") == "tap":
            action["type"] = "click"
        if action.get("type") in {"finish", "finished", "complete", "completed"}:
            action["type"] = "done"
        VLMCoordsBackend._normalize_point_fields(action)
        if "type" not in action:
            logger.warning("VLM action missing type. Raw response: %s", content[:500])
            raise ValueError("VLM action response missing 'type'.")
        return action

    @staticmethod
    def _repair_common_json_coordinate_errors(text: str) -> str:
        """Repair common VLM coordinate slips before strict JSON parsing.

        Qwen occasionally emits click points as ``"x":750,910`` where the
        second number is the intended y coordinate. Keep this deliberately
        narrow so unrelated malformed JSON still fails visibly.
        """
        if '"x"' not in text or re.search(r'"y"\s*:', text):
            repaired = re.sub(
                r'("x"\s*:\s*-?\d+(?:\.\d+)?)\s*,\s*-?\d+(?:\.\d+)?\s*,\s*("y"\s*:)',
                r"\1,\2",
                text,
            )
            if repaired != text:
                logger.warning("Repaired malformed x/y coordinate JSON: %s -> %s", text[:200], repaired[:200])
            return repaired

        repaired = re.sub(
            r'("x"\s*:\s*(-?\d+(?:\.\d+)?))\s*,\s*(-?\d+(?:\.\d+)?)(\s*[}\]])',
            r'\1,"y":\3\4',
            text,
            count=1,
        )
        if repaired != text:
            logger.warning("Repaired missing y coordinate JSON: %s -> %s", text[:200], repaired[:200])
        return repaired

    @staticmethod
    def _normalize_point_fields(action: dict) -> None:
        if "x" in action and "y" in action:
            return
        for field in ("element", "point", "position", "coordinate", "coordinates", "target"):
            value = action.get(field)
            if not isinstance(value, list) or not value:
                continue
            coords = value[0] if isinstance(value[0], list) else value
            if len(coords) == 2:
                action["x"] = int(float(coords[0]))
                action["y"] = int(float(coords[1]))
                return
            if len(coords) == 4:
                x1, y1, x2, y2 = coords
                action["x"] = (int(float(x1)) + int(float(x2))) // 2
                action["y"] = (int(float(y1)) + int(float(y2))) // 2
                return
