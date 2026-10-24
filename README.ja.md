# auto-pr-io

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md)

**視覚情報によるデバイス操作と、Android の画面・音声の観察を行う Windows GUI。**

スクリーンショット、視覚言語モデル、構造化された操作、デバイス実行器を一つの確認可能なループにまとめます。Windows は `pyautogui`、Android は ADB で操作します。現在の入口は `main.py` で、`ui_v2` の Tkinter UI を起動します。

> **実験的なソースプロジェクト。** GitHub のインストール用 Release はまだありません。座標操作の結果はモデル提供元、対象アプリ、デバイスに依存します。起動できても、任意のタスクが正確に完了する保証はありません。

## 二つのモード

| モード | 入力 | 結果 |
| --- | --- | --- |
| Build | Windows / Android の画面とタスク | モデルが計画したクリック、入力、スクロール等 |
| Chat | Android の画面と任意のローカル音声文字起こし | デバイスを操作せず、メモと回答を出力 |

デスクトップの Chat は実装済み機能として扱っていません。AutoGLM-Phone は外部 `phone_agent` を必要とする任意のアダプターで、実行環境は同梱されません。

## 主な機能

- Windows 全画面、指定領域、指定ウィンドウをキャプチャし、各ステップでも同じ対象を保持。
- モデルの座標を画面内ピクセルとデスクトップ位置へ変換し、マウス/キーボード操作を実行。Unicode 入力にはクリップボード貼付を使用。
- ADB デバイスの選択、画面プレビュー、操作。Android 補助アプリは IME と再生音声キャプチャを提供。
- FunASR / SenseVoiceSmall によるローカル文字起こしを画面情報と組み合わせて利用。
- Markdown Skill、クリック禁止矩形、ライブログ、タスク履歴。
- 英語、簡体字中国語、繁体字中国語、日本語の GUI。

## Windows で開始

Windows 10/11 と Tkinter 付き Python 3.10–3.12 を使用します。推奨は Python 3.12 です。Android には ADB と許可済み USB/無線デバッグ接続が必要です。音声関連には PyTorch などが含まれ、ダウンロードが大きくなることがあります。

```powershell
git clone https://github.com/LE-saber/auto-pr-io.git
Set-Location .\auto-pr-io
.\start.ps1
```

ランチャーは対応 Python を探し、`.venv312` を作成・修復し、その際に依存パッケージをインストールします。その後 Tcl/Tk と ADB を確認して起動します。既存の有効な環境の依存パッケージを自動更新する機能ではありません。手動インストールまたは依存関係の更新は次のとおりです。

```powershell
py -3.12 -m venv .venv312
.\.venv312\Scripts\python.exe -m pip install -r requirements.txt
.\.venv312\Scripts\python.exe main.py
```

**Settings → API and ADB settings** に提供元のエンドポイント、モデル、キー、必要な ADB パスを設定します。画面の対象または Android デバイス、Build/Chat を選び、結果を確認しやすい小さなタスクから始めます。Windows の選択肢は GLM、Doubao、Qwen など、Android には汎用座標等のアダプターがあります。利用可否はアカウントとモデルへのアクセス権によります。

## Android の音声と入力

[補助アプリの説明](android/AutoPrKeyboardAudio/README.md) にソース、ビルド、インストール手順があります。パッケージは `com.autopr.keyboardaudio`、IME は `com.autopr.keyboardaudio/.AdbImeService` です。

文書化された構成では Android 13 以上、MediaProjection の承認、キャプチャを許可する対象アプリが必要です。通話、保護されたメディア、キャプチャ禁止アプリでは無音になる場合があります。録音と文字起こしはローカルの `recordings/` に保存し、既定の ASR モデルは `iic/SenseVoiceSmall` です。

## 設定・データ・制約

- 設定は `settings.json` に保存します。キーには利用可能なら Windows DPAPI を使います。`b64_unprotected:` へのフォールバックは復元可能な符号化で、**暗号化ではありません**。
- 画面、録音、`history/tasks.jsonl` にはタスクデータが含まれ得ます。モデル要求は選択した画面や文脈を設定先へ送ります。ローカル ASR があっても全処理がオフラインとは限りません。
- 禁止矩形はクリック座標を制約するもので、完全な権限機構ではありません。重大な操作は直接監督してください。
- JSON が不正だったり座標が誤ったりする場合があります。Android の入力互換性は OS とアプリに依存します。
- ブラウザー DOM 自動化、完全な確認/権限システム、本番運用の信頼性保証はありません。

## ソースと詳細資料

| パス | 役割 |
| --- | --- |
| [main.py](main.py)、[ui_v2/](ui_v2/) | 現行の入口と GUI |
| [auto_click/](auto_click/) | ループ、バックエンド、ADB、音声、Skill、履歴 |
| [windows/](windows/) | 画面、領域、ウィンドウのキャプチャ |
| [settings_store.py](settings_store.py) | 設定とキー保存 |
| [skills/](skills/) | CIDA/VocabGo を含むタスク手順 |
| [tests/](tests/) | 既存の回帰テスト |
| [ui/](ui/) | 保持された旧 GUI。主入口ではありません |

[従来の詳細中国語ガイド](README.reference.zh-CN.md) には操作プロトコル、座標計算、CIDA モード、バックエンド、テスト、ロードマップを保持しています。[PROJECT_INTRO.md](PROJECT_INTRO.md) は補足説明、[DESIGN.md](DESIGN.md)、[HANDOVER.md](HANDOVER.md)、[work.md](work.md) は設計と過去の記録です。記録は当時の状態として読んでください。

## 開発時の確認

設定済み Windows 環境で実行します。

```powershell
.\.venv312\Scripts\python.exe -m compileall auto_click ui ui_v2 settings_store.py tests
.\.venv312\Scripts\python.exe tests\test_20260506_fixes.py
.\.venv312\Scripts\python.exe tests\test_desktop_runtime.py
.\.venv312\Scripts\python.exe tests\test_ui_v2_contract.py
```

これは既存の確認コマンドであり、この文書更新での成功結果を示すものではありません。実モデル/実機確認には対応環境が必要です。ルートには全体のライセンス宣言がなく、依存ソフトには各自のライセンスが適用されます。
