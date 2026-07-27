"""Reasoning oracle backend used by automation loops for hard subproblems."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ReasoningOracle:
    """Small wrapper around reasoning-oriented LLM providers."""

    _DEFAULT_API_BASE = {
        "deepseek": "https://api.deepseek.com/v1",
        "openai": "https://api.openai.com/v1",
        "anthropic": "",
        "zhipu": "https://open.bigmodel.cn/api/paas/v4",
        "qwen_vl": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "volcengine": "https://ark.cn-beijing.volces.com/api/v3",
        "custom": "",
    }
    _DEFAULT_MODEL = {
        "deepseek": "deepseek-reasoner",
        "openai": "o3-mini",
        "anthropic": "claude-opus-4-6",
        "zhipu": "glm-4.6v-flashx",
        "qwen_vl": "qwen3-vl-plus",
        "volcengine": "doubao-seed-2-0-lite-260215",
        "custom": "",
    }
    _SYSTEM_PROMPT = (
        "You are a powerful reasoning assistant. Solve the given problem step by step. "
        "Show your work for math problems. Provide a clear, concise final answer."
    )

    def __init__(
        self,
        provider: str = "deepseek",
        api_key: str = "",
        api_base: str = "",
        model: str = "",
        timeout: int = 120,
    ):
        self.provider = (provider or "deepseek").lower()
        if self.provider not in self._DEFAULT_API_BASE:
            raise ValueError(f"Unknown oracle provider: {provider!r}")
        self.api_key = api_key
        self.api_base = api_base or self._DEFAULT_API_BASE[self.provider]
        self.model = model or self._DEFAULT_MODEL[self.provider]
        self.timeout = timeout
        self._client = None
        self._client_fingerprint = ""

    def ask(self, question: str, context: str = "",
            image_b64: str = "") -> str:
        """Ask the oracle a question, optionally with a screenshot.

        Parameters
        ----------
        question:   The problem description or question to solve.
        context:    Optional extra context (task description, prior steps, etc.).
        image_b64:  Base-64 encoded PNG screenshot.  When provided and the
                    model supports vision, the image is sent alongside the text.
        """
        user_text = question
        if context:
            user_text = f"Context:\n{context}\n\nQuestion:\n{question}"
        logger.info("[Oracle] %s/%s — %s", self.provider, self.model, question[:100])
        try:
            image_b64 = image_b64 if self._supports_vision() else ""
            if self.provider == "anthropic":
                return self._ask_anthropic(user_text, image_b64)
            return self._ask_openai_compatible(user_text, image_b64)
        except Exception as exc:
            logger.exception("[Oracle] request failed")
            return f"ERROR: Oracle request failed: {exc}"

    def _supports_vision(self) -> bool:
        """Return whether this oracle provider/model should receive image blocks."""
        if self.provider == "deepseek":
            return False
        model = (self.model or "").lower()
        if self.provider == "openai":
            return any(token in model for token in ("gpt-4", "gpt-5", "o4", "vision"))
        if self.provider == "anthropic":
            return True
        if self.provider == "zhipu":
            return any(token in model for token in ("glm-4v", "glm-4.6v", "vision"))
        if self.provider == "qwen_vl":
            return "vl" in model
        if self.provider == "volcengine":
            return any(token in model for token in ("doubao", "vision", "seed"))
        return any(token in model for token in ("vision", "vl", "4v", "4.6v", "image", "multimodal"))

    @staticmethod
    def _build_user_content(user_text: str, image_b64: str) -> object:
        """Return either a plain string or a multimodal content list."""
        if not image_b64:
            return user_text
        return [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{image_b64}"},
            },
            {"type": "text", "text": user_text},
        ]

    def _client_stale(self) -> bool:
        return self._client_fingerprint != f"{self.api_key}|{self.api_base}|{self.timeout}"

    def _ask_openai_compatible(self, user_text: str, image_b64: str) -> str:
        if self._client is None or self._client_stale():
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.api_key or None,
                base_url=self.api_base or None,
                timeout=self.timeout,
            )
            self._client_fingerprint = f"{self.api_key}|{self.api_base}|{self.timeout}"
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self._SYSTEM_PROMPT},
                {"role": "user", "content": self._build_user_content(user_text, image_b64)},
            ],
        )
        return response.choices[0].message.content or ""

    def _ask_anthropic(self, user_text: str, image_b64: str) -> str:
        if self._client is None or self._client_stale():
            import anthropic

            kwargs = {"api_key": self.api_key or None, "timeout": self.timeout}
            if self.api_base:
                kwargs["base_url"] = self.api_base
            self._client = anthropic.Anthropic(**kwargs)
            self._client_fingerprint = f"{self.api_key}|{self.api_base}|{self.timeout}"

        if image_b64:
            content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_b64,
                    },
                },
                {"type": "text", "text": user_text},
            ]
        else:
            content = user_text

        response = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=self._SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
        parts: list[str] = []
        for block in response.content:
            text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
            if text:
                parts.append(str(text))
        return "\n".join(parts)
