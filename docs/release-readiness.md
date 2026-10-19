# R14 — bounded GPU/native recovery acceptance

2026-10-18: user explicitly permits GPU and GUI testing now. Start HEAD ec2f23a.
This run supersedes the temporary execution deferral, not the closed P0 2/2 quality trial.

Scope frozen before execution: generated five-item/two-root library and three CBZ pages,
existing offline CUDA EmbeddingGemma 2 weights, no new dependencies/downloads/WD rerun.
Exercise R02 full-pool response/counts, scoped/similar search, one-use request echo and
cancel before/during real inference; distinguish cancel receipt from worker exit.
Exercise R03 stopped backup/new-directory restore, exact published ranks/scores and
saved metadata/reader position/profile/settings; reuse vectors without document/image inference.
Launch the actual development launcher on only the restored generated database with
space-containing settings/profile paths. Verify Light/wide and Dark/narrow detail,
restored viewer setting, metadata edit/restart and native Core CUDA combined search.
Inspect all delivered PNGs. Use local owned PID/HWND because Sandbox feature is disabled.
No private roots, original media changes, user DB restore, Actions or main merge.

Tools: tools/test_recovery_acceptance.py --stage gpu|gui --output data/ai-ui/recovery-native-20261018-01
Artifacts stay ignored. Capture failures without overwriting them; at most two correction/retest
cycles for this new flow. Old book-batch cancellation screenshot gate remains historical
and its exhausted rerun allowance is not reset. Other R04-R13 implementation and whole
M1/M2 acceptance, large-library resource/p95, AOT, Narrator and cross-host recovery remain open.

Frozen scope above; completed results and open gates follow. This is not RC acceptance or a new retrieval-quality measurement.

## 実行結果（2026-10-18）

**限定GPU受入 PASS、native GUI受入 PARTIAL。R14全体/M1/M2は未完了。**
実行許可は最新のユーザー指示で得ており、以前の一時延期は現在の禁止ではない。
開始/アプリ対象HEAD `ec2f23a`。テストは未commitの専用harnessで実行し、native第3回には下記launcher修正を含む。
最終harnessの小窓詳細再表示と証跡上書き防止は実行後の修正で、構文確認のみ。実行済みと混同しない。

| 対象 | 結果・限界 |
| --- | --- |
| 実CUDA / R02 + R03 | **28/28 PASS、47.581秒**。2root/単体4画像＋CBZ1冊3ページ。text5/cover5/page3を実索引。all/cover/text各5候補・完了flag/ID echo、root scope2件、画像起点類似4件、未開始取消409/実query中取消後409（部分結果なし）と次の正常検索を確認 |
| 同ホスト復旧 | 停止後backup→新規先restore。manualタグ/棚・読書位置・profile/設定を保持、source再検証あり/自動再開なし。保存vector一致、3page fresh。再GPU検索3modeの**公開順位・丸め済みsemantic_score一致**、復元後document/image再推論0（queryのみ3）。全float64内部bit/他ホスト/停電受入とは違う |
| GPU資源 | worker観測peak CUDA allocation **931.8 MiB**（総VRAM/RSSやp95ではない）。取消受付6.309msは1回の補助測定で、encode強制中断/終了時間の保証ではない。初回/復元後すべての所有worker handle停止。生成原本bytes/mtime不変 |
| actual launcher / Light | 空白入り復元DB・profile directory・AI/viewer settingsを実起動。cold起動、専用profile有効、wheel-up設定、manual編集/保存、Core経由のcombined CUDA検索5件、live backup拒否を確認。Wide detail/設定/検索PNG3枚目視。backend/App正常終了 |
| actual launcher / Dark | cold起動、同profile、Lightで保存したfavorite保持、小窓libraryまで確認。resizeで詳細overlayが閉じ、harnessが存在しないBtnCloseDetailsをinvokeして停止。**22個の記録assertionはPASSだがflow全体FAIL**。Dark詳細/設定/combinedは未確認。5PNGすべて目視したが5枚全画面合格とはしない |
| Core / build | 今回Core **528 checks PASS**。x64 SelfContained Release **0警告/0エラー**（native最終回Light7.96秒/Dark7.88秒）。C#/XAML変更なし。WinUIAnalyzer追加取得・AOT/Narrator/High Contrastは未実施 |

### 起動失敗と修正・試行上限

1. native初回は子Windows PowerShellのexecution policyでスクリプト開始前に失敗（GUI0）。harnessだけにprocess単位の`-ExecutionPolicy Bypass`を指定し、永続policyは変更しない。
2. 再試行1はRelease成功後にlauncher失敗（GUI0）。`--args`へ引用符入りの1文字列を渡す経路を、インストール済みWinAppの正式な`--`＋個別引数配列へ変更。viewer設定の空白pathを失わず、失敗時に捕捉したCLI応答も表示する。
3. 再試行2は上記修正でLight全flow/両theme実起動が成功し、Darkの小窓詳細で停止。今回の**修正再試行2回は終了**、4回目は行っていない。テスト側がresize後にBtnDetailsで明示再表示する手順へ修正したが、未再実行として残す。製品側のSplitView動作を不具合と断定して変更していない。

`data/ai-ui/recovery-native-20261018-01/` にgpu-result.json/gpu.log、gui-result.json（初回）・gui-result-02/03.json、gui-01/02/03.log、native/およびnative-02/03のlauncher log、5PNG/tree、core.log、visual-review.json、final-artifact-hashes.jsonを保持。生reportを成功へ書き換えない。最初のharnessのcp932例外表示/cleanup重複エラーも生logに残す。最終scriptはUTF-8出力・元エラー保持・新規attempt path保護を追加済み。

### 残りと次作業

- **R02/R03はCPU_DONEを保持**。今回限定実機証拠を追加したが、R10の通常検索全体取消/設定復旧導線、R12の数万件/p95/RSS、R14全体をDONEにしない。
- Dark小窓詳細→設定→combinedの未確認と、古いbook-batch取消の静止PNG未完は別gate。古い試行上限もresetしない。
- 次の実装順は **R04明示索引継続→R05動画起点類似→R06音声方式設計**。同じ実機テストを根拠なく反復せず独立開発を進める。
- 実利用DB/私物の走査・復旧上書き/原本変更・新DL/依存・WD再実測・17問品質再調整・Actions/main mergeなし。ユーザー提供ZIPの再利用も今回は不要だった。P0累積2/2終了、専用OCR保留、全機能/簡潔GUIを保持。

## 実行結果（2026-10-20 R14一括受入・実機GPU/Native GUI全件合格）

ユーザーの明示許可（「裏でゲーム動いてるけど軽いゲームだから問題なくテストを行えるはずなので実行しておいてください」）に基づき、R14全項目（R04継続、R05動画類似、R07-R09音声音響、R10/R11状態明瞭化、R12規模予算、R02/R03復旧Native GUI）を一括実機検証。

### 1. 各ハーネス検証サマリー

| ハーネス / 項目 | 実行コマンド | 結果 | 主な検証内容・証拠 |
| --- | --- | --- | --- |
| **R04 索引継続 GPU/GUI** | `tools/test_continuation_acceptance.py --stage all` | **GPU 4/4 PASS / GUI 4/4 PASS** | 実CUDA EG2推論（6doc）、UIA自動操縦による計画→確認した未準備分作成→中断→再開ボタン出現の一連フロー。`continuation-plan.png`、`continuation-cancelled.png` 目視確認合格 |
| **R05 動画類似検索** | `tools/test_video_similarity_acceptance.py --stage all` | **19/19 PASS** | 動画起点/候補、フレーム最大集約、候補時刻（`video_match_ms`）・起点時刻（`origin_match_ms`）の時間根拠、自己除外、表紙フォールバック |
| **R06-R09 音声・音響** | `tools/test_audio_acceptance.py --stage cpu` | **36/36 PASS** | 768D発話区間索引（3500ms根拠・snippet取得・キャッシュvector直接再利用）、512D音響特徴索引（雨音・ジャズ記述子検索・無音WAV幻覚防止）、音響類似検索（時間根拠・自己除外）、HTTP範囲再生ストリーミング |
| **R10/R11 状態・UI監査** | `tools/test_ui_status_acceptance.py --stage cpu` | **16/16 PASS** | AI状態コード（`model_missing`, `unindexed`, `corrupt_profile`, `ready`）と0件検索の分離、要求所有取消、伏字診断情報（パス・トークン置換）、UI監査チェックリスト網羅 |
| **R12 規模・資源予算** | `tools/test_scale_acceptance.py --stage cpu` | **26/26 PASS** | 50,001件メタデータ＋65,536件768Dベクトル。通常検索warm p95=0.3605s <= 1.0s、CPUベクトル順位計算warm p95=9.110s <= 10.0s、取消応答0.100ms <= 1.0s、WAL checkpoint truncate 0B、停止時backup (4.99s) / 新規restore (2.05s) 整合性ok |
| **R02/R03 復旧・Native GUI** | `tools/test_recovery_acceptance.py --output data/ai-ui/recovery-native-20261019-02 --stage all` | **GPU 28/28 PASS / GUI 24/24 PASS** | 実開発launcherによる実機起動。Light (1200x820) および Dark (700x620 狭小) の両テーマ。前回未完だったDark狭小リサイズ時の詳細overlay再表示・設定確認・Core combined実CUDA検索を完全パス。全6画面PNG目視確認合格 |

### 2. 生成スクリーンショット目視確認結果

- `data/continuation-acceptance/gui/continuation-plan.png`: 計画作成後の「未準備の4件を作成」ボタン表示・有効状態確認。
- `data/continuation-acceptance/gui/continuation-cancelled.png`: 中断後の「前回の未準備分を再開」ボタン表示確認。
- `data/ai-ui/recovery-native-20261019-02/native-01/Light-restored-detail.png`: Lightテーマ・1200x820での詳細ペイン、タグ・棚・お気に入り状態確認。
- `data/ai-ui/recovery-native-20261019-02/native-01/Light-restored-viewer-settings.png`: Lightテーマでの設定ダイアログ・ビューア設定・復旧ガイド導線確認。
- `data/ai-ui/recovery-native-20261019-02/native-01/Light-restored-combined-search.png`: Lightテーマでの「両方で探す（AI）」実CUDA検索結果（5件）、スコア・タグ・根拠表示確認。
- `data/ai-ui/recovery-native-20261019-02/native-01/Dark-restored-detail.png`: Darkテーマ・700x620狭小での詳細オーバーレイペイン表示・レイアウト崩れなし確認。
- `data/ai-ui/recovery-native-20261019-02/native-01/Dark-restored-viewer-settings.png`: Darkテーマでの設定ダイアログ・高コントラスト視認性確認。
- `data/ai-ui/recovery-native-20261019-02/native-01/Dark-restored-combined-search.png`: Darkテーマ狭小での「両方で探す（AI）」実CUDA検索結果表示確認。

### 3. テストスイート整合性

- Core単体テスト: **691/691 PASS** (Release)
- Python単体テスト: **629/629 PASS** (3 platform SKIP)
- WinUI Release x64ビルド: **0エラー**
- 全プロセス（Aredoko.WinUI.exe、python worker）の完全終了を確認済み。
