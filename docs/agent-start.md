# AIエージェントの開始・再開ガイド

> **最新（2026-10-15 Windows続行）**：P1 画像・表紙の類似検索Windows一括検証（`Check-Similarity.cmd` → `similarity-check-20261015-120824-dbfe63` **41 checks / PNG 10枚**、`unindexed` **9 checks**、`text-only` **9 checks**、double-click回帰 **22 checks / keys 16**）を完了し、続いてユーザー合意の **[登録フォルダ管理ハブ・複数選択検索・一括初期棚編集](folder-library-management.md)** を実装・Windows実機検証（`folder-hub-native-07` **37 checks / PNG 10枚**、最終 **Python 301 PASS / Core 280 PASS / x64 Release PASS**）まで完了。P0の新固定baselineは未実施（改善試行累積0/2）。詳細は [両handoff最上段](codex-handoff.md) を参照。

> 2026-10-15 21:10 JST ユーザー合意（文書）：[登録フォルダをメインのリスト／グリッドへまとめ、複数選択検索と初期棚編集を行う仕様](folder-library-management.md)。

> 2026-10-15続行：類似検索の取消/復帰・破損vector・応答検査を補強。Python全300 PASS/skip0。帰宅後のWindows確認は [windows-similarity-handoff.md](windows-similarity-handoff.md) と `Check-Similarity.cmd` から開始する。Core/Release/nativeは今回の環境では未実行。

> 最新（2026-10-15・P1）：画像/表紙のアイテム起点類似検索API・WinUI context menu・復帰/取消のソースを追加。[仕様と検証境界](item-similarity.md)。Coreテスト・Windows Release/nativeは今回未実行。P0の新baselineは未実施、累積改善試行0。今回はユーザーの明示依頼でP1を実装し、P0を完了扱いにしていない。

> 最新（2026-10-15）：シークバー・時刻付きサムネイル・下部帯の左右端揃えを追加。Python279/Core213/Release・native88checks（全18PNG確認）PASS。[操作と制限](video-seek-preview.md)。動画/音声内容索引・アイテム起点類似検索は未実装。[最終目標と計画](media-content-plan.md)。

> 2026-10-15：大容量動画の範囲取得再生を接続。Python276/Core208/Release・native73checks（全12PNG確認）PASS。[最新仕様・実測と限界](video-streaming.md)。シークバー/hoverサムネイルも接続済み（下記最新記録を参照）。

入口はリポジトリ直下の **AGENTS.md**。ファイル名は複数形・大文字。Codex、Antigravity、ChatGPTなどが開発を始める際は、そこに指定された文書まで読む。

## 現在の作業先

- リポジトリ：jakymiku/Aredoko
- 製品の作業ブランチ：`feat/winui3-production-mvp-20261011`
- 既存Draft PR：[#5](https://github.com/jakymiku/Aredoko/pull/5)
- PR base：`feat/gui-framework-comparison-20261010`
- `main`と比較/試作PRは過去段階の資産。再開時にmainの説明だけで現在の実装を判断しない。
- `docs/product-vision-20261013`はビジョン文書を作成した履歴ブランチ。文書を製品作業ブランチへ選択的に取り込み済み。以後の開発では**作業先のdocs/product-vision.md**を正本として読む。別ブランチの古いコードやhandoffを現状として採用しない。

## 文書の役割と読む順序

| 文書 | 判断すること |
| --- | --- |
| AGENTS.md | 作業ルール、参照順序、許可の境界 |
| docs/product-vision.md | 長期目的・ユーザーの検索体験・開発原則の正本 |
| docs/folder-library-management.md | ユーザー合意の登録フォルダ一覧・複数root検索・初期棚編集の仕様と受け入れ条件 |
| docs/development-priorities.md | **次に実装する優先順位・評価指標・合格条件（2026-10-15更新）** |
| docs/codex-handoff.md / docs/chat-handoff.md の最新節 | 実装済み機能、実際の検証結果、未完了項目、次の作業 |
| 最新コード・テスト・Issue #4 / PR #5 | 現在の実装と変更範囲の確認 |
| docs/spec.md | 仕様の方向と提案。未実装を含むのでコード・最新handoffで照合 |
| README.md | 起動方法と入口。詳細な進捗はhandoffへ |
| モデル・検索・資源・reader等の設計文書 | 当該機能の実装時に参照 |

製品目的が古い文書と異なる場合はproduct-visionを優先する。実装状態は最新のコード・テスト・handoff/PRで確認する。ビジョンにある目標を、実装済み・精度確認済みと読み替えない。古いhandoffの次手や一時的な操作依頼を現在へ自動再適用しない。

## 開始時の確認

1. `git status`、現在branch・HEAD・差分・PRのhead/baseを確認。未保存変更を上書きしない。最新の作業先へ安全に同期できる場合だけ進める。
2. AGENTS→vision→**development-priorities**→両handoff最新節→Issue/PRを読む。過去の実装を再作成せず、最優先の未完了項目から次の小さな縦切りを選ぶ。検索品質を測定し、可能なら評価に根拠がある修正まで実装する。
3. ローカルで実行できるテストを使う。**CIは必要時だけ**。Windowsがない場合はRelease/native GUI未検証を明記し、Python成功をGUI合格にしない。
4. 作業終了時は変更・テスト・未検証・次の3手をhandoffへ記録し、同じDraft PRを更新する。mainへのマージはユーザー確認まで行わない。

## 今後の優先開発（2026-10-15）

最新のユーザー方針を [development-priorities.md](development-priorities.md) に記録。**検索精度の固定評価→既存画像embeddingの右クリック類似検索→OCR/候補タグ/複数ページ文脈のシチュエーション判定**を直近の軸とする。続いてフォルダ本の論理作品化、動画/音声の時間付き内容索引を進める。動画プレイヤーの細部やUI全面改修に偏らない。ただし障害/保全/重大な退行は優先する。

これは方向指定であって実装済みの宣言ではない。実装前に最新ソース・テスト・既存PR・両handoffと照合し、LinuxのみならGUIを実機確認済みにしない。新しいモデル/依存/私有素材の無断取得・操作は禁止。CIはAGENTSの必要時単発ポリシーを維持する。

## 今回の再開で把握すべき境界

- 最新：読書位置/向きを別SQLite tableへ保存・復元、revision更新時cover、取得/保存失敗時の保全・manual retry。全Python271/Core188/Release/reader-progress-native-02 55checks/34keys/10PNG全目視PASS。他AIの動画・根拠・double-click更新を維持。[reader-progress.md](reader-progress.md)と両handoff最新を正とする。

- 2026-10-14 Windows続行：語別`search_evidence`のCore解析・WinUI表示（`SearchEvidence<id>`）と、専用ウィンドウによるWindowsネイティブ動画再生（`GET /api/library/video/<id>`、64MiB上限、`VideoPlayerView`の再生/一時停止/1秒移動/音量・消音/非対応・破損・503・409案内/auto-hide・F10・Esc）を実装。Windows実機で全Python264・Core168・x64 Release PASSを確認し、ネイティブGUIでサムネイルdouble-click（`viewer-doubleclick-01` 22 checks PASS）、語別検索根拠＋引用符/バックスラッシュ/`[`検索（`search-evidence-01` 30 checks PASS）、動画サムネイル＋検索根拠（`video-native-01` 50 checks PASS）、動画再生（`video-player-01` 70 checks PASS / keys 30）をすべて完走確認。[実機検証](viewer-reader-validation.md)と[両handoff最上段](codex-handoff.md)を正とする。

- 2026-10-14 夜：v6固定評価とprecision/correct-emptyを追加し、通常検索APIにitem別search_evidence（direct/related/missing）を追加。全Python263 PASS、v6全72結果はAPI追加前後同一。

- 2026-10-14 続行：動画SARの比率、JSONタグ値の文字検索/AI根拠、過大IDのGET/POST/scanを修正。全Python256 PASS、Windows/.NET/nativeは未検証。動画20・文字検索10・AI候補4・ID境界4の回帰を追加/確認。[両handoffの最上段](codex-handoff.md)を正とする。

- 2026-10-14 Linux続行：動画先頭frameのbackendとWinUIプレビュー接続ソースを追加。全Python246 PASS、Windows/.NET/nativeは未検証。プレビューID/URL検証も修正。[動画thumbnail](video-thumbnails.md)・両handoffの最上段を正とし、以前のRelease/Core/GUI結果を今回へ流用しない。double-click実機・動画再生は残る。

- 2026-10-14 共通viewer：専用Window・薄枠/端に接する上下帯・auto-hide/画像左右/reader見開きを実装。Core147・preview12/reader16・Release PASS。最終window実機は[viewer-reader-validation.md](viewer-reader-validation.md)、double-clickは実機未検証。両handoff最新節を正とする。

- 2026-10-14 続き：folder50/reader105 GUI checks（reader実入力14）、Python31/Core107/Release PASS。Light/Darkの候補/dirtyとLightの棚/context/解除・復元、Light/DarkのCBZ/ZIP reader・関連語を生成素材で確認。実JSON picker・zoom/直接Reopen・高DPI/Contrast/Narrator等は残る。[実機結果](native-folder-reader-validation.md)と最新handoffを参照。候補の自動区切りはconfidenceではない。

- 曖昧な日本語から目的のローカルファイルへ到達することが製品の核。「東方 巫女」から保存済みの博麗霊夢の立ち絵を探すケースは**今後の評価目標**。
- EmbeddingGemma 2を含むモデルは交換可能。文字/確定タグ/関連知識/意味/画像特徴を役割ごとに補完する。フィルターやユーザーの手動整理を勝手に覆さない。
- 読書UI・関連語dialogはソース追加済み。Linux時点のPython205件・C# Core93件・C#のみのコンパイル検査PASSは履歴。後続WindowsではPython211/Core97/Releaseとwindowless error probeがPASS、nativeはLight辞書/検索理由までの部分確認で全体FAIL。当時のreader/Dark/pickerは未到達（[Windows確認の履歴](windows-hark-followup.md)）。今回のreader/関連語Light/Darkは上記で確認、実JSON pickerは未完了。以後の変更を自動保証しない。
- 文字検索は正規化＋複数語AND、ユーザー登録の関連語辞書で候補を追加できる（[related-terms.md](related-terms.md)）。辞書は同梱・自動取得しない。
- resize時の詳細pane自動保持、高DPI/Contrast/Narrator、フォルダ本/Komga等は別の未完了項目。詳細は最新handoff。
- 私物の無断scan/書換え、外部送信、モデル取得・依存導入・OS変更を勝手に行わない。

どのAIでも「この作業ブランチのAGENTS.mdと参照先を読み、最新handoffから続きを実装してください」と依頼できる構成にする。各ツールがAGENTSを自動発見すること自体は保証しない。
