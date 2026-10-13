# Aredoko

> **最新（2026-10-14、追加確認は一部残る）**：フォルダ/棚/解除・再登録/AI候補のLight/Dark GUIは新batch46checks PASS。初期棚の表示・再登録の除外・一括適用checkbox状態を修正。追加batchは補助HWND参照で停止し、初期棚の修正後表示まで確認。Python14/Core107/Release PASS。右クリック設定と追加復元条件は実機未完了。自動区切りは正解率ではありません。[使い方と検証](docs/folder-search-and-ai-candidates.md)。

> **Windows確認の更新（2026-10-13）**：追加reader/辞書のWindows Release・Core97・Python211は通過。実GUIはLightの辞書・関連/部分一致までで、reader/Dark/JSON pickerは未確認。起動スクリプトはpayloadのhashで配置を分離し、古いAppX dependencyの使い回しを避けます。[結果と残作業](docs/windows-hark-followup.md)。

**名前を忘れても、内容や特徴を覚えていれば見つかる。** 本・同人誌・画像・動画・音楽・制作素材を、曖昧な日本語から探せるWindows向けローカルメディアライブラリを目指しています。

「あれ、どこだっけ？」→「東方 巫女」→ PC内の「博麗霊夢の立ち絵」が見つかる。正式名を思い出すための外部検索と、手元のファイル検索の往復を短縮することが原点です。**この例の検索精度は今後の検証目標**です。

長期目的の正本は[プロダクトビジョン](docs/product-vision.md)。モデルや手法は交換可能で、目的のファイルへ到達できたか、手間が減ったかを判断基準にします。

## 開発を引き継ぐAIへ

入口はルートの **[AGENTS.md](AGENTS.md)**。指定された参照文書まで読み、[開始・再開ガイド](docs/agent-start.md)と両handoffの最新節を確認してください。

現在の作業先は `feat/winui3-production-mvp-20261011`、[Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5)。mainと比較用ブランチは過去段階の資産です。CIは必要なときだけ使います。

## 開発版の状態（2026-10-13）

製品GUIは**WinUI 3 + C#**、バックエンドはPython + SQLiteのloopback APIです。明示登録したフォルダの一覧・検索、リスト/グリッド、画像/CBZ/ZIPの先頭プレビュー、タグ/棚/お気に入り保存、交換可能profileでのoffline AI文章・画像・混合検索を実装しています。配布完成版ではありません。

CBZ/ZIPページ閲覧APIはPythonで検証済み。読書画面の接続候補も追加しましたが、**追加C#テスト・Windows Releaseビルドは確認済みで、読書画面の実GUI確認は未完了**です。[読書画面の確認手順](docs/archive-reader.md)を参照してください。

全文OCR、動画/音声の内容索引、画像フォルダの論理作品化、Komga、見開き・読書位置保存、配布installerなどは後続です。Layaは実験的なopt-inで既定無効。実装状況と証拠は[開発handoff](docs/codex-handoff.md)・[チャットhandoff](docs/chat-handoff.md)・PRの最新記録を優先してください。

## WinUI開発版の起動

Windowsの既存Python/.NET/WinApp環境で、repository rootから実行します。

```powershell
pwsh -NoProfile -File tools/start-winui.ps1
```

「フォルダ管理」からフォルダを明示登録・scanします。モデル/profileの準備は[WinUI MVP](docs/winui-mvp.md)・[モデルprofile](docs/model-profiles.md)を参照。依存やモデルの自動導入、私物の自動scanは行いません。

## 保存済みWeb操作試作

`web/`と`app/server.py`は、架空データを使う既存Web demoです。製品GUIの比較や過去の操作検証の資産として保持しています。

Python 3.12以降で `start-demo.cmd` または `python app/server.py --open` を実行すると、http://127.0.0.1:8765 が開きます。初回は5万件の架空データを生成します。Ctrl+Cで終了。ポート競合時は `--port 8766` を指定します。実ファイルのscanやAI推論はこのdemoでは行いません。

Tauri/WinUI比較用の試作・計測手順は[GUI比較キット](docs/gui-compare.md)を参照。製品GUIの採用はWinUI 3で決定済みです。

## 検証と文書

Python CPUテスト：`python -m unittest discover -s tests -v`。Web構文：`node --check web/app.js`。Web UI試験：既存Node版Playwright/Edgeで `node tools/run-ui-check.cjs`（一時DBを使用）。Windows/C#のgateは機能別の確認手順へ。実施していない検証を成功扱いしません。

| 文書 | 内容 |
| --- | --- |
| [AGENTS.md](AGENTS.md) / [開始ガイド](docs/agent-start.md) | AIの入口・作業先・読む順序 |
| [プロダクトビジョン](docs/product-vision.md) | 長期目的の正本 |
| [開発handoff](docs/codex-handoff.md) / [チャットhandoff](docs/chat-handoff.md) | 最新進捗・実測・未完了項目 |
| [仕様](docs/spec.md) | 方向と提案仕様 |
| [API](docs/api.md) / [モデルprofile](docs/model-profiles.md) | 実装契約とモデル交換 |
| [詳細UI](docs/editor-layout.md) / [読書画面](docs/archive-reader.md) | UIの実装・検証範囲 |

元メディア、購入作品、DB、モデル、個人設定、認証情報はGit管理しません。元ファイルは移動・削除・リネーム・変換せず、整理情報はDBで管理します。APIはloopback限定です。
