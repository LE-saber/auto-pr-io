# auto-pr-io 项目交接文档

## 项目概述

**auto-pr-io** 是一个基于视觉语言模型（VLM）的智能屏幕自动化工具。它通过集成 OpenAI、Anthropic、智谱清言等多�?VLM 服务，实现了 Windows 桌面�?Android 设备的自动化控制。用户可以用自然语言描述任务，系统自动分析屏幕截图，识别 UI 元素坐标，执行点击、滑动、输入等操作�?
**核心能力�?*
- Windows 桌面自动化：通过 VLM 视觉识别�?pyautogui 实现点击、输入、滑�?- Android 自动化：通过 ADB 连接，支持无线和 USB 两种连接方式
- 多后端支持：OpenAI Computer Use、通用 VLM JSON 坐标提取、AutoGLM-Phone
- 推理层增强：集成 DeepSeek 等推理模型作�?Oracle，处理复杂逻辑
- 音频捕获与转文字：支�?Android 13+ 设备录音并用 Whisper 转录
- 图形界面：基�?Tkinter 的易用操作面�?
---

## 项目结构

```
auto-pr-io/
├── main.py                          # 应用入口，初始化 Tkinter GUI
├── config.py                        # 全局配置（API 密钥、路径等�?├── settings_store.py                # 持久化配置管理（settings.json�?├── requirements.txt                 # Python 依赖清单
├── start.bat / start.ps1            # Windows 一键启动脚�?├── fix_adb_driver.ps1               # ADB 驱动修复工具（vivo USB 驱动�?├── sitecustomize.py                 # Python 启动定制（预留）
├── tk_bootstrap.py                  # Tkinter 运行库初始化
�?├── auto_click/                      # 自动化核心模�?�?  ├── clicker.py                   # AutoClicker 类，支持 5 种后�?�?  ├── adb.py                       # ADB 控制器，负责 Android 交互
�?  ├── audio.py                     # 音频捕获�?Whisper 转录
�?  ├── executor.py                  # VLM 执行引擎
�?  └── backends/
�?      ├── reasoning_oracle.py      # 推理�?Oracle（DeepSeek/OpenAI/Anthropic�?�?      └── ... 其他后端实现
�?├── vlm/                             # VLM 客户端和提示词管�?�?  ├── client.py                    # 统一 VLM 客户�?�?  ├── models.py                    # 模型枚举和元数据
�?  ├── prompt_manager.py            # 提示词模板管�?�?  └── prompt_templates.json        # 系统提示词库
�?├── ui/                              # GUI 组件
�?  ├── main_window.py               # 主窗口和菜单�?�?  ├── settings_dialog.py           # 设置对话�?�?  ├── vlm_panel.py                 # VLM 配置面板
�?  ├── auto_click_panel.py          # 自动化任务面�?�?  ├── capture_panel.py             # 截图和预览面�?�?  ├── result_panel.py              # 执行结果显示
�?  ├── log_panel.py                 # 日志输出面板
�?  └── image_preview.py             # 图片预览组件
�?├── windows/                         # Windows 特定功能
�?  ├── capture.py                   # mss 截图
�?  └── window_selector.py           # 窗口选择�?�?├── .runtime/                        # Tcl/Tk 运行库（启动脚本自动复制�?├── Screenshots/                     # 截图保存目录（自动创建）
└── settings.json                    # 用户配置文件（自动生成）
```

---

## 环境要求

### Python 版本
- **Python 3.10+** （推�?3.11 �?3.12�?- �?Windows 上安�?Python 时，勾�?"Add Python to PATH"

### 依赖安装

项目使用 `requirements.txt` 管理依赖。启动脚�?`start.bat` / `start.ps1` 会自动创建虚拟环境并安装依赖，无需手动操作�?
**核心依赖�?*
```
Pillow>=10.0.0          # 图片处理
mss>=9.0.0              # Windows 截图
pywin32>=306            # Windows API 调用（DPI 感知等）
openai>=1.30.0          # OpenAI API 客户�?anthropic>=0.28.0       # Anthropic Claude API 客户�?requests>=2.31.0        # HTTP 请求
zhipuai>=2.0.0          # 智谱清言 GLM API
pyautogui>=0.9.54       # 鼠标键盘控制
python-dotenv>=1.0.0    # .env 文件支持
psutil>=5.9.0           # 系统信息获取
```

### 特殊依赖

#### 1. PyTorch + CUDA（用于本�?Whisper 转录�?若使用本�?Whisper 模型进行音频转文字，需�?PyTorch CUDA 支持�?```bash
# CUDA 12.4 版本（推�?RTX 40 系或 30 系）
pip install torch==2.6.0+cu124 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# �?CPU 版本（速度慢，不推荐）
pip install torch torchvision torchaudio
```

#### 2. openai-whisper（音频转文字�?若启用本地转录模式：
```bash
pip install openai-whisper
```
首次使用会自动下载模型文件（~1.5GB，默�?`large-v3-turbo` 模型）�?
#### 3. phone-agent（AutoGLM-Phone 后端�?已在 `requirements.txt` 中集成，无需单独安装�?
#### 4. FFmpeg（音频处理）
Whisper 需�?FFmpeg 来处理音频文件�?
**Windows 安装 FFmpeg�?*
```bash
# 使用 Chocolatey
choco install ffmpeg

# 或手动安�?# 1. 下载：https://ffmpeg.org/download.html
# 2. 解压到如 C:\ffmpeg
# 3. 添加�?PATH 环境变量
# 4. 验证：ffmpeg -version
```

#### 5. ADB（Android 调试桥）
用于连接和控�?Android 设备�?
**Windows 安装 ADB�?*
- 官方 Android SDK Platform-Tools：https://developer.android.com/tools/releases/platform-tools
- 或通过包管理器：`choco install adb`
- 解压后添加路径到 PATH 环境变量，或�?Settings 中手动指�?ADB 路径

---

## 快速启�?
### Windows 一键启�?
#### 方法一：start.bat（推荐）
在项目目录中直接双击 `start.bat`，或在命令行运行�?```cmd
start.bat
```

#### 方法二：start.ps1（PowerShell�?右键 `start.ps1`，选择"�?PowerShell 运行"，或�?PowerShell 中：
```powershell
.\start.ps1
```

**启动脚本自动完成以下步骤�?*
1. 检�?Python 安装
2. 创建 `.venv312` 虚拟环境（如不存在）
3. 安装 `requirements.txt` 中的依赖
4. 检查和复制 Tcl/Tk 运行库到 `.runtime/`
5. 验证 ADB 可用性（可选）
6. 启动 GUI 应用

### 手动启动

若不使用启动脚本，可手动执行�?```bash
# 创建虚拟环境
python -m venv .venv312

# 激活虚拟环�?.venv312\Scripts\activate         # Windows
source .venv312/bin/activate      # Linux/Mac

# 安装依赖
pip install -r requirements.txt

# 启动应用
python main.py
```

---

## 功能模块说明

### 1. 后端控制模式（Backend�?
auto-pr-io 支持 5 种自动化后端，在 VLM 面板中选择�?
#### OpenAI Computer Use
- **用�?*：使�?OpenAI 最新的原生计算机使用能力（支持 gpt-4o 等）
- **优势**：识别精度高，直接返回点击坐�?- **需�?*：OpenAI API 密钥
- **平台**：Windows 桌面

#### vlm_coords
- **用�?*：通用 VLM JSON 坐标提取模式，支持任�?OpenAI 兼容 API
- **实现**：发送截图，VLM 返回 JSON 格式的坐�?`{"action": "click", "x": 100, "y": 200}`
- **优势**：支持国�?API（如硅基流动 SiliconFlow、百度千帆等�?- **平台**：Windows 桌面

#### openai_adb
- **用�?*：OpenAI Computer Use �?Android 设备上的应用
- **需�?*：ADB 连接、OpenAI API 密钥
- **平台**：Android

#### adb_vlm
- **用�?*：通用 VLM JSON 坐标提取�?Android 上的应用
- **优势**：支持国�?API，成本低
- **平台**：Android

#### autoglm_phone
- **用�?*：智�?AutoGLM-Phone，专门为手机自动化设计的原生后端
- **优势**：针对手�?UI 优化，效果最�?- **需�?*：智谱清言 API 密钥
- **平台**：Android

---

### 2. Android ADB 控制

#### 无线 ADB 连接（推荐）

**配对步骤（首次连接）�?*

1. 启用开发者选项和无线调�?   - Android 设备设置 �?关于手机 �?连续点击"版本�? 7 �?   - 返回上一级，进入"开发者选项"
   - 启用"USB 调试"�?无线调试"

2. 获取配对信息
   - 点击"无线调试"
   - 记下设备 IP 地址和端口（�?`192.168.1.100:37847`�?   - 进入"配对"，记下配对码（如 `123456`�?
3. 配对设备
   ```bash
   adb pair <设备IP>:<端口> <配对�?
   # 例：adb pair 192.168.1.100:37847 123456
   ```
   成功后会显示 "Successfully paired"

4. 连接设备
   ```bash
   adb connect <设备IP>:<无线调试端口>
   # 例：adb connect 192.168.1.100:50286
   ```

5. 验证连接
   ```bash
   adb devices
   ```
   看到设备列表中出�?`设备IP:端口  device` 即表示连接成�?
**注意事项�?*
- 手机重启后需重新连接（或�?auto-pr-io 设置中勾�?启动时自动连�?�?- 确保手机和电脑在同一 WiFi 网络
- 无线 ADB 端口每次重启可能变化，以设备上显示的端口为准

#### USB ADB 连接

1. �?USB 线连接手机和电脑
2. �?Android 设备上允�?USB 调试"
3. 验证连接：`adb devices`

**vivo USB 驱动问题�?*
某些 vivo 手机需要特殊驱动。使�?`fix_adb_driver.ps1` 自动修复�?```powershell
# 以管理员身份运行
.\fix_adb_driver.ps1
```
该脚本会�?- 下载 Google USB 驱动
- 自动注入 vivo 设备 ID（VID_2D95�?- 打开设备管理器，指导手动安装驱动

或者安�?vivo 官方 PC Manager 也能解决问题�?
#### ADB 路径配置

�?ADB 不在 PATH 中，可在 Settings 中手动指定：
- 打开 auto-pr-io
- 点击"Settings"
- 进入"ADB"标签
- 填写完整 ADB 路径（如 `D:\Android\platform-tools\adb.exe`�?
---

### 3. Oracle 推理�?
**用途：** �?VLM 遇到复杂的逻辑决策时，调用外部推理模型（如 DeepSeek-R1）进行深度推理�?
**场景示例�?*
- 识别 UI 后，需判断"当前应该点击哪个按钮来完成目�?
- 处理条件逻辑和流程控�?
**配置步骤�?*

1. 打开 Settings �?Oracle 标签
2. 勾�?启用 Oracle"
3. 选择推理模型提供商：
   - **deepseek**（推荐）：deepseek-v4-pro / deepseek-reasoner
   - **openai**：o3-mini / o1（需 paid API�?   - **anthropic**：claude-opus-4-6
   - **custom**：自定义 API 端点

4. 填写 API 密钥
5. 填写 API Base URL（若使用自定义端点）
6. 填写模型名称
7. 设置超时时间（默�?120 秒）

**默认配置�?*
- 提供商：DeepSeek
- 模型：deepseek-v4-pro
- API Base：https://api.deepseek.com/v1
- 超时�?20 �?
**获取 DeepSeek API 密钥�?*
- 访问 https://platform.deepseek.com
- 注册账户，获�?API 密钥
- 充值（�?token 计费�?
---

### 4. 音频捕获与转�?
**支持条件�?*
- 仅限 Android 13+ 设备
- 需启用 ADB 连接

**工作流程�?*
1. 通过 `adb screenrecord --audio` 录制设备音频
2. 下载录制文件到本�?3. 使用 Whisper 模型转录为文�?4. 返回转录结果�?VLM

**两种转录模式�?*

#### Local 模式（推荐，但需 GPU�?- 使用本地 openai-whisper �?- 首次运行会自动下载模型（~1.5GB�?- 推荐模型：`large-v3-turbo`（平衡速度和准确度�?- 需求：
  - PyTorch CUDA 支持（RTX 4060+ 推荐�?  - FFmpeg 安装

**优势�?*
- 速度快（GPU 加速）
- 无隐私泄�?- 成本�?
#### API 模式
- 调用 OpenAI Whisper API 或兼容服�?- 支持的提供商�?  - OpenAI（https://api.openai.com/v1�?  - SiliconFlow（https://api.siliconflow.cn/v1，推荐国内用户）
  - Groq（https://api.groq.com/openai/v1�?
**配置步骤�?*

1. 打开 Settings �?Audio 标签
2. 勾�?启用音频捕获"
3. 选择转录模式�?   - **local**：本�?Whisper
   - **api**：API 调用

4. 若选择 API 模式�?   - 填写 API 密钥
   - 填写 API Base URL
   - 填写模型名称（默�?`whisper-1`�?
5. 若选择 Local 模式�?   - 填写本地模型名称（默�?`large-v3-turbo`�?   - 确保 PyTorch CUDA 版本匹配

6. 设置录音时长（默�?3 秒）

---

### 5. Settings 配置说明

Settings（`settings.json`）包含所有用户配置，持久化保存�?
#### Providers（VLM 提供商）

**openai**
```json
{
  "api_key": "sk-...",
  "api_base": "https://api.openai.com/v1",
  "model": "gpt-4o"  // �?gpt-5.5（付费用户）
}
```

**anthropic**
```json
{
  "api_key": "sk-ant-...",
  "model": "claude-3-5-sonnet-20241022"
}
```

**zhipu**（智谱清言�?```json
{
  "api_key": "...",
  "api_base": "https://open.bigmodel.cn/api/paas/v4",
  "model": "glm-4v"  // 视觉模型
}
```

**custom**（自定义 OpenAI 兼容 API�?```json
{
  "api_key": "...",
  "api_base": "https://custom-api.example.com/v1",
  "model": "custom-model"
}
```

**vlm_coords**（JSON 坐标提取�?- 使用 custom �?API 配置
- 模型应支�?JSON 输出

**autoglm_phone**（智�?AutoGLM�?```json
{
  "api_key": "...",  // 智谱 API 密钥
  "api_base": "https://open.bigmodel.cn/api/paas/v4",
  "model": "autoglm-phone"
}
```

#### ADB 设置

```json
{
  "path": "adb",                    // ADB 可执行文件路�?  "last_device_id": "192.168.1.100:50286"  // 上次连接的设�?}
```

#### Oracle 设置

```json
{
  "enabled": false,                 // 是否启用推理�?  "provider": "deepseek",           // 推理模型提供�?  "api_key": "sk-...",
  "api_base": "https://api.deepseek.com/v1",
  "model": "deepseek-v4-pro",       // 推理模型�?  "timeout": 120
}
```

#### Audio 设置

```json
{
  "enabled": false,
  "whisper_api_key": "",            // Whisper API 密钥
  "whisper_api_base": "https://api.openai.com/v1",
  "duration_s": 3                   // 录音时长（秒�?}
```

---

## 已知问题 & 注意事项

### 1. vivo USB ADB 驱动
**问题�?* vivo 手机通过 USB 连接时设备管理器显示"未识�?�?AndroidUsbDeviceClass"�?
**解决方案�?*
- 运行 `fix_adb_driver.ps1`（自动注�?vivo 驱动�?- 或安�?vivo 官方 PC Manager（包含完整驱动）
- 或下�?vivo USB 驱动包手动安�?
### 2. 无线 ADB 连接丢失
**问题�?* 手机重启�?ADB 连接断开�?
**解决方案�?*
- �?Settings �?ADB 中勾�?启动时自动连�?（若实现�?- 或手动重新连接：`adb connect <设备IP>:<端口>`
- 检查手机和电脑是否在同一 WiFi 网络

### 3. AutoGLM-Phone 依赖问题
**问题�?* `ModuleNotFoundError: No module named 'phone_agent'`

**解决方案�?*
- `phone_agent` 已集成在 requirements.txt �?- 若仍缺失，手动安装：`pip install phone-agent`

### 4. PyTorch CUDA 版本不匹�?**问题�?* 本地 Whisper 加载失败，或 CUDA 设备无法识别�?
**解决方案�?*
- 确认本地 CUDA 版本：`nvidia-smi`
- 根据 CUDA 版本重装 PyTorch�?  ```bash
  # CUDA 12.4
  pip install torch==2.6.0+cu124 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124 --force-reinstall
  ```
- 或使�?CPU 版本（速度慢）�?  ```bash
  pip install torch torchvision torchaudio --force-reinstall
  ```

### 5. FFmpeg 未安�?**问题�?* "ffmpeg not found" �?Whisper 音频处理失败�?
**解决方案�?*
- Windows�?  ```bash
  choco install ffmpeg
  # 或手动下载：https://ffmpeg.org/download.html
  ```
- 验证安装：`ffmpeg -version`

### 6. Tkinter GUI 启动失败
**问题�?* "No module named 'tkinter'" �?_tkinter.TclError"�?
**解决方案�?*
- 启动脚本 `start.bat` / `start.ps1` 会自动复�?Tcl/Tk 运行�?- 若仍失败，重新安�?Python（勾�?tcl/tk 组件�?- 或手动安装：`pip install tk`

### 7. OpenAI API 配额不足
**问题�?* API 返回 429 �?quota exceeded�?
**解决方案�?*
- 检�?OpenAI 账户余额：https://platform.openai.com/account/billing
- 切换到其�?VLM 提供商（Anthropic、智谱清言、SiliconFlow 等）
- 使用国内 API（如硅基流动）降低成�?
---

## 后续开发建�?
### 1. 国内 Whisper 转录替代
**现状�?* 使用 OpenAI Whisper API 需要国际支付�?
**建议方案�?*
- 接入硅基流动（SiliconFlow）的 Whisper 转录服务
- API 兼容 OpenAI，成本更低，速度更快
- 参考：https://docs.siliconflow.cn/audio/

### 2. USB ADB 驱动优化
**现状�?* vivo 手机需要特殊驱动或额外安装步骤�?
**建议方案�?*
- 集成 vivo 官方驱动到项目（如许可允许）
- 或提供一键安�?vivo PC Manager 的脚�?- 扩展支持其他国产手机品牌（OPPO、小米、荣耀等）

### 3. Oracle 层扩�?**现状�?* 仅支�?DeepSeek、OpenAI、Anthropic�?
**建议方案�?*
- 添加本地 LLM 支持（LLaMA、Mistral 等）
- 支持自托管推理模型（vLLM、Text Generation WebUI�?- 集成更多国内推理模型（通义千问、Kimi 等）

### 4. 多平台支�?**现状�?* 主要面向 Windows�?
**建议方案�?*
- 支持 Linux �?macOS GUI
- 提供 Web 接口（Flask/FastAPI�?- Docker 容器化部�?
### 5. 持久化工作流
**现状�?* 每次仅执行单个任务�?
**建议方案�?*
- 支持任务队列和调�?- 记录操作日志和屏幕录�?- 添加失败重试机制

### 6. 模型选择优化
**现状�?* 用户需手动选择模型�?
**建议方案�?*
- 根据任务复杂度自动选择模型
- 实现模型成本评估和最优路�?- 支持 A/B 测试不同后端

---

## 常见操作

### 如何更新依赖
```bash
# 激活虚拟环�?.venv312\Scripts\activate

# 更新所有依�?pip install -r requirements.txt --upgrade

# 或更新特定包
pip install --upgrade openai anthropic
```

### 如何查看日志
- �?UI �?"Log" 面板中实时查�?- 或在控制台输出查看完整日�?
### 如何重置设置
```bash
# 删除 settings.json，重启应用会重新生成默认配置
rm settings.json
```

### 如何禁用某个后端
- �?API 密钥为空，该后端会自动禁�?- �?Settings 中清空对应的 API Key 即可

---

## 技术架构简�?
```
用户输入(自然语言)
    �?[UI Main Window]
    �?[Task Description] �?[VLM Client]
    �?              �?[Screenshot Capture] �?[VLM Response]
    �?[AutoClicker - Backend Router]
    ├─ OpenAI Computer Use
    ├─ VLM JSON Coords
    ├─ ADB + OpenAI
    ├─ ADB + VLM JSON
    └─ AutoGLM-Phone
    �?[Oracle - Reasoning Layer（可选）]
    �?[Executor - Action Execution]
    ├─ pyautogui (Windows)
    ├─ ADB (Android)
    └─ Audio Capture & Whisper
    �?[Action Result] �?[Feedback to VLM]
    �?[Loop until task complete or max steps]
```

---

## 联系与支�?
若有问题或建议，请：
1. 查看本文档的"已知问题"部分
2. 检�?GitHub Issues（若项目开源）
3. 联系项目维护�?
祝使用愉快！
