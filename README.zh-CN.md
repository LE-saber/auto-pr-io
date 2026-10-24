# auto-pr-io

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md)

**面向视觉设备自动化与 Android 屏幕/音频观察的 Windows GUI。**

将截图、视觉语言模型、结构化动作与设备执行器组合为可观察的循环。Windows 使用 `pyautogui` 执行动作，Android 使用 ADB。当前入口为 `main.py`，加载 `ui_v2` Tkinter 界面。

> **实验性源码项目。** 当前没有已发布的 GitHub 安装包 Release。模型坐标操作取决于提供商、目标应用和设备，成功启动不代表任意任务都能可靠完成。

## 两种工作模式

| 模式 | 输入 | 结果 |
| --- | --- | --- |
| Build | Windows 或 Android 截图和任务 | 模型规划的点击、输入、滚动等支持动作 |
| Chat | Android 截图及可选本地语音转写 | 只输出笔记和回答，不操作设备 |

桌面 Chat 不属于已实现能力。AutoGLM-Phone 只是可选适配器，依赖外部 `phone_agent`，不是仓库自带运行时。

## 主要能力

- Windows 全屏、区域或窗口截图，各步骤保持所选捕获目标。
- 模型坐标映射为截图像素及桌面偏移，执行鼠标/键盘动作，通过剪贴板粘贴 Unicode 文字。
- 选择 ADB 设备、预览手机屏幕并执行动作；Android 辅助应用提供输入法和播放音频捕获。
- 用 FunASR / SenseVoiceSmall 在本地转写音频，并与屏幕上下文一起使用。
- 选择 Markdown Skill、设置禁点矩形、查看实时日志及任务历史。
- GUI 支持英文、简体中文、繁体中文和日文。

## Windows 快速开始

使用 Windows 10/11、带 Tkinter 的 Python 3.10–3.12，推荐 Python 3.12。Android 功能还需要 ADB 和已授权的 USB/无线调试连接。语音依赖包含 PyTorch，下载体积可能较大。

```powershell
git clone https://github.com/LE-saber/auto-pr-io.git
Set-Location .\auto-pr-io
.\start.ps1
```

启动器寻找兼容 Python，创建或修复 `.venv312`，在创建/修复环境时安装依赖，检查 Tcl/Tk 和 ADB 后启动 GUI。它不会为已有有效环境自动更新依赖。手动安装或刷新依赖可执行：

```powershell
py -3.12 -m venv .venv312
.\.venv312\Scripts\python.exe -m pip install -r requirements.txt
.\.venv312\Scripts\python.exe main.py
```

在 **Settings → API and ADB settings** 填写所选提供商的端点、模型、Key 与所需 ADB 路径。选择桌面捕获目标或 Android 设备，再选择 Build/Chat，从结果容易核对的小任务开始。桌面提供 GLM、豆包、千问入口；Android 另有通用坐标等适配器。实际可用性取决于账号和模型权限。

## Android 音频与输入

[辅助应用说明](android/AutoPrKeyboardAudio/README.md) 包含源码、构建和安装步骤。包名为 `com.autopr.keyboardaudio`，IME 为 `com.autopr.keyboardaudio/.AdbImeService`。

项目记录的播放捕获环境要求 Android 13+、MediaProjection 授权以及目标应用允许捕获。通话、受保护媒体和禁止捕获的应用可能只产生静音。录音及转写文本存于本地 `recordings/`；默认 ASR 模型为 `iic/SenseVoiceSmall`。

## 配置、数据与限制

- 本机偏好存于 `settings.json`。Windows 优先用 DPAPI 保存 Key；`b64_unprotected:` 回退是可逆编码，**不等于加密**。
- 截图、录音和 `history/tasks.jsonl` 可能包含任务数据。模型请求会把所选画面和上下文发给配置的提供商，本地 ASR 不代表整个工作流离线。
- 禁点矩形只限制点击位置，不构成完整权限体系，重要操作应直接监督。
- 模型 JSON 可能无效，坐标可能不准；Android 输入兼容性取决于系统与目标应用。
- 项目未提供浏览器 DOM 自动化、完整确认/授权体系或生产可靠性保证。

## 源码与详细资料

| 路径 | 作用 |
| --- | --- |
| [main.py](main.py)、[ui_v2/](ui_v2/) | 当前入口和 GUI |
| [auto_click/](auto_click/) | 主循环、后端、ADB、音频、Skill 和历史 |
| [windows/](windows/) | 全屏、区域及窗口捕获 |
| [settings_store.py](settings_store.py) | 配置和 Key 存储 |
| [skills/](skills/) | 包括 CIDA/VocabGo 在内的任务规则 |
| [tests/](tests/) | 已有回归测试 |
| [ui/](ui/) | 保留的旧 GUI，不是主入口 |

[原完整中文指南](README.reference.zh-CN.md) 保留动作协议、坐标计算、CIDA 模式、后端、测试、流程与路线图。[PROJECT_INTRO.md](PROJECT_INTRO.md) 提供项目补充；[DESIGN.md](DESIGN.md)、[HANDOVER.md](HANDOVER.md) 和 [work.md](work.md) 是设计及历史记录，应按各自快照理解。

## 开发检查

在已配置的 Windows 环境运行：

```powershell
.\.venv312\Scripts\python.exe -m compileall auto_click ui ui_v2 settings_store.py tests
.\.venv312\Scripts\python.exe tests\test_20260506_fixes.py
.\.venv312\Scripts\python.exe tests\test_desktop_runtime.py
.\.venv312\Scripts\python.exe tests\test_ui_v2_contract.py
```

以上是现有检查命令，不代表本次文档更新运行后的测试结果。真实模型和设备检查需要对应 Windows、Android 和提供商环境。根目录未声明统一许可证，依赖遵循各自许可证。
