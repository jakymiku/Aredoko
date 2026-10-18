# Aredoko

> 最新（2026-10-18）：[停止時の一式バックアップ・新規先復旧](docs/backup-recovery.md)を実装/CPU確認（R03 CPU_DONE）。実利用DBの上書きは行わず、GUI導線/実機受入は残る。次は[完成計画R04](docs/completion-roadmap.md)の明示索引継続。以降の古いcheckpointは履歴。

> **現状と次の開発（2026-10-18）**：登録/整理・画像/本ページ/代表動画frame検索・各viewer・WD候補レビューは実装済み。[保存済み索引の全件検索](docs/full-library-search.md)を接続し、候補の1万件打切りを解消。索引の継続、動画起点類似、音声/音楽内容、GUIの復旧導線/配布/製品受入は残作業。[完成までの実行計画](docs/completion-roadmap.md)と[最新handoff](docs/codex-handoff.md)を参照。下の古いcheckpointは履歴であり、現行機能の未実装判定には使わない。

本を複数まとめて準備する場合は、右クリックの「複数の本をAI検索に追加…」から、表示中の検索結果の本をチェック→範囲を確認→追加。最大8冊・1冊16ページ・合計128ページで、中断した最後のジョブはAI設定から同じ範囲を再開できます。[操作と制限](docs/page-batch-indexing.md)。

> **本の内部ページのAI検索（2026-10-17）**：本の右クリック →「本のページをAI検索に追加…」で準備済み数/範囲を確認し、次の未準備範囲を1冊・最大16ページずつ追加。「画像の見た目（AI）」から本単位に探して一致ページを読めます。既存の表紙索引と英語タグの日本語検索を保持。[操作・実測・一括索引の残る制限](docs/page-image-search.md)。OCRは保留。

> **最新（2026-10-16 実利用フィードバック全22件完了・動画時刻付きAI索引・ページ本文検索WinUI接続）**：動画内容の時間付き代表フレームAI索引・作品単位の検索結果集約・該当時刻への自動シーク再生（F12: `ai_video_frames` / `video_match_ms` / `VideoPlayerView`）、ページ本文検索モードのWinUI接続と一致ページへの読書ジャンプ（`ModePageText` / `PageTextEvidence<id>`）、GIF/WebP/APNGアニメーション再生と54,802KB級APNGのbounded処理（F07/F08/F11）、解除済みフォルダのDB完全削除（F21）まで実装・Windows実機確認。**全Python 397件実行（394 PASS / 3 SKIP）・Core 361 PASS・x64 Release 0 warnings 0 errors**、実機 **`feedback-video-ai-20261016-02`（106 checks / keys 56 / PNG 24枚）**・**`page-text-search-20261016-01`（29 checks / PNG 5枚）**・**`feedback-animation-20261016-01`（16 checks / PNG 4枚）**・**`feedback-antigravity-20261016-13`（98 checks / PNG 19枚）** PASS。[22件の対応表](docs/user-feedback-20261016.md)・[最新handoff](docs/codex-handoff.md)。

> **履歴（2026-10-16 P2 未承認タグ候補の明示検索）**：確定タグ検索（`GET /api/items`）とは明確に分離した **未承認タグ候補の検索モード（`POST /api/library/tag-suggestions/search`・検索方法「未承認タグ候補」`ModeTagCandidates`・一覧行の由来/根拠/stale表示 `ProposalEvidence<id>`）** を実装・Windows実機検証。最新バッチの未承認（`pending`）候補のみを対象とし、既存の登録フォルダ選択（単一/複数和集合）・種類・お気に入り/未確認/棚フィルターを共有。Windows実機で**全Python 337 PASS / Core 305 PASS / x64 Release 0 warnings 0 errors / 実機 `tag-candidate-search-20261016-02` 24 checks PASS（PNG 4枚全目視）** を確認。[タグ候補と検索仕様](docs/tag-suggestions.md)・[WDアダプタ](docs/wd-tagger.md)・[最新handoff](docs/codex-handoff.md)。

> 最新：P0新固定baseline v7（24問・実GPU）を測定し、画像候補がないcover検索の無駄なquery推論を省略。改善累積1/2で一区切り、P1/フォルダハブ完了を維持して次はP2。[結果・限界](docs/search-phase-v7-results.md)・[直近の優先順位](docs/development-priorities.md)。

> **最新（2026-10-15 Windows続行）**：P1 **画像・表紙のアイテム起点類似検索（`POST /api/library/ai/similar`・右クリック「似た画像・素材を探す」・取消/復帰）のWindows実機検証**と、ユーザー合意の**登録フォルダ管理ハブ・複数フォルダ統一検索（通常/AI/類似）・初期棚の一括/単一編集（`FolderHubView` / `FolderEditorPanel`）**を実装・実機検証。Windows実機で**全Python 301 PASS / Core 280 PASS / x64 Release PASS**、`Check-Similarity.cmd`（`similarity-check-20261015-120824-dbfe63` **41 checks / PNG 10枚**＋`unindexed` **9 checks / PNG 2枚**＋`text-only` **9 checks / PNG 2枚**＋double-click回帰 **22 checks / keys 16 / PNG 8枚**）および登録フォルダハブ実機（`folder-hub-native-07` **37 checks / PNG 10枚**）をすべて完走・全32枚のPNGを目視確認。[類似検索](docs/item-similarity.md)・[登録フォルダ管理](docs/folder-library-management.md)・[最新handoff](docs/codex-handoff.md)。

> 最新（2026-10-15）：シークバー・時刻付きサムネイル・下部帯の左右端揃えを追加。Python279/Core213/Release・native88checks（全18PNG確認）PASS。[操作と制限](docs/video-seek-preview.md)。[最終目標と計画](docs/media-content-plan.md)。

> 2026-10-15：大容量動画の範囲取得再生を接続。Python276/Core208/Release・native73checks（全12PNG確認）PASS。[最新仕様・実測と限界](docs/video-streaming.md)。シークバー/hoverサムネイルも接続済み（下記最新記録を参照）。

> **最新：読書位置保存**：CBZ/ZIPを開き直すと読めたページと単ページ/見開き方向を復元。本の更新時は先頭へ、保存/取得失敗では旧位置を保持・手動retry。全Python271/Core188/Release PASS、Light/Dark実機55checks/34keys/10PNG全目視。[操作と検証](docs/reader-progress.md)。動画・検索根拠・double-clickの他AI更新も維持。


> **履歴（2026-10-14 Windows続行）**：語別検索根拠（`SearchEvidence`）のWinUI表示と、専用ウィンドウによる**Windowsネイティブ動画再生（`VideoPlayerView`：再生/一時停止/1秒移動/音量・消音/非対応・破損・503・409案内/auto-hide・F10・Esc）**を実装。Windows実機で**全Python 264 PASS / Core 168 PASS / x64 Release PASS**を確認し、**サムネイルdouble-click（`viewer-doubleclick-01` 22 checks PASS）**、**語別検索根拠＋引用符/バックスラッシュ/`[`タグ検索（`search-evidence-01` 30 checks PASS）**、**動画thumbnail（`video-native-01` 50 checks PASS）**、**動画再生（`video-player-01` 70 checks PASS / keys 30）**をすべて実機完走・全PNG目視確認。[実機検証](docs/viewer-reader-validation.md)・[動画](docs/video-thumbnails.md)・[検索根拠](docs/literal-search-v6.md)。

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

単体画像は詳細の「画像を大きく表示」またはサムネイルのダブルクリックから閲覧できます。← / →で現在の検索結果ページ内の画像だけを検索順に送り、拡大・スクロール・表示リセットも可能です。未保存編集は保持されます。[操作と制限](docs/image-viewer.md)。動画は先頭フレームのサムネイル表示と、詳細の「動画を再生」からの専用ウィンドウ再生（再生/一時停止・前後1秒移動・音量/消音・非対応/破損時の案内、範囲取得・2TiB上限（生成70MiBで検証））を[Windows実機（Light/Dark）で確認済み](docs/video-thumbnails.md)です。

動画の時間付き代表frame索引、画像フォルダの一冊管理、読書位置保存は後続開発で実装済みです。音声/音楽内容索引、任意Komga連携、製品配布は残作業で、専用OCRは保留しています。Layaは実験的なopt-inで既定無効。実装状況と証拠は[開発handoff](docs/codex-handoff.md)・[チャットhandoff](docs/chat-handoff.md)・PRの最新記録を優先してください。

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
