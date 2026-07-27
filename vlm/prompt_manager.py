import json
from pathlib import Path
from typing import Optional


class PromptManager:
    BUILTIN_TEMPLATES = {
        'describe_ui': (
            'Please describe this UI screenshot in detail. '
            'What elements are visible? What is the application doing?'
        ),
        'find_button': (
            'In this screenshot, identify all clickable buttons or interactive elements. '
            'List their labels and approximate positions.'
        ),
        'analyze_screen': (
            'Analyze this screen. Summarize what is happening and what actions '
            'the user might want to take next.'
        ),
        'ocr_text': (
            'Extract all visible text from this screenshot. '
            'Preserve layout as much as possible.'
        ),
        'custom': '',
    }

    def __init__(self, templates_file: Optional[Path] = None):
        self._templates_file = templates_file
        self._custom_templates: dict[str, str] = {}
        self._load_custom_templates()

    def _load_custom_templates(self) -> None:
        if self._templates_file is None or not self._templates_file.exists():
            return
        try:
            with open(self._templates_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._custom_templates = {
                    k: v for k, v in data.items() if isinstance(v, str)
                }
        except (json.JSONDecodeError, OSError):
            self._custom_templates = {}

    def _save_custom_templates(self) -> None:
        if self._templates_file is None:
            return
        try:
            self._templates_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._templates_file, 'w', encoding='utf-8') as f:
                json.dump(self._custom_templates, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def get_template_names(self) -> list[str]:
        names = list(self.BUILTIN_TEMPLATES.keys())
        for name in self._custom_templates:
            if name not in self.BUILTIN_TEMPLATES:
                names.append(name)
        return names

    def get_template(self, name: str) -> str:
        if name in self._custom_templates:
            return self._custom_templates[name]
        if name in self.BUILTIN_TEMPLATES:
            return self.BUILTIN_TEMPLATES[name]
        raise KeyError(f"Template '{name}' not found")

    def save_template(self, name: str, content: str) -> None:
        self._custom_templates[name] = content
        self._save_custom_templates()

    def delete_template(self, name: str) -> None:
        if name in self.BUILTIN_TEMPLATES and name not in self._custom_templates:
            raise ValueError(f"Cannot delete built-in template '{name}'")
        if name not in self._custom_templates:
            raise KeyError(f"Template '{name}' not found")
        del self._custom_templates[name]
        self._save_custom_templates()

    def format_prompt(self, name: str, **kwargs) -> str:
        template = self.get_template(name)
        if not kwargs:
            return template

        class _SafeDict(dict):
            def __missing__(self, key):
                return f'{{{key}}}'

        return template.format_map(_SafeDict(**kwargs))

    def is_builtin(self, name: str) -> bool:
        return name in self.BUILTIN_TEMPLATES
