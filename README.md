# Aredoko

> **最新（2026-10-14 Windows続行）**：語別検索根拠（`SearchEvidence`）のCore解析とWinUI一覧表示を実装し、Windows実機で**全Python 263 PASS / Core 157 PASS / x64 Release PASS**を確認。未完了だった**サムネイルdouble-click（`viewer-doubleclick-01` 22 checks PASS）**、**語別検索根拠＋引用符/バックスラッシュ/`[`タグ検索（`search-evidence-01` 30 checks PASS）**、**動画thumbnailのLight/Dark・SAR 8:9比率・503再試行・遅延取消（`video-native-01` 50 checks PASS）**をすべて実機完走・全PNG目視確認。[実機検証](docs/viewer-reader-validation.md)・[動画](docs/video-thumbnails.md)・[検索根拠](docs/literal-search-v6.md)。

> **履歴（2026-10-14 夜）**：新しい固定検索評価v6を実行前に凍結し、余分な候補/正解なしの空回答も測定。通常検索APIに作品ごとの直接一致・関連語一致・欠落語を追加。順位・展開・fallbackは維持し、v6追加前後の72結果は同一。全Python **263 PASS / skip0**。根拠のWinUI表示とWindows検証は当時後続。[結果とAPI](docs/literal-search-v6.md)。

> **履歴（2026-10-14 続行）**：引用符・バックスラッシュ入りタグの検索見落としとJSON構文による誤ヒットを修正。AI検索の文字一致根拠も共通化。動画thumbnailはSARの表示比率を保持し、作品/登録rootの過大IDを事前拒否。全Python **256 PASS / skip0**。Windows/.NET/nativeは当時未検証。[検索](docs/related-terms.md)・[動画](docs/video-thumbnails.md)・[handoff](docs/codex-handoff.md)。

> **履歴（2026-10-14 Linux続行）**：既存ffmpeg/ffprobeによる動画の先頭フレームを追加。登録・索引済み動画のみ、10秒/共通2枠/256px/512KiB、memory cache限定。WinUIプレビューへ接続するソースを追加し、全Python **246 PASS / skip0**。Windows Release/native表示は当時未検証。[動作範囲と制限](docs/video-thumbnails.md)。プレビューAPIの数値ID超過・不正URLも400へ修正。

> **履歴（2026-10-14 共通ビューア）**：画像/CBZ/ZIPを専用WinUIウィンドウで閲覧。薄い左右・下枠、端に接する上下バー、idle hide/マウス再表示/F10、画像左右送り、読書single/右左・左右見開き。Core147・Python preview12/reader16・Release PASS、専用window画像/読書Light/Dark全PNGを個別目視。double-click入口はコード追加済み・実機未確認。[当時の検証](docs/viewer-reader-validation.md)。


> **履歴（2026-10-14 続き）**：フォルダGUI50checks、読書・関連語GUI105checks/キーボード14回を生成素材のLight/Darkで確認。右クリック設定・復元除外の残gateを通過、reader下部操作の切れと閉じた後の未保存詳細/focus復帰を修正。Python31/Core107/Release PASS。実JSON picker・高DPI/Contrast/Narrator等は残作業。[結果と残作業](docs/native-folder-reader-validation.md)。

> **履歴：Windows確認（2026-10-13）**：追加reader/辞書のWindows Release・Core97・Python211は通過。実GUIはLightの辞書・関連/部分一致までで、reader/Dark/JSON pickerは未確認。起動スクリプトはpayloadのhashで配置を分離し、古いAppX dependencyの使い回しを避けます。[結果と残作業](docs/windows-hark-followup.md)。

**名前を忘れても、内容や特徴を覚えていれば見つかる。** 本・同人誌・画像・動画・音楽・制作素材を、曖昧な日本語から探せるWindows向けローカルメディアライブラリを目指しています。

「あれ、どこだっけ？」→「東方 巫女」→ PC内の「博麗霊夢の立ち絵」が見つかる。正式名を思い出すための外部検索と、手元のファイル検索の往復を短縮することが原点です。**この例の検索精度は今後の検証目標**です。

長期目的の正本は[プロダクトビジョン](docs/product-vision.md)。モデルや手法は交換可能で、目的のファイルへ到達できたか、手間が減ったかを判断基準にします。

## 開発を引き継ぐAIへ

入口はルートの **[AGENTS.md](AGENTS.md)**。指定された参照文書まで読み、[開始・再開ガイド](docs/agent-start.md)と両handoffの最新節を確認してください。

現在の作業先は `feat/winui3-production-mvp-20261011`、[Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5)。mainと比較用ブランチは過去段階の資産です。CIは必要なときだけ使います。

## 開発版の状態（2026-10-14）

製品GUIは**WinUI 3 + C#**、バックエンドはPython + SQLiteのloopback APIです。明示登録したフォルダの一覧・検索、リスト/グリッド、画像/CBZ/ZIPの先頭プレビュー、タグ/棚/お気に入り保存、交換可能profileでのoffline AI文章・画像・混合検索を実装しています。配布完成版ではありません。

CBZ/ZIPの読書画面は、**生成本でLight/Darkのページ移動・破損/再試行・更新後の再open・キャンセル・未保存編集の保持をWindows実GUI確認済み**です。JSON picker、reader zoom等は引き続き未確認です。[読書画面の確認手順](docs/archive-reader.md)を参照してください。

単体画像は詳細の「画像を大きく表示」またはサムネイルのダブルクリックから閲覧できます。← / →で現在の検索結果ページ内の画像だけを検索順に送り、拡大・スクロール・表示リセットも可能です。未保存編集は保持されます。[操作と制限](docs/image-viewer.md)。動画thumbnailは[Windows実機（Light/Dark）で確認済み](docs/video-thumbnails.md)、動画再生は後続です。

全文OCR、動画/音声の内容索引、画像フォルダの論理作品化、Komga、読書位置保存、配布installerなどは後続です。読書の見開きはsession内で実装・確認済みです。Layaは実験的なopt-inで既定無効。実装状況と証拠は[開発handoff](docs/codex-handoff.md)・[チャットhandoff](docs/chat-handoff.md)・PRの最新記録を優先してください。

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
