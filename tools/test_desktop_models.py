"""Non-executing vision smoke test for the supported desktop model providers."""
from __future__ import annotations

import argparse
import base64
import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from auto_click.backends.vlm_coords import VLMCoordsBackend
from settings_store import get_provider_settings


PROVIDERS = {
    "zhipu": "Zhipu GLM Vision",
    "volcengine": "ByteDance / Volcengine Ark",
    "qwen_vl": "Qwen VL / DashScope",
}
BUTTON_RECT = (220, 120, 420, 240)


def synthetic_screen() -> str:
    image = Image.new("RGB", (640, 360), "#f3f5f7")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 639, 58), fill="#252a32")
    draw.text((20, 20), "DESKTOP VISION TEST", fill="white")
    draw.rectangle(BUTTON_RECT, fill="#16a34a", outline="#0d7131", width=4)
    draw.text((292, 174), "FINISH", fill="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def run_provider(provider: str, screenshot_b64: str) -> tuple[str, str]:
    settings = get_provider_settings(provider)
    api_key = str(settings.get("api_key", "")).strip()
    api_base = str(settings.get("api_base", "")).strip()
    model = str(settings.get("model", "")).strip()
    if not api_key:
        return "SKIP", "API key is not configured"
    if not api_base:
        return "FAIL", "API base is not configured"
    if not model:
        return "FAIL", "model is not configured"

    backend = VLMCoordsBackend(
        api_key=api_key,
        api_base=api_base,
        model=model,
        target_context="a Windows desktop screenshot",
        coordinate_mode="normalized_1000",
        normalized_output_to_pixels=True,
    )
    action = backend.get_next_action(
        "Click the center of the green FINISH button. Do not click anything else.",
        screenshot_b64,
    )
    action_type = str(action.get("type", ""))
    try:
        x = int(action["x"])
        y = int(action["y"])
    except (KeyError, TypeError, ValueError):
        return "FAIL", f"model={model} action={action!r}"
    x1, y1, x2, y2 = BUTTON_RECT
    if action_type not in {"click", "double_click"}:
        return "FAIL", f"model={model} action={action!r}"
    if not (x1 <= x <= x2 and y1 <= y <= y2):
        return "FAIL", f"model={model} coordinates=({x},{y}) outside {BUTTON_RECT}"
    return "PASS", f"model={model} action={action_type} coordinates=({x},{y})"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--provider",
        choices=["all", *PROVIDERS],
        default="all",
    )
    args = parser.parse_args()

    selected = list(PROVIDERS) if args.provider == "all" else [args.provider]
    screenshot_b64 = synthetic_screen()
    failures = 0
    configured = 0
    for provider in selected:
        try:
            status, detail = run_provider(provider, screenshot_b64)
        except Exception as exc:
            status, detail = "FAIL", f"{type(exc).__name__}: {exc}"
        if status != "SKIP":
            configured += 1
        if status == "FAIL":
            failures += 1
        print(f"[{status}] {PROVIDERS[provider]}: {detail}")

    if failures:
        return 1
    if not configured:
        print("No selected provider has a configured API key.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
