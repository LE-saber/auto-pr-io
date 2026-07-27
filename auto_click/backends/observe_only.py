"""Passive VLM observer backend for screen/audio note taking."""
from __future__ import annotations

import logging

from openai import OpenAI

logger = logging.getLogger(__name__)


class ObserveOnlyBackend:
    """OpenAI-compatible vision backend that returns user-facing notes, not actions."""

    def __init__(
        self,
        api_key: str,
        api_base: str,
        model: str,
        target_context: str = "an Android phone screen",
        timeout: int = 120,
    ):
        self.timeout = timeout
        self.client = OpenAI(api_key=api_key or "unused", base_url=api_base, timeout=timeout)
        self.model = model
        self.target_context = target_context

    def reset(self) -> None:
        pass

    def observe(
        self,
        task: str,
        screenshot_b64: str,
        audio_context: str = "",
        previous_notes: str = "",
    ) -> str:
        prompt = (
            f"You are passively observing {self.target_context}. "
            "You must not control the device, click, type, navigate, or return JSON actions. "
            "Your job is to help the user by reading the visible screen and any ASR transcript. "
            "If this is a class, course, meeting, livestream, video, or spoken Q&A, produce useful "
            "notes and answer user questions based only on what is visible or transcribed. "
            "If there is not enough new information, say so briefly instead of inventing details.\n\n"
            "User request:\n"
            f"{task}\n\n"
            "Recent ASR transcript:\n"
            f"{audio_context or '(none yet)'}\n\n"
            "Previous assistant notes:\n"
            f"{previous_notes or '(none yet)'}\n\n"
            "Return a concise user-facing update in the user's language. Prefer this structure when useful:\n"
            "- 新内容 / New content\n"
            "- 笔记 / Notes\n"
            "- 问答 / Q&A\n"
            "- 待确认 / Unclear\n"
        )
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a passive screen/audio observation assistant. "
                        "Never output GUI automation actions or JSON."
                    ),
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
            temperature=0.2,
            max_tokens=1200,
            timeout=self.timeout,
        )
        choice = response.choices[0]
        content = (choice.message.content or "").strip()
        logger.info(
            "Observe response finish_reason=%s content=%s",
            getattr(choice, "finish_reason", ""),
            content[:500],
        )
        return content or "暂无可整理的新内容。"
