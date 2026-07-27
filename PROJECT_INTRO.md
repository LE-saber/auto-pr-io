# auto-pr-io 项目介绍

## 2026-05-11 Code Review Follow-up

- `AutoClicker.run_task()` now uses a startup lock around the `_running` check/set and rolls `_running` back to `False` if backend setup, executor setup, or initial screenshot capture fails before a worker thread is started.
- Chat/Observe mode now applies the same 120-second OpenAI-compatible request timeout as the Build-mode VLM backend.
- API key storage now writes new protected values with a `dpapi:` prefix. If DPAPI is unavailable, the fallback is stored as `b64_unprotected:` and a warning is logged because this is reversible obfuscation, not encryption.
- History rotation now keeps trimming old records until `history/tasks.jsonl` is under the configured size limit, instead of keeping at least 100 records even when the file is still too large.
- Regression tests were expanded for startup rollback and Observe-mode timeout.

## 项目定位

`auto-pr-io` 是一个面向 Windows 桌面和 Android 手机的多模态自动化/观察助手。项目核心不是让模型直接“拥有点击能力”，而是把 VLM、多模态截图理解、语音转文字、固定动作协议、坐标映射、ADB/桌面执行器和 GUI 控制面板组合成一套可运行的 Agent 系统。

当前项目分为两类工作模式：

- **Build 模式**：模型可以控制设备。适合自动点击、填写、做题、回复简单消息、完成简单手机或电脑操作。
- **Chat 模式**：模型只观察和收听，不控制设备。适合看网课、会议、直播或视频时实时整理笔记、总结重点、回答问题。

Chat 模式内部使用只读后端 `observe_adb`，但它不会显示在 OpenAI Computer Use、AutoGLM-Phone、GLM 等自动化后端列表中，避免把“聊天观察”和“设备控制”混在一起。

## 主要功能

### 1. Android 手机自动化

Android 端通过 ADB 读取截图、执行点击/输入/返回等动作：

```text
手机截图
-> VLM 识别屏幕和任务
-> 输出 JSON 动作
-> 坐标映射
-> ADB 执行
-> 再截图反馈
```

常用动作协议示例：

```json
{"type":"click","x":500,"y":875}
{"type":"type","text":"hello"}
{"type":"key","keys":["ENTER"]}
{"type":"listen_audio","duration":5,"question":"what is being said"}
{"type":"done"}
```

对于 GLM/Qwen 等手机坐标模型，项目支持 `1000x1000` 归一化坐标，再转换为真实手机分辨率：

```text
real_x = norm_x / 1000 * screen_width
real_y = norm_y / 1000 * screen_height
```

### 2. Windows 桌面自动化

桌面端支持全屏、指定区域、指定窗口截图。执行层主要通过 `pyautogui` 完成点击和输入。桌面端后端包括 OpenAI Computer Use 和通用 VLM 坐标后端。

### 3. Chat 观察模式

Chat 模式关闭控制端，只做观察和回答：

- 读取 Android 屏幕截图。
- 可持续接收手机内录音 ASR 文本。
- 不启用 ADB Keyboard。
- 不执行点击、输入、滑动、返回。
- 模型回复显示在 GUI 右侧的 **Chat 回复** 窗口。

适用场景：

- 网课实时笔记。
- 会议纪要。
- 视频内容总结。
- 根据屏幕和语音回答用户问题。

### 4. 本地实时语音转文字

项目已去掉旧的 Whisper 方案，转向本地 FunASR / SenseVoice：

```text
Android 机内录音
-> ADB 拉取音频片段
-> 本地 SenseVoiceSmall 转写
-> 注入 VLM 上下文
```

相关能力：

- 支持持续录音。
- 支持录音状态显示。
- 录音文件归档到 `recordings/`。
- ASR 文本进入 VLM 上下文和历史记录。

Android 端依赖自定义辅助 APK：

```text
android/AutoPrKeyboardAudio
package: com.autopr.keyboardaudio
IME: com.autopr.keyboardaudio/.AdbImeService
```

它同时承担 ADB Keyboard 和机内录音辅助功能。

### 5. Skill 系统

项目提供给 VLM 的 skill 文件位于：

```text
skills/
```

GUI 支持：

- 查看 skill。
- 新增 skill。
- 复制 skill。
- 删除 skill。
- 编辑并保存 skill。
- 勾选“强制使用”某个 skill。

被强制勾选的 skill 会优先注入 VLM prompt，避免仅依赖关键词匹配导致模型读不到关键规则。

当前重要 skill：

- `cida-work.md`：CIDA/VocabGo 做题总规则。
- `cida-type4.md`：第四种题型的短规则，默认强制启用。
- `adb_keyboard.md`：ADB Keyboard 使用提示。
- `audio_analysis.md`：语音分析提示。

### 6. 禁止点击区域

GUI 支持在截图上框选禁止点击区域，并保存为预设。运行时点击动作会先经过限制检查：

```text
VLM click
-> 禁止区域检查
-> 如果命中，阻止执行
-> 把 blocked_click 反馈给 VLM
-> VLM 重新规划
```

这可以避免模型点击系统导航栏、返回、误提交或危险区域。

### 7. 日志和历史记录

日志面板支持筛选：

- 按级别：Info / Error 等。
- 按关键词：例如 `realtime sensevoice`。
- 快捷过滤：点击坐标、VLM 回复、ADB 动作等。

历史记录保存：

- 任务内容。
- 使用后端。
- 模型。
- 成功/失败状态。
- 相关截图。
- Chat 模式回复。

历史记录文件位于：

```text
history/tasks.jsonl
```

## 技术架构

### GUI 层

主要文件：

```text
main.py
ui/main_window.py
ui/auto_click_panel.py
ui/phone_screen_panel.py
ui/chat_panel.py
ui/log_panel.py
ui/result_panel.py
ui/forbidden_zones_panel.py
ui/settings_dialog.py
```

职责：

- 设备选择。
- Build / Chat 模式切换。
- 后端选择。
- API 和 ADB 设置。
- 实时截图预览。
- Chat 回复显示。
- 日志和历史记录展示。
- skill 管理。
- 禁止点击区域管理。

### 自动化核心层

主要文件：

```text
auto_click/clicker.py
auto_click/adb.py
auto_click/executor.py
auto_click/audio.py
auto_click/model_skills.py
auto_click/forbidden_zones.py
```

职责：

- 运行主循环。
- 截图获取。
- VLM 后端调用。
- JSON 动作解析。
- ADB / Windows 执行。
- ASR 音频转写。
- skill 注入。
- 禁止点击区域拦截。
- 历史记录回调。

### 模型后端

主要文件：

```text
auto_click/backends/vlm_coords.py
auto_click/backends/openai_cua.py
auto_click/backends/autoglm_phone.py
auto_click/backends/observe_only.py
auto_click/backends/reasoning_oracle.py
```

后端类型：

- OpenAI Computer Use。
- AutoGLM-Phone。
- 通用 OpenAI-compatible VLM 坐标后端。
- Qwen VL / GLM Vision。
- Observe-only Chat 后端。
- Oracle 推理辅助模型。

## 运行环境

推荐使用项目内 Python 3.12 虚拟环境：

```powershell
.\.venv312\Scripts\python.exe main.py
```

依赖安装见：

```text
requirements.txt
```

主要依赖：

- `openai`
- `zhipuai`
- `Pillow`
- `pyautogui`
- `mss`
- `funasr`
- `modelscope`
- `torch`
- `torchaudio`
- `sv-ttk`

## API 设置位置

API Key 不放在首页，统一在：

```text
Settings -> API and ADB settings
```

常用配置：

- Qwen VL：`qwen_vl`
- Zhipu GLM：`zhipu`
- OpenAI：`openai`
- Generic VLM：`vlm_coords`
- Oracle：`oracle`

配置会保存到：

```text
settings.json
```

## Android 辅助 APK

源码目录：

```text
android/AutoPrKeyboardAudio
```

作用：

- ADB Keyboard 输入文字。
- 机内录音。
- 显示录音授权和录音状态。
- 向 PC 端输出音频片段。

构建使用本机 Gradle：

```text
D:\gradle\gradle-9.0.0-bin\gradle-9.0.0\bin\gradle.bat
```

## Build 模式与 Chat 模式区别

| 项目 | Build 模式 | Chat 模式 |
|---|---|---|
| 是否控制设备 | 是 | 否 |
| 是否点击/输入 | 是 | 否 |
| 是否读取截图 | 是 | 是 |
| 是否可用 ASR | 是 | 是 |
| 典型用途 | 自动做题、自动操作手机/电脑 | 网课笔记、会议总结、问答 |
| 后端选择 | OpenAI / GLM / Qwen / AutoGLMPhone 等 | 内部 observe-only 后端 |

## 当前设计细节

- Chat 模式不直接暴露 `observe_adb`，避免用户把它当成自动化控制后端。
- Build 模式下才显示和使用自动化后端。
- `observe_adb` 仍保留在内部 `AutoClickPanel.BACKEND_LABELS`，是为了保存历史状态和内部切换。
- Chat 模式输出进入 `ui/chat_panel.py`，并同步保存到任务历史。
- ASR 连续转写会被注入观察后端上下文，用于实时笔记和问答。
- 强制 skill 会优先注入 VLM，日志中会出现 `VLM skills injected` 便于确认。

## 后续可完善方向

- Chat 模式增加“只总结新增内容”的去重策略。
- Chat 模式增加手动提问输入框，把用户临时问题注入下一轮观察。
- ASR 增加 VAD 和长文本分段合并，减少空片段。
- 历史记录增加 Chat 回复全文导出。
- Build 模式增加更严格的动作审计和二次确认。
- 桌面端也支持 Chat 观察模式，用于 PC 网课/会议总结。

## 最近安全加固 (2026-05-06)

### API 密钥加密

`settings.json` 中的 API 密钥不再明文存储。保存时使用 Windows DPAPI (`win32crypt.CryptProtectData`) 加密并转为 base64 存入 JSON 文件。DPAPI 将加密绑定到当前 Windows 用户账户，即使文件被拷贝到其他机器或用户也无法解密。

- **加密范围**：`providers.*.api_key`、`oracle.api_key`、`audio.whisper_api_key`
- **向后兼容**：已有的明文密钥文件可正常读取，下次保存时自动转为加密格式
- **回退策略**：如果 DPAPI 解密失败（如跨机器迁移），尝试 base64 混淆层，再失败则当作明文使用

### 并发安全

- **竞态条件修复** (`auto_click/clicker.py:run_task`): `_running` 标志在线程启动前设置，防止重复调用 `run_task()` 产生多个并发自动化循环
- **VLM 历史线程安全**: `_vlm_history` 列表（自动化线程和音频回调线程共享）新增 `threading.Lock` 保护所有读写操作

### 运行时保护

- **VLM 请求超时** (`vlm_coords.py`): OpenAI 客户端和 API 请求均设置 `timeout=120` 秒，防止模型 API 挂死导致自动化线程永久阻塞
- **桌面截图异常处理**: `pyautogui.screenshot()` 添加 try/except，失败时抛出 `RuntimeError` 而非无提示崩溃

### 资源管理

- **日志行数上限** (`log_panel.py`): 内存中日志行数上限 5000 行，超出后保留最新 5000 行
- **历史记录轮转** (`history.py`): `history/tasks.jsonl` 超过 10 MB 时自动修剪至最近一半记录
- **Oracle 客户端刷新** (`reasoning_oracle.py`): 当 API 密钥或端点变更时自动重建 HTTP 客户端，不再复用旧连接

### 启动优化

- **延迟目录创建** (`config.py`): `SCREENSHOTS_DIR.mkdir()` 不再在 import 时执行，改为按需调用 `ensure_screenshots_dir()`
