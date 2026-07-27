"""
Global configuration for auto-pr-io.
Values can be overridden via .env or environment variables.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
SCREENSHOTS_DIR = BASE_DIR / "Screenshots"


def ensure_screenshots_dir() -> Path:
    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    return SCREENSHOTS_DIR

PROMPTS_FILE = BASE_DIR / "vlm" / "prompt_templates.json"
SETTINGS_FILE = BASE_DIR / "settings.json"

# ---------- VLM defaults ----------
DEFAULT_PROVIDER = os.getenv("VLM_PROVIDER", "openai")
DEFAULT_MODEL = os.getenv("VLM_MODEL", "gpt-4o")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY", "")
DASHSCOPE_API_KEY = os.getenv(
    "DASHSCOPE_API_KEY",
    os.getenv("QWEN_API_KEY", ""),
)
VOLCENGINE_API_KEY = os.getenv(
    "ARK_API_KEY",
    os.getenv("VOLCENGINE_API_KEY", ""),
)
VOLCENGINE_API_BASE = os.getenv(
    "VOLCENGINE_API_BASE",
    "https://ark.cn-beijing.volces.com/api/v3",
)
VOLCENGINE_MODEL = os.getenv(
    "VOLCENGINE_MODEL",
    "doubao-seed-2-0-lite-260215",
)

CUSTOM_API_BASE = os.getenv("CUSTOM_API_BASE", "")
CUSTOM_API_KEY = os.getenv("CUSTOM_API_KEY", "")
CUSTOM_MODEL = os.getenv("CUSTOM_MODEL", "")

DEFAULT_TEMPERATURE = float(os.getenv("VLM_TEMPERATURE", "0.2"))
DEFAULT_MAX_TOKENS = int(os.getenv("VLM_MAX_TOKENS", "2048"))
DEFAULT_TIMEOUT = int(os.getenv("VLM_TIMEOUT", "60"))

# ---------- UI ----------
APP_TITLE = "auto-pr-io · VLM Screen Analyzer"
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 850
THEME = "clam"  # ttk theme
