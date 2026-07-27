# auto-pr-io 接手文档

本文记录前期对项目做过的改造，以及后续继续对接 Windows / Android 自动操作时需要关注的入口、配置和未完成事项�?
## 1. 项目目标

当前项目是一�?Windows 桌面 GUI 工具，核心能力包括：

- 截取 Windows 屏幕、区域或窗口截图�?- 将截图发送给 VLM 进行分析�?- 通过模型返回的动作自动操�?Windows 桌面�?- 通过 ADB 截图�?`adb shell input` 自动操作 Android 手机�?- �?GUI 中集中管�?API �?ADB 配置，减少命令行操作�?- �?GUI 中实时查看运行日志和错误�?
入口仍然是：

```powershell
.\.venv312\Scripts\python.exe main.py
```

## 2. 重要改动概览

### 2.1 Tkinter/Tcl 启动修复

相关文件�?
- `main.py`
- `tk_bootstrap.py`
- `sitecustomize.py`
- `.runtime/tcl/`

问题背景�?
本机 Python313 �?Tcl/Tk 初始化会�?`Can't find a usable init.tcl`。排查发现系�?PATH 中存�?Anaconda �?Tcl DLL，同�?Python313 原始 Tcl 路径在当前环境下解析异常�?
处理方式�?
- �?Python313 �?Tcl/Tk 运行库复制到项目�?`.runtime/tcl/`�?- �?`main.py` 导入 `tkinter` 前调�?`configure_tk_runtime()`�?- `tk_bootstrap.py` 会优先设置：
  - `TCL_LIBRARY=.runtime/tcl/tcl8.6`
  - `TK_LIBRARY=.runtime/tcl/tk8.6`
  - Python313 `DLLs` 路径优先进入 `PATH`

注意�?
不要�?`import tkinter` 移到 `configure_tk_runtime()` 之前，否�?GUI 可能再次启动失败�?
`.runtime/tcl/` 目录是本机专用拷贝，不提交到版本控制。换机器时需重新�?Python 安装目录拷贝对应版本�?`tcl8.6/` �?`tk8.6/`�?
### 2.2 设置系统

相关文件�?
- `settings_store.py`
- `ui/settings_dialog.py`
- `config.py`

新增持久化配置文件：

```text
settings.json
```

该文件运行时生成，不应写死用户真�?API Key。设置窗口位于：

```text
Settings -> API and ADB settings
```

目前保存的配置包括：

- OpenAI API Key / API Base / 默认模型
- Anthropic API Key / 默认模型
- Zhipu API Key / API Base / 默认模型
- Custom OpenAI-compatible API（Key + Base + Model�?- Generic VLM coordinates API（Key + Base + Model�?- AutoGLM-Phone API
- ADB path
- 最近选择�?ADB device id

代码读取设置的主要函数：

- `settings_store.load_settings()`
- `settings_store.save_settings(settings)`
- `settings_store.get_provider_settings(provider)`
- `settings_store.get_adb_settings()`
- `settings_store.update_adb_device(device_id)`

### 2.3 API 输入移出首页

相关文件�?
- `ui/vlm_panel.py`
- `ui/auto_click_panel.py`

现在首页不再直接展示 API Key/API Base 输入框�?
VLM 分析面板只保留：

- Provider
- Model
- Temperature
- Max tokens
- Prompt template
- Prompt

发送时通过 `settings_store.get_provider_settings(provider)` 读取 API Key �?API Base�?
Auto-click 面板也不再要求用户在首页�?API，而是在启动任务时根据后端自动读取对应配置�?
## 3. 自动操作架构

### 3.1 总调度器

相关文件�?
- `auto_click/clicker.py`

核心类：

```python
AutoClicker
```

支持�?backend�?
```python
"openai"        # Windows - OpenAI Computer Use
"vlm_coords"    # Windows - Generic VLM coordinates
"openai_adb"    # Android ADB - OpenAI Computer Use
"adb_vlm"       # Android ADB - Generic VLM coordinates
"autoglm_phone" # Android ADB - AutoGLM-Phone
"anthropic"     # 预留，当前缺�?anthropic_cu.py（见 §7.5�?```

主要流程�?
1. `_setup_backend()` 初始化模型后端�?2. `_setup_executor()` 初始化执行器�?3. `_capture_screenshot_b64()` 获取当前目标截图�?   - Windows：`pyautogui.screenshot()`
   - Android：`ADBController.screenshot_b64()`
4. `_run_loop()` 循环�?   - 发截图给模型
   - 模型返回 action
   - executor 执行动作
   - 再截图继�?5. `{"type": "done"}` 作为循环终止信号；`max_steps` 作为安全上限�?
`autoglm_phone` 走独立的 `_run_phone_task()` 路径，不经过上述循环�?
### 3.2 Windows 执行�?
相关文件�?
- `auto_click/executor.py`

核心类：

```python
ActionExecutor
```

通过 `pyautogui` 执行动作�?
支持动作�?
- `click`
- `double_click`
- `move`
- `drag`（支持路径数组或单目标点�?- `scroll`（direction/amount�?- `type`（`pyautogui.write`�?- `key` / `keypress`（支持热键组合和单键�?- `wait`
- `screenshot`（no-op，截图由 clicker 统一负责�?- `done`（no-op，终止信号）

内部�?`_held_modifiers()` 上下文管理器�?`_normalize_key()` 键名映射（CTRL→ctrl、CMD→win 等）。所有坐标通过 `pyautogui.size()` 做边界检查�?
### 3.3 Android ADB 控制�?
相关文件�?
- `auto_click/adb.py`

核心类：

```python
ADBController
ADBActionExecutor
```

`ADBController` 负责�?
- `adb devices`（枚举设备，返回 `DeviceInfo` 列表�?- `ensure_ready(device_id)` 验证设备状�?- `adb exec-out screencap -p`（截图为 PNG bytes�?- `adb shell input tap`
- `adb shell input swipe`
- `adb shell input text`（含 shell 转义�?- `adb shell input keyevent`

`ADBActionExecutor` 负责把模�?action 转换�?ADB 命令�?
支持动作�?
- `click` / `tap`
- `double_click` / `double_tap`
- `drag` / `swipe`
- `scroll`
- `type`
- `key` / `keypress`（通过 `KEY_MAP` 映射 keyevent 码）
- `back`
- `home`
- `wait`
- `screenshot`
- `done`

注意�?
`adb shell input text` 对中文和特殊字符支持有限。如果后续要稳定输入中文，建议新增剪贴板方案，例如：

- ADB Keyboard
- `am broadcast` 输入�?- Appium / uiautomator2 输入接口

## 4. 模型后端

### 4.1 OpenAI Computer Use

相关文件�?
- `auto_click/backends/openai_cua.py`

核心类：

```python
OpenAIComputerBackend
OpenAICUABackend = OpenAIComputerBackend  # 别名
```

当前实现�?
- 使用 OpenAI Responses API（`client.responses.create`）�?- 默认模型�?`gpt-5.5`�?- 模型名不�?`computer-use-preview` 开头时使用新工具格式：

```python
tools=[{"type": "computer"}]
```

- 对旧 `computer-use-preview` 兼容�?
```python
tools=[{
    "type": "computer_use_preview",
    "display_width": ...,
    "display_height": ...,
    "environment": ...
}]
```

- 通过 `previous_response_id` 维持对话状态�?- 处理 `acknowledged_safety_checks` 字段�?- `_normalize_action()` �?`keypress` 统一�?`key`，归一�?`scroll_y`�?
OpenAI 后端�?`openai` �?`openai_adb` 两种 backend 中复用，区别是：

- `openai` 执行器为 Windows `ActionExecutor`
- `openai_adb` 执行器为 Android `ADBActionExecutor`

### 4.2 Generic VLM coordinates

相关文件�?
- `auto_click/backends/vlm_coords.py`

核心类：

```python
VLMCoordsBackend
```

这是通用 OpenAI-compatible fallback�?
它要求模型每次只返回一�?JSON action，例如：

```json
{"type": "click", "x": 100, "y": 200}
```

支持 `target_context` 参数区分 Windows �?Android 语境（影�?system prompt）。会自动剥除模型回复中的 Markdown 代码围栏�?
优点�?
- 可以接本地模型或第三�?OpenAI-compatible API�?- 同时支持 Windows �?Android ADB�?
缺点�?
- 稳定性弱于专门的 Computer Use 工具�?- 模型必须严格遵守 JSON 输出（当前无 schema 校验和自动重试，�?§8.8）�?
### 4.3 AutoGLM-Phone

相关文件�?
- `auto_click/backends/autoglm_phone.py`

当前实现是适配外部 Open-AutoGLM 包：

```python
from phone_agent import PhoneAgent
```

如果 `phone_agent` 未安装，构造时抛出 `RuntimeError` 并提示安装方式，不会导致其他 backend 崩溃（懒加载）�?
注意�?
该包当前没有随项目安装。使用前需要后续人员自行确�?Open-AutoGLM 的安装方式和版本兼容性�?
AutoGLM-Phone 定位�?Android/HarmonyOS 手机 Agent，不�?Windows 桌面自动化方案�?
### 4.4 Anthropic Computer Use（未实现�?
`auto_click/clicker.py` 中保留了 `"anthropic"` 分支，但对应后端文件不存在：

```text
auto_click/backends/anthropic_cu.py   �?缺失
```

选择�?backend 时会在运行时抛出 `ImportError`。详�?§7.5�?
## 5. GUI 改�?
### 5.1 主窗�?
相关文件�?
- `ui/main_window.py`

主窗口现在包括：

- 左侧：`CapturePanel`（截图控制）
- 中间：`ImagePreviewPanel`（图像预览）
- 右侧页签�?  - `VLM`（`VLMPanel`�?  - `Auto-click`（`AutoClickPanel`�?- 底部页签�?  - `VLM result`（`ResultPanel`�?  - `Run log`（`LogPanel`�?
菜单�?
```text
File -> Save screenshot
Settings -> API and ADB settings
Settings -> Clear result
```

保存设置后会自动调用 `vlm_panel.reload_settings()` �?`auto_click_panel.reload_settings()`，刷新面板中的模型默认值�?
### 5.2 自动点击面板

相关文件�?
- `ui/auto_click_panel.py`

当前用户流程�?
1. 打开 Settings 配好 API �?ADB path�?2. �?Auto-click 面板选择 backend�?3. Android backend 会显�?ADB 设备区域�?4. 点击 `Refresh` 自动扫描设备�?5. 从下拉框选择设备�?6. 填任务描述�?7. 点击 `Start`�?
ADB 设备状态显示逻辑�?
- `ADBController.list_devices()` 获取所有设备�?- 下拉框显�?`device_id (state)`�?- 实际启动时只�?`device_id` �?`AutoClicker`�?- `AutoClicker` 内部 `ADBController.ensure_ready()` 会拒绝未 ready 的设备�?
### 5.3 日志面板

相关文件�?
- `ui/log_panel.py`

新增�?
```python
TkLogHandler   # 队列驱动，线程安�?LogPanel       # �?200ms 通过 after() 轮询队列
```

`MainWindow._install_log_handler()` 会把 handler 加到 root logger�?
后续只要使用标准 logging�?
```python
logger.info("...")
logger.exception("...")
```

就会实时显示�?GUI �?`Run log` 页签里�?
### 5.4 Settings 对话�?
相关文件�?
- `ui/settings_dialog.py`

Notebook 布局，包含两个页签：

- **API 页签**�? �?provider �?Key / Base / Model 输入（可滚动 Canvas）�?  - openai、anthropic、zhipu、custom、vlm_coords、autoglm_phone
- **ADB 页签**：ADB 可执行文件路径�?
保存时写�?`settings.json`，并回调 `on_save` 通知主窗口刷新面板�?
## 6. 完整文件清单

以下是项目所有源文件（不�?`.venv312/`、`__pycache__/`、`.runtime/`）：

### 根目�?
| 文件 | 状�?| 说明 |
|---|---|---|
| `main.py` | �?完整 | 入口，调�?`configure_tk_runtime()` 后再导入 tkinter |
| `config.py` | �?完整 | 全局配置，支�?`.env` 覆盖 |
| `settings_store.py` | �?完整 | `settings.json` 读写�? provider + ADB |
| `tk_bootstrap.py` | �?完整 | Tcl/Tk 路径引导，机器专�?|
| `sitecustomize.py` | �?完整 | Python 站点定制（Tcl 辅助�?|
| `requirements.txt` | �?完整 | �?ASCII，无中文注释 |
| `work.md` | �?本文 | 接手文档 |

### `windows/`

| 文件 | 状�?| 说明 |
|---|---|---|
| `__init__.py` | �?| 包标�?|
| `capture.py` | �?完整 | 全屏/区域/窗口截图，`RegionCaptureOverlay` 拖�?|
| `window_selector.py` | �?完整 | 可选窗口列表对话框 |

### `vlm/`

| 文件 | 状�?| 说明 |
|---|---|---|
| `__init__.py` | �?| 包标�?|
| `models.py` | �?完整 | `VLMConfig` dataclass，`PROVIDER_DEFAULTS` |
| `prompt_manager.py` | �?完整 | 5 内置模板 + JSON 持久化自定义模板 |
| `client.py` | �?完整 | �?provider 发图，懒加载 SDK |

### `ui/`

| 文件 | 状�?| 说明 |
|---|---|---|
| `__init__.py` | �?| 包标�?|
| `main_window.py` | �?完整 | 主窗口布局，菜单，日志 handler |
| `capture_panel.py` | �?完整 | 截图控制面板 |
| `image_preview.py` | �?完整 | 图像预览组件 |
| `result_panel.py` | �?完整 | VLM 结果显示 |
| `vlm_panel.py` | �?完整 | VLM 参数配置，不�?API Key 输入 |
| `auto_click_panel.py` | �?完整 | 自动操作控制面板 |
| `settings_dialog.py` | �?完整 | API + ADB 配置对话�?|
| `log_panel.py` | �?完整 | 实时日志面板，队列驱�?|

### `auto_click/`

| 文件 | 状�?| 说明 |
|---|---|---|
| `__init__.py` | �?| 包标�?|
| `clicker.py` | �?完整 | 总调度器�? backend 分支 |
| `executor.py` | �?完整 | Windows pyautogui 执行�?|
| `adb.py` | �?完整 | Android ADB 控制层和执行�?|
| `backends/__init__.py` | �?| 包标�?|
| `backends/openai_cua.py` | �?完整 | OpenAI Computer Use 后端 |
| `backends/vlm_coords.py` | �?完整 | Generic VLM JSON 坐标后端 |
| `backends/autoglm_phone.py` | �?完整 | AutoGLM-Phone 适配层（外部依赖�?|
| `backends/anthropic_cu.py` | �?**缺失** | Anthropic Computer Use �?未实�?|
| `backends/reasoning_oracle.py` | �?完整 | 推理 Oracle 客户端（DeepSeek-R1 / o3 / Claude Opus�?|

**合计�?9 个源文件已实现，1 个缺失（`anthropic_cu.py`）�?*

## 7. 运行和验�?
### 7.1 编译检�?
```powershell
.\.venv312\Scripts\python.exe -m compileall -q main.py tk_bootstrap.py sitecustomize.py settings_store.py ui windows vlm auto_click
```

### 7.2 GUI 启动

```powershell
.\.venv312\Scripts\python.exe main.py
```

### 7.3 ADB 检�?
用户不再必须手动执行 `adb devices`，但开发调试时可用�?
```powershell
adb devices
```

GUI 内部会通过 `Refresh` 按钮调用同样逻辑�?
## 8. 已知问题和后续建�?
### 8.1 需要补 README

目前还没有面向普通用户的 README。建议后续补�?
- 安装依赖
- 配置 API
- 连接 Android 手机
- Windows 自动化使用示�?- Android 自动化使用示�?- 常见错误排查

### 8.2 需要增加依�?环境检�?
建议启动时检查：

- `adb` 是否可用
- OpenAI SDK 是否可用
- `pyautogui` 屏幕权限
- Tk runtime 是否可用（`.runtime/tcl/` �?`sys.base_prefix/tcl`�?- `settings.json` 是否可写

### 8.3 ADB 输入中文能力不足

当前 `adb shell input text` 只适合简单英文和符号。中文输入建议接�?
- ADB Keyboard
- uiautomator2
- Appium

### 8.4 网页任务建议引入 Playwright

对于邮件、网页购物、网页表单，Playwright 比纯视觉坐标点击更稳定。推荐架构：

- 网页任务优先 Playwright DOM 操作
- 桌面软件和手�?App �?Computer Use / VLM + 截图坐标

### 8.5 Anthropic Computer Use 尚未实现

`auto_click/clicker.py` 中保留了 `"anthropic"` 分支，但当前缺少�?
```text
auto_click/backends/anthropic_cu.py
```

选择�?backend 时会在运行时抛出 `ImportError`。如需实现，参考要点：

- 使用 `anthropic` SDK，模�?`claude-3-5-sonnet-20241022` 或更新�?- 请求头需包含 beta 标志：`anthropic-beta: computer-use-2024-10-22`�?- 工具类型�?`computer_20241022`，需提供 `display_width_px` / `display_height_px`�?- 支持动作：`left_click`、`type`、`key`、`scroll`、`drag`、`screenshot`�?- 动作需映射�?`ActionExecutor` / `ADBActionExecutor` 格式�?
若不计划支持，建议从 UI 中彻底移�?`"anthropic"` 选项，避免误导用户�?
### 8.6 AutoGLM-Phone 仍是外部依赖

`auto_click/backends/autoglm_phone.py` 只是适配层。后续需要确认：

- Open-AutoGLM 安装方式
- `phone_agent` API 是否稳定
- ADB/HDC 设备选择如何和本项目设置联动

### 8.7 安全确认逻辑目前较弱

当前 `Log each action before execution` 主要是记录动作，不是真正阻塞式确认�?
如果要用于真实发送消息、邮件或购物，建议新增：

- 高风�?action 拦截
- 发�?下单/付款前确认弹�?- 目标 App / 网址白名�?- 最大金额、联系人白名单等策略

### 8.8 `.runtime/tcl/` 机器绑定

`.runtime/tcl/` 是从本机 Python313 安装目录手动拷贝的，不应提交到版本控制�?
新机器部署时�?
1. 确认 Python 版本（项目当前使�?Python 3.13.x）�?2. �?`%PYTHON_HOME%\tcl\tcl8.6\` �?`%PYTHON_HOME%\tcl\tk8.6\` 复制到项�?`.runtime\tcl\`�?3. 或者直接确�?`sys.base_prefix/tcl/tcl8.6/init.tcl` 存在，`tk_bootstrap.py` 会自动找到�?
## 9. 后续接手优先�?
建议按以下顺序继续：

1. �?README �?`.env.example`（低风险，高价值）�?2. 增加启动时环境诊断面板（adb / SDK / Tk 可用性检查）�?3. **实现 `auto_click/backends/anthropic_cu.py`**（或�?UI 移除该选项）�?4. �?Android ADB 增加截图预览�?5. �?ADB 增加中文输入方案（推�?uiautomator2）�?6. 增加 Playwright 网页自动�?backend�?7. 增加任务模板�?   - 回复当前消息
   - 回复当前邮件
   - 搜索商品并加入购物车
   - 打开 App 并执行指定操�?8. �?`VLMCoordsBackend` 增加 JSON schema 校验和自动重试�?
## 10. 修订记录

| 版本 | 日期 | 内容 |
|---|---|---|
| v0.1 | 2026-03 | Claude Code（Session 1）：初始 GUI 框架，截图模块，VLM 集成，auto-click 预留 |
| v0.2 | 2026-03 | Claude Code（Session 2）：AutoGLM-Phone �?OpenAI Computer Use 调研，ADB 控制层，�?backend 架构设计 |
| v0.3 | 2026-04 | Codex（gpt-5.5）独立完成：settings 系统、日志面板、所�?backend 实现、GUI 全面重构；产出本�?v0.3（原�?`work.md`�?|
| v0.4 | 2026-04-30 | Claude Code：校验全部源文件，补充完整文件清单（§6），更新已知问题，标�?`anthropic_cu.py` 缺失细节和新机器部署注意事项 |
| v0.5 | 2026-04-30 | Claude Code + Codex：新�?Oracle 推理层——`reasoning_oracle.py`、`ask_oracle` action 循环、Settings Oracle 标签页、两�?backend 提示词更新，支持 DeepSeek-R1 / o3-mini / Claude Opus |
