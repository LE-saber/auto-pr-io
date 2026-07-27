from dataclasses import dataclass, field
from typing import Optional

PROVIDER_DEFAULTS = {
    'openai': {
        'models': ['gpt-4o', 'gpt-4-turbo', 'gpt-4-vision-preview'],
        'default': 'gpt-4o',
    },
    'anthropic': {
        'models': ['claude-3-5-sonnet-20241022', 'claude-3-opus-20240229'],
        'default': 'claude-3-5-sonnet-20241022',
    },
    'zhipu': {
        'models': ['glm-4.6v-flashx', 'glm-4v-plus', 'glm-4v'],
        'default': 'glm-4.6v-flashx',
    },
    'qwen_vl': {
        'models': ['qwen3-vl-plus', 'qwen3-vl-32b'],
        'default': 'qwen3-vl-plus',
    },
    'volcengine': {
        'models': ['doubao-seed-2-0-lite-260215'],
        'default': 'doubao-seed-2-0-lite-260215',
    },
    'custom': {
        'models': [],
        'default': '',
    },
}


@dataclass
class VLMConfig:
    provider: str = 'openai'
    model: str = 'gpt-4o'
    api_key: str = ''
    api_base: str = ''
    temperature: float = 0.2
    max_tokens: int = 2048
    timeout: int = 60

    @classmethod
    def from_config(cls, provider: Optional[str] = None) -> 'VLMConfig':
        """Create a VLMConfig populated with defaults from config.py."""
        import config as cfg

        provider = provider or 'openai'
        defaults = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS['openai'])
        model = defaults['default']

        api_key = ''
        api_base = ''
        if provider == 'openai':
            api_key = getattr(cfg, 'OPENAI_API_KEY', '')
        elif provider == 'anthropic':
            api_key = getattr(cfg, 'ANTHROPIC_API_KEY', '')
        elif provider == 'zhipu':
            api_key = getattr(cfg, 'ZHIPU_API_KEY', '')
        elif provider == 'qwen_vl':
            api_key = getattr(cfg, 'DASHSCOPE_API_KEY', '')
            api_base = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
        elif provider == 'volcengine':
            api_key = getattr(cfg, 'VOLCENGINE_API_KEY', '')
            api_base = getattr(
                cfg,
                'VOLCENGINE_API_BASE',
                'https://ark.cn-beijing.volces.com/api/v3',
            )
        elif provider == 'custom':
            api_key = getattr(cfg, 'CUSTOM_API_KEY', '')
            api_base = getattr(cfg, 'CUSTOM_API_BASE', '')

        temperature = getattr(cfg, 'DEFAULT_TEMPERATURE', 0.2)
        max_tokens = getattr(cfg, 'DEFAULT_MAX_TOKENS', 2048)
        timeout = getattr(cfg, 'DEFAULT_TIMEOUT', 60)

        return cls(
            provider=provider,
            model=model,
            api_key=api_key,
            api_base=api_base,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )

    def effective_model(self) -> str:
        """Return the model name, falling back to the provider default if empty."""
        if self.model:
            return self.model
        defaults = PROVIDER_DEFAULTS.get(self.provider, {})
        return defaults.get('default', '')
