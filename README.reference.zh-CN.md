> [Current introduction / 当前介绍](README.md) · 原详细指南作为参考保留；历史环境、后续计划与当前能力应分别理解。

# auto-pr-io

`auto-pr-io` 是一个面向 Windows 桌面和 Android 手机的多模态自动化/观察助手。它的核心不是让模型直接控制系统，而是把截图、视觉语言模型、固定 JSON 动作协议、坐标映射、ADB/桌面执行器、语音转文字和 GUI 控制面板组合成一个可运行的 Agent 循环。

项目当前可以理解为一个 **Auto-GLMPhone-plus / Computer Use GUI 实验平台**：

```text
用户任务
-> 截图或手机画面
-> VLM 看屏幕并规划下一步
-> 输出固定 JSON 动作
-> 坐标映射和安全限制
-> ADB 或 Windows 执行器操作
-> 再截图反馈
-> 循环直到完成
```

同时它也提供只观察、不点击的 Chat 模式，用于网课、会议、视频、直播等场景的实时笔记和问答。

## 当前定位

这个项目主要解决两类问题：

1. **Build 模式：让模型操作设备**
   - Android：通过 ADB 截图、点击、滑动、输入、返回、Home 等。
   - Windows：通过屏幕截图和 `pyautogui` 执行鼠标键盘动作。
   - 适合自动做题、简单 App 操作、简单表单填写、低风险重复点击任务。

2. **Chat 模式：让模型只观察并回答**
   - 不点击、不输入、不返回、不控制设备。
   - 读取 Android 屏幕和本地 ASR 转写结果。
   - 适合网课笔记、会议纪要、视频总结、根据屏幕和语音回答问题。

## 主要能力

| 能力 | 当前实现 |
|---|---|
| Windows 屏幕分析 | 全屏、区域、窗口截图 |
| Windows 自动操作 | `pyautogui` 点击、输入、快捷键、滚动、拖拽 |
| Android 自动操作 | ADB 截图、点击、滑动、输入、返回、Home |
| Android 设备选择 | GUI 自动扫描 ADB 设备并选择 |
| 手机实时预览 | GUI 显示 Android 截图和动作标注 |
| VLM 坐标后端 | OpenAI-compatible 协议的 Vision 模型输出 JSON 动作 |
| Windows VLM | 智谱 GLM、火山方舟豆包、千问 VL 三种入口 |
| GLM Vision | Windows / Android，默认 `glm-4.6v-flashx` |
| Qwen VL | Windows / Android，默认 `qwen3-vl-plus` |
| ByteDance Vision | Windows，默认 `doubao-seed-2-0-lite-260215` |
| AutoGLM-Phone | 可选外部后端，依赖 Open-AutoGLM / `phone_agent` |
| 本地 ASR | Android 机内录音 + FunASR / SenseVoiceSmall |
| Skill 系统 | Markdown skill 注入 VLM prompt，可强制启用 |
| 禁止点击区域 | 在截图上框选矩形，运行时拦截危险点击 |
| 日志和历史 | GUI 实时日志、筛选、任务历史、截图关联 |
| 多语言 GUI | 简体中文、英文、日文、繁体中文 |
| 字号调整 | GUI 可调整字体大小 |
| 密钥保护 | Windows 下使用 DPAPI 加密保存 API Key |

## 项目结构

```text
auto-pr-io/
├── main.py                         # GUI 入口
├── config.py                       # 全局路径和默认配置
├── settings_store.py               # settings.json 读写、API Key 加密
├── requirements.txt                # Python 依赖
├── start.bat / start.ps1           # Windows 一键启动脚本
├── PROJECT_INTRO.md                # 当前项目说明和近期变更
├── HANDOVER.md / work.md           # 历史交接文档
│
├── auto_click/                     # 自动化核心
│   ├── clicker.py                  # 主循环、Build/Chat 调度、ASR 注入
│   ├── adb.py                      # ADB 设备、截图、输入和执行器
│   ├── executor.py                 # Windows pyautogui 执行器
│   ├── audio.py                    # Android 机内录音 + SenseVoice 转写
│   ├── model_skills.py             # skill 选择和强制注入
│   ├── forbidden_zones.py          # 禁止点击区域检查
│   ├── history.py                  # 任务历史记录
│   ├── backends/
│   │   ├── vlm_coords.py           # 通用 VLM JSON 坐标后端
│   │   ├── openai_cua.py           # OpenAI Computer Use 后端
│   │   ├── observe_only.py         # Chat/观察模式后端
│   │   ├── autoglm_phone.py        # AutoGLM-Phone 适配层
│   │   └── reasoning_oracle.py     # 推理 Oracle 辅助
│   └── modes/
│       └── profiles.py             # CIDA Work 等任务模式配置
│
├── ui_v2/                          # 当前 Tkinter GUI（main.py 唯一入口）
│   ├── app.py                      # 应用壳、目标/模式切换、任务控制
│   ├── backend.py                  # GUI 到 AutoClicker 的适配层
│   ├── desktop.py                  # 区域框选和窗口选择
│   ├── screen.py                   # Windows / Android 实时画面
│   ├── settings.py                 # API / ADB / ASR / Oracle 设置
│   ├── views.py                    # 历史、Skill、日志、Chat 等视图
│   ├── i18n.py                     # 四语言文本
│   └── theme.py                    # 深色主题和字体
├── ui/                             # 旧版 GUI，仅保留兼容，不由 main.py 导入
│
├── windows/                        # Windows 截图能力
│   ├── capture.py                  # 全屏、区域、窗口截图
│   └── window_selector.py          # 旧窗口选择兼容模块
│
├── android/AutoPrKeyboardAudio/    # Android 辅助 APK
│   ├── README.md                   # APK 构建、安装、录音说明
│   └── app/                        # Android 源码
│
├── skills/                         # 给 VLM 使用的 Markdown skill
├── Screenshots/                    # 截图和示例图片
├── recordings/                     # Android 音频归档和转写 sidecar
├── history/                        # tasks.jsonl 历史记录
└── tests/                          # 回归测试
```

## 运行方式

推荐使用项目内的 Python 3.12 虚拟环境：

```powershell
.\.venv312\Scripts\python.exe main.py
```

也可以用一键脚本：

```powershell
.\start.ps1
```

或：

```cmd
start.bat
```

启动脚本会尝试完成：

- 检查 Python 3.10-3.12。
- 创建或原地修复断链的 `.venv312`。
- 安装 `requirements.txt`。
- 准备 Tcl/Tk runtime。
- 检查 ADB 是否可用。
- 启动 GUI。

## 依赖环境

基础依赖见 `requirements.txt`，主要包括：

- `openai`
- `zhipuai`
- `anthropic`
- `Pillow`
- `mss`
- `pyautogui`
- `pyperclip`
- `pywin32`
- `sv-ttk`
- `funasr`
- `modelscope`
- `torch`
- `torchaudio`

建议环境：

- Windows 10/11。
- Python 3.10 - 3.12，当前项目优先使用 `.venv312`。
- Android 自动化需要 ADB。
- 本地 SenseVoice ASR 建议使用可运行 PyTorch 的环境。

## API 和设置

API Key 不在首页填写，统一在 GUI 中配置：

```text
Settings -> API and ADB settings
```

配置会保存到：

```text
settings.json
```

当前支持的 provider 包括：

- `zhipu`
- `volcengine`
- `qwen_vl`
- `openai`
- `anthropic`
- `custom`
- `vlm_coords`
- `deepseek_vision`
- `autoglm_phone`

Windows 下保存 API Key 时会优先使用 DPAPI 加密：

```text
dpapi:<base64>
```

如果 DPAPI 不可用，会退回到可逆的 base64 标记：

```text
b64_unprotected:<base64>
```

这只是兼容回退，不等同于真正加密。

## Android 自动化路径

Android 端主要通过 ADB 完成：

```text
ADB screencap
-> 发送截图给 VLM
-> VLM 返回 JSON 动作
-> 1000x1000 归一化坐标映射到真实分辨率
-> adb shell input 执行
-> 重新截图反馈
```

常见动作协议：

```json
{"type":"click","x":500,"y":875}
{"type":"double_click","x":500,"y":500}
{"type":"type","text":"hello"}
{"type":"key","keys":["ENTER"]}
{"type":"scroll","x":500,"y":700,"direction":"down","amount":300}
{"type":"listen_audio","duration":5,"question":"what is being said"}
{"type":"wait","seconds":1}
{"type":"done"}
```

手机坐标模式通常使用 `1000x1000` 归一化坐标：

```text
real_x = norm_x / 1000 * screen_width
real_y = norm_y / 1000 * screen_height
```

例如在 `1080x2400` 手机上：

```text
(837, 832) -> (904, 1997)
```

## Android 辅助 APK

项目内置了一个 Android 辅助 APK：

```text
android/AutoPrKeyboardAudio
```

它的作用是：

- 提供 ADB Keyboard 兼容输入法。
- 支持通过广播输入文字。
- 提供 Android UI 申请机内录音权限。
- 使用 `MediaProjection` + `AudioPlaybackCaptureConfiguration` 做机内录音。
- 输出 `latest.wav` 和 chunk 音频给 PC 端 ASR 使用。

IME 名称：

```text
com.autopr.keyboardaudio/.AdbImeService
```

包名：

```text
com.autopr.keyboardaudio
```

安装和构建说明见：

```text
android/AutoPrKeyboardAudio/README.md
```

注意：Android 只允许捕获允许被录制的播放流。部分 App、通话、DRM 内容或受保护媒体可能会产生静音。

## 本地实时语音转文字

旧 Whisper 路径已经不作为主路径，当前项目主要使用本地 FunASR / SenseVoice：

```text
Android 机内录音
-> 辅助 APK 输出 wav chunk
-> PC 端拉取音频片段
-> SenseVoiceSmall 本地转写
-> 注入 VLM 上下文
```

默认模型：

```text
iic/SenseVoiceSmall
```

相关文件：

```text
auto_click/audio.py
```

录音文件会归档到：

```text
recordings/
```

并尽量生成同名 `.txt` 转写 sidecar，便于人工复核。

## Windows 自动化路径

Windows 端支持：

- 全屏截图。
- 框选区域截图。
- 指定窗口截图。
- 使用 `pyautogui` 执行点击、输入、滚动、拖拽、快捷键。
- 每一步继续捕获同一个屏幕、区域或窗口，不会在首步后退回全屏。
- 中文等 Unicode 文本通过剪贴板粘贴输入。
- GUI 实时接收每一步的新截图和动作标记。

电脑端模型统一输出 `1000x1000` 归一化坐标，运行时经过两段映射：

```text
归一化坐标
-> 当前截图内像素坐标
-> 区域/窗口在桌面上的绝对坐标
-> pyautogui 执行
```

禁止点击区域、GUI 标记和历史截图始终使用截图内像素坐标，因此区域或窗口偏移不会污染这些数据。

适合桌面软件和无法用 DOM/API 稳定控制的场景。

如果任务是网页、邮箱、购物网站或表单，长期方案更建议接入 Playwright / Selenium 等结构化浏览器自动化。当前项目的桌面能力更偏视觉坐标控制。

## Build 模式和 Chat 模式

| 项目 | Build 模式 | Chat 模式 |
|---|---|---|
| 是否控制设备 | 是 | 否 |
| 是否点击/输入 | 是 | 否 |
| 是否读取截图 | 是 | 是 |
| 是否使用 ASR | 可用 | 可用 |
| 典型场景 | 自动做题、自动点击、简单 App 操作 | 网课笔记、会议总结、实时问答 |
| 后端 | Windows：GLM / Doubao / Qwen；Android：GLM / Qwen / AutoGLMPhone 等 | 内部 `observe_adb` |

Chat 模式内部使用：

```text
auto_click/backends/observe_only.py
```

它会明确要求模型不要返回 JSON 动作，也不要控制设备，只输出面向用户的笔记或回答。

## 当前后端

GUI 中主要后端：

- `Windows - Zhipu GLM Vision`
- `Windows - ByteDance Doubao Vision`
- `Windows - Qwen VL`
- `Android ADB - OpenAI Computer Use`
- `Android ADB - Generic VLM coordinates`
- `Android ADB - GLM Vision (glm-4.6v-flashx)`
- `Android ADB - DeepSeek Vision (deepseek-vl2)`
- `Android ADB - CIDA Work Mode`
- `Android ADB - AutoGLM-Phone`

Chat 模式对应的 `observe_adb` 不作为普通自动化后端暴露，避免用户把“只观察”误认为“可控制”。

## CIDA Work 模式

项目包含一个面向 CIDA/VocabGo 练习的专用模式：

```text
auto_click/modes/profiles.py
skills/cida-work.md
skills/cida-type4.md
Screenshots/example/
```

该模式的设计思路：

- 主模型：Qwen3-VL-Plus / Qwen3-VL-32B，用于看屏幕、理解题型、规划操作。
- 快速辅助模型：GLM-4.6V-FlashX，用于低成本页面状态识别和简单点击。
- ASR：本地 FunASR / SenseVoiceSmall，用于听力题语音转文字。
- Skill：通过 `cida-work` 和 `cida-type4` 限定题型规则，避免模型误解箭头、横线、短语填空等界面元素。

默认强制 skill：

```text
cida-type4.md
```

## Skill 系统

Skill 文件位于：

```text
skills/
```

它们是给 VLM 看的 Markdown 规则，不是 Python 插件。GUI 支持：

- 新增 skill。
- 选择 skill。
- 编辑内容。
- 保存修改。
- 复制 skill。
- 删除 skill。
- 勾选强制使用。

运行时 `auto_click/model_skills.py` 会根据任务、屏幕上下文和强制配置选择最多若干 skill 注入 prompt。

## 禁止点击区域

禁止点击区域用于限制 VLM 的点击位置。流程是：

```text
在截图上框选矩形
-> 保存为预设
-> 运行时读取当前预设
-> 点击前检查坐标是否落入禁止区域
-> 如果命中则阻止执行并反馈给 VLM
```

相关文件：

```text
auto_click/forbidden_zones.py
ui/forbidden_zones_panel.py
```

这个功能适合保护：

- 系统导航栏。
- 返回按钮。
- 提交按钮。
- 删除按钮。
- 付款、发送、确认等高风险区域。

## 日志和历史

GUI 日志支持按等级和关键词过滤。常见关键词：

- `VLM response`
- `ADB action`
- `realtime sensevoice`
- `Audio transcription`
- `blocked`
- `ERROR`

历史记录保存到：

```text
history/tasks.jsonl
```

历史中会尽量记录：

- 任务描述。
- 后端。
- 模型。
- 成功/失败。
- 错误信息。
- 相关截图。
- Chat 模式回复。

文件超过上限时会自动修剪旧记录。

## 验证命令

编译检查：

```powershell
.\.venv312\Scripts\python.exe -m compileall auto_click ui settings_store.py tests
```

回归测试：

```powershell
.\.venv312\Scripts\python.exe tests\test_20260506_fixes.py
```

当前测试覆盖重点包括：

- API Key 加密和兼容读取。
- 历史记录轮转。
- 日志行数上限。
- Oracle 客户端刷新。
- `AutoClicker.run_task()` 并发启动保护。
- 启动失败时 `_running` 回滚。
- VLM / Observe 后端请求超时。
- `_vlm_history` 线程安全访问。
- Windows 区域/窗口坐标偏移和缩放。
- Windows 拖拽、禁点区域和 Unicode 输入。
- 固定捕获目标在每一步持续生效。
- 智谱、火山方舟、千问的非执行式视觉坐标冒烟测试。

## 已知限制

- 当前根目录可能不是完整 Git 工作树，发布前需要确认 `.gitignore`，避免提交 `.venv312/`、`.runtime/`、`recordings/`、`Screenshots/phone_live/`、`__pycache__/` 等运行产物。
- VLM 坐标后端依赖模型输出 JSON。代码已处理代码围栏、字段别名、部分 Qwen 坐标错误，并将电脑端归一化坐标转为截图像素；连续无效响应仍会退化为 `wait`。
- Android 机内录音依赖 Android 13+、MediaProjection 授权和目标 App 允许播放捕获。
- ADB Keyboard 可以改善输入，但系统输入法、中文输入和特殊字符仍可能受 Android 版本和目标 App 限制。
- AutoGLM-Phone 后端依赖外部 Open-AutoGLM / `phone_agent`，不是本项目完全自带实现。
- Chat 模式目前主要面向 Android 观察；桌面观察模式后续还可以扩展。
- 对真实发送消息、邮件、购物、付款等任务，建议继续增加确认弹窗、白名单、金额限制和动作审计。

## 后续开发方向

- 为网页任务增加 Playwright 后端，避免纯视觉坐标点击造成误操作。
- 增强 ASR 的 VAD、分段合并、去重和时间戳。
- 给 Chat 模式增加临时提问输入框和“只总结新增内容”策略。
- 增加桌面 Chat 观察模式。
- 增加任务模板，例如回复消息、邮件草稿、商品搜索、加入购物车。
- 完善 Android 辅助 APK 的状态回传和安装更新流程。
- 增加更严格的动作 schema 校验和模型输出修复。

## 一句话总结

`auto-pr-io` 是一个以 GUI 为入口的多模态设备 Agent 项目：它让 VLM 通过固定动作协议指挥 Windows 或 Android 执行器，并通过截图、ASR、skill、禁止区域和历史日志形成可观察、可调试的自动化闭环。
