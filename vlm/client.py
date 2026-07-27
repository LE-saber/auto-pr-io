from __future__ import annotations

import base64
import io
import logging

from PIL import Image

from vlm.models import VLMConfig

logger = logging.getLogger(__name__)


class VLMClient:
    """Thin wrapper around multiple VLM provider SDKs."""

    def send_image(self, image: Image.Image, prompt: str, config: VLMConfig) -> str:
        """Send *image* + *prompt* to the VLM specified by *config*.
        Returns the response text string.
        """
        b64 = self._image_to_base64(image)
        dispatch = {
            'openai': self._call_openai,
            'anthropic': self._call_anthropic,
            'zhipu': self._call_zhipu,
            'qwen_vl': self._call_openai_compatible,
            'volcengine': self._call_openai_compatible,
            'custom': self._call_custom,
        }
        handler = dispatch.get(config.provider)
        if handler is None:
            raise ValueError(f"Unsupported provider: {config.provider}")
        return handler(b64, prompt, config)

    @staticmethod
    def _image_to_base64(image: Image.Image) -> str:
        buf = io.BytesIO()
        if image.mode not in ('RGB', 'L'):
            image = image.convert('RGB')
        image.save(buf, format='PNG')
        return base64.b64encode(buf.getvalue()).decode('utf-8')

    # ------------------------------------------------------------------
    def _call_openai(self, b64: str, prompt: str, cfg: VLMConfig) -> str:
        from openai import OpenAI
        client = OpenAI(
            api_key=cfg.api_key or None,
            base_url=cfg.api_base or None,
            timeout=cfg.timeout,
        )
        response = client.chat.completions.create(
            model=cfg.effective_model(),
            messages=[{
                'role': 'user',
                'content': [
                    {'type': 'image_url',
                     'image_url': {'url': f'data:image/png;base64,{b64}'}},
                    {'type': 'text', 'text': prompt},
                ],
            }],
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
        )
        return response.choices[0].message.content or ''

    def _call_anthropic(self, b64: str, prompt: str, cfg: VLMConfig) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=cfg.api_key or None, timeout=cfg.timeout)
        response = client.messages.create(
            model=cfg.effective_model(),
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
            messages=[{
                'role': 'user',
                'content': [
                    {'type': 'image',
                     'source': {'type': 'base64', 'media_type': 'image/png', 'data': b64}},
                    {'type': 'text', 'text': prompt},
                ],
            }],
        )
        return '\n'.join(
            block.text for block in response.content if block.type == 'text'
        )

    def _call_zhipu(self, b64: str, prompt: str, cfg: VLMConfig) -> str:
        from zhipuai import ZhipuAI
        client = ZhipuAI(api_key=cfg.api_key or None)
        response = client.chat.completions.create(
            model=cfg.effective_model(),
            messages=[{
                'role': 'user',
                'content': [
                    {'type': 'image_url',
                     'image_url': {'url': f'data:image/png;base64,{b64}'}},
                    {'type': 'text', 'text': prompt},
                ],
            }],
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
        )
        return response.choices[0].message.content or ''

    def _call_custom(self, b64: str, prompt: str, cfg: VLMConfig) -> str:
        return self._call_openai_compatible(b64, prompt, cfg)

    def _call_openai_compatible(self, b64: str, prompt: str, cfg: VLMConfig) -> str:
        from openai import OpenAI
        if not cfg.api_base:
            raise ValueError(f"{cfg.provider} provider requires 'api_base' to be set")
        model = cfg.effective_model()
        if not model:
            raise ValueError(f"{cfg.provider} provider requires 'model' to be set")
        client = OpenAI(
            api_key=cfg.api_key or 'unused',
            base_url=cfg.api_base,
            timeout=cfg.timeout,
        )
        response = client.chat.completions.create(
            model=model,
            messages=[{
                'role': 'user',
                'content': [
                    {'type': 'image_url',
                     'image_url': {'url': f'data:image/png;base64,{b64}'}},
                    {'type': 'text', 'text': prompt},
                ],
            }],
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
        )
        return response.choices[0].message.content or ''
