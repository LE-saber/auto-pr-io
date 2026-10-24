# auto-pr-io

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md)

**以 Windows GUI 操作視覺設備自動化，並觀察 Android 畫面與音訊。**

將擷取畫面、視覺語言模型、結構化動作與裝置執行器串成可觀察的循環。Windows 動作使用 `pyautogui`，Android 使用 ADB。現行入口 `main.py` 載入 `ui_v2` Tkinter 介面。

> **實驗性原始碼專案。** 目前沒有已發布的 GitHub 安裝包 Release。模型座標操作取決於供應商、目標應用與裝置；啟動成功不保證任意任務都能可靠完成。

## 兩種模式

| 模式 | 輸入 | 結果 |
| --- | --- | --- |
| Build | Windows 或 Android 畫面與任務 | 模型規劃的點擊、輸入、捲動等支援動作 |
| Chat | Android 畫面與可選的本機語音轉寫 | 只輸出筆記及回答，不操作裝置 |

桌面 Chat 尚非已實作能力。AutoGLM-Phone 是可選介接器，依賴外部 `phone_agent`，不是隨附執行環境。

## 主要能力

- 擷取 Windows 全螢幕、區域或視窗，各步驟保持所選目標。
- 將模型座標換算為畫面像素與桌面位移，執行滑鼠/鍵盤動作，以剪貼簿貼上 Unicode 文字。
- 選取 ADB 裝置、預覽畫面及執行動作；Android 輔助程式提供輸入法與播放音訊擷取。
- 透過 FunASR / SenseVoiceSmall 在本機轉寫音訊，與畫面上下文合併使用。
- 選取 Markdown Skill、設定禁止點擊矩形、查看即時日誌與任務歷史。
- GUI 支援英文、簡體中文、繁體中文及日文。

## Windows 快速開始

使用 Windows 10/11 與含 Tkinter 的 Python 3.10–3.12，建議 Python 3.12。Android 功能另需 ADB 及已授權的 USB/無線偵錯連線。語音依賴包含 PyTorch，下載可能較大。

```powershell
git clone https://github.com/LE-saber/auto-pr-io.git
Set-Location .\auto-pr-io
.\start.ps1
```

啟動器尋找相容 Python，建立或修復 `.venv312`，在建立/修復時安裝依賴，檢查 Tcl/Tk 與 ADB 後啟動 GUI。已有有效環境不會自動更新依賴。手動安裝或更新依賴：

```powershell
py -3.12 -m venv .venv312
.\.venv312\Scripts\python.exe -m pip install -r requirements.txt
.\.venv312\Scripts\python.exe main.py
```

在 **Settings → API and ADB settings** 輸入供應商端點、模型、Key 及所需 ADB 路徑。選擇桌面擷取目標或 Android 裝置與 Build/Chat 模式，先做結果容易核對的小任務。桌面入口包含 GLM、豆包、千問；Android 另有通用座標等介接器，可用性取決於帳號及模型權限。

## Android 音訊與輸入

[輔助程式說明](android/AutoPrKeyboardAudio/README.md) 含原始碼、建置與安裝步驟。套件名為 `com.autopr.keyboardaudio`，IME 為 `com.autopr.keyboardaudio/.AdbImeService`。

專案記錄的播放擷取環境需要 Android 13+、MediaProjection 同意及目標應用允許擷取。通話、受保護媒體及禁止擷取的應用可能產生靜音。本機 `recordings/` 保留錄音及轉寫文字，預設 ASR 模型為 `iic/SenseVoiceSmall`。

## 設定、資料與限制

- 偏好存於 `settings.json`。Windows 優先使用 DPAPI 儲存 Key；`b64_unprotected:` 是可逆編碼，**不是加密**。
- 畫面、錄音與 `history/tasks.jsonl` 可能含任務資料。模型請求將所選畫面及上下文送往設定的供應商；本機 ASR 不代表整個流程離線。
- 禁點矩形只限制點擊位置，並非完整權限機制；重要操作應直接監督。
- 模型 JSON 可能無效、座標可能不準；Android 輸入相容性因系統和應用而異。
- 本專案未提供瀏覽器 DOM 自動化、完整確認/授權體系或生產可靠性保證。

## 原始碼與資料

| 路徑 | 作用 |
| --- | --- |
| [main.py](main.py)、[ui_v2/](ui_v2/) | 現行入口及 GUI |
| [auto_click/](auto_click/) | 主循環、後端、ADB、音訊、Skill 與歷史 |
| [windows/](windows/) | 螢幕、區域及視窗擷取 |
| [settings_store.py](settings_store.py) | 設定及 Key 儲存 |
| [skills/](skills/) | 含 CIDA/VocabGo 的任務規則 |
| [tests/](tests/) | 既有迴歸測試 |
| [ui/](ui/) | 保留的舊 GUI，非主入口 |

[原完整簡體中文指南](README.reference.zh-CN.md) 保留動作協定、座標換算、CIDA 模式、後端、測試及路線圖。[PROJECT_INTRO.md](PROJECT_INTRO.md) 補充專案資訊；[DESIGN.md](DESIGN.md)、[HANDOVER.md](HANDOVER.md)、[work.md](work.md) 為設計及歷史紀錄，應依當時快照理解。

## 開發檢查

在已設定的 Windows 環境執行：

```powershell
.\.venv312\Scripts\python.exe -m compileall auto_click ui ui_v2 settings_store.py tests
.\.venv312\Scripts\python.exe tests\test_20260506_fixes.py
.\.venv312\Scripts\python.exe tests\test_desktop_runtime.py
.\.venv312\Scripts\python.exe tests\test_ui_v2_contract.py
```

這些是既有檢查命令，不是本次文件更新聲稱取得的測試結果。真實模型及裝置檢查需要對應環境。根目錄沒有統一授權聲明，依賴保留各自授權。
