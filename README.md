# auto-pr-io

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md)

**A Windows GUI for visual device automation and Android screen/audio observation.**

Combine screenshots, a vision-language model, structured actions and device executors in one observable loop. Windows actions use `pyautogui`; Android actions use ADB. The current entry point is `main.py` with the `ui_v2` Tkinter interface.

> **Experimental source project.** No packaged GitHub Release is currently published. Model-driven coordinate actions depend on the selected provider, target app and device; a successful setup is not a guarantee that arbitrary tasks will complete correctly.

## Two work modes

| Mode | Input | Result |
| --- | --- | --- |
| Build | Windows or Android screenshots and a task | Model-planned clicks, input, scrolling and other supported actions |
| Chat | Android screenshots and optional local speech transcripts | Notes and answers without device actions |

Desktop Chat is not claimed as an implemented mode. AutoGLM-Phone is an optional adapter requiring the external `phone_agent` package, not a bundled runtime.

## Capabilities

- Capture the full Windows screen, a selected region or a window; keep the chosen capture target across steps.
- Convert model coordinates to screenshot pixels and desktop offsets; execute mouse/keyboard actions, including Unicode text via clipboard paste.
- Select an ADB device, preview its screen and run phone actions. The Android helper supplies an IME and playback-audio capture.
- Transcribe captured audio locally with FunASR / SenseVoiceSmall; use transcripts alongside screen context.
- Select Markdown skills, configure forbidden click rectangles, inspect live logs and retain task history.
- Use the English, Simplified Chinese, Traditional Chinese or Japanese GUI.

## Start on Windows

Use Windows 10/11 and Python 3.10–3.12 with Tkinter; Python 3.12 is the project's preferred environment. Android features also require ADB and an authorized USB/wireless debugging connection. Speech dependencies include PyTorch and may require substantial downloads.

```powershell
git clone https://github.com/LE-saber/auto-pr-io.git
Set-Location .\auto-pr-io
.\start.ps1
```

The launcher locates a compatible Python, creates or repairs `.venv312`, prepares dependencies when creating/repairing that environment, checks Tcl/Tk and ADB, then starts the GUI. It is not an automatic dependency updater for an already valid environment. For a manual install, or to refresh dependencies:

```powershell
py -3.12 -m venv .venv312
.\.venv312\Scripts\python.exe -m pip install -r requirements.txt
.\.venv312\Scripts\python.exe main.py
```

In **Settings → API and ADB settings**, enter the chosen provider's endpoint/model/key and ADB location as needed. Choose the desktop capture target or Android device, select Build or Chat, and start with a small task whose result you can inspect. Desktop provider options include GLM, Doubao and Qwen; Android also has generic coordinate and other adapters. Availability depends on your provider account and model access.

## Android audio and input

The helper source and build/install instructions are in [android/AutoPrKeyboardAudio](android/AutoPrKeyboardAudio/README.md). Its package is `com.autopr.keyboardaudio`; the IME is `com.autopr.keyboardaudio/.AdbImeService`.

Playback capture requires Android 13+ in the documented project setup, MediaProjection approval, and a target app that allows capture. Calls, protected media and apps that disallow capture may yield silence. Recordings and transcription sidecars are local files under `recordings/`. The default ASR model is `iic/SenseVoiceSmall`.

## Configuration, data and limits

- `settings.json` stores local preferences. API keys use Windows DPAPI where available; the fallback `b64_unprotected:` representation is reversible and **is not encryption**.
- Screenshots, recordings and `history/tasks.jsonl` may contain task data. Model requests send the selected screen/context to the configured provider; local ASR does not make the whole workflow offline.
- Forbidden rectangles constrain click positions; they do not constitute a comprehensive permission system. Keep consequential actions under direct supervision.
- Model JSON can be invalid or coordinates inaccurate. Android input compatibility varies by OS and target app.
- Browser DOM automation, a complete confirmation/permission system and a production reliability guarantee are not provided by this project.

## Source map and detailed guides

| Path | Responsibility |
| --- | --- |
| [main.py](main.py), [ui_v2/](ui_v2/) | Current GUI entry point and interface |
| [auto_click/](auto_click/) | Automation loop, backends, ADB, audio, skills and history |
| [windows/](windows/) | Screen, region and window capture |
| [settings_store.py](settings_store.py) | Settings and key storage |
| [skills/](skills/) | Task instructions, including CIDA/VocabGo modes |
| [tests/](tests/) | Existing regression suites |
| [ui/](ui/) | Retained older GUI; not the main entry point |

The [complete original Chinese guide](README.reference.zh-CN.md) retains action-protocol examples, coordinate calculations, CIDA mode details, provider options, tests, diagrams and roadmap. [PROJECT_INTRO.md](PROJECT_INTRO.md) gives additional project context; [DESIGN.md](DESIGN.md), [HANDOVER.md](HANDOVER.md) and [work.md](work.md) record design and historical work. Read historical observations in the context of their snapshot.

## Development checks

From a configured Windows environment:

```powershell
.\.venv312\Scripts\python.exe -m compileall auto_click ui ui_v2 settings_store.py tests
.\.venv312\Scripts\python.exe tests\test_20260506_fixes.py
.\.venv312\Scripts\python.exe tests\test_desktop_runtime.py
.\.venv312\Scripts\python.exe tests\test_ui_v2_contract.py
```

These are existing project checks, not results claimed by this documentation update. Live model/device checks need the appropriate Windows, Android and provider environment. No repository-wide license is declared at the root; dependencies retain their own licenses.
