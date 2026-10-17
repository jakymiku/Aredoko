# AIエージェントの開始・再開ガイド

> **最新：combined/RRFの限定改善を採用、P0累積2/2で区切り（2026-10-17）**：スコア幅による重み付け1案のみ。事前固定24問の正解あり22問は16/22→20/22、root限定22条件は22/22維持、旧Top1正解の悪化0。既存直接視覚13問は7/13→13/13（WD4問を混ぜない）。明示text/cover・原本/索引・scope不変。[方式・条件・2件の残失敗](combined-fusion-evaluation.md)。旧1/2は履歴、追加の自動調整/OCR復帰なし。次はページ検索の性能内訳、既存chunk UI。

> **最新：長い本の明示分割APIと再開（2026-10-17）**：CPU plan→固定128ページ以内を16ページずつatomic公開→同じjob/page/revision/scope/profileを再起動後に明示再開。旧Python分割メソッドを再利用/強化し、HTTP認証/所有cancel/保存job置換競合を検証。[契約・限界](page-chunked-indexing.md)。**GUI接続は次の段階**、旧16ページ/複数本UIは保持。専用OCR保留、14素材の実評価・bit同一ランキング・P0 1/2・簡潔GUIを維持。

> **最新：代表的疑似同人誌・画像内文字認識（Visual-OCR）実機評価完了（2026-10-17）**：ユーザー提供の2つのZIP（`Aredoko_search_test_images_8.zip`＋`Aredoko_text_recognition_test_images_6.zip`、計14枚）を用い、実モデル（CUDA EmbeddingGemma 2 768D＋WD Tagger CPU `wd-swinv2-v3`）での実機評価を完了（`data/representative-eval/real-v1-20261017/`）。複数ZIP自動マージ（`--zip <path> ...`）を実装。視覚（`cover`）モードにおいて、専用OCRなしでの画像内日本語文字認識（`visual_text_ja`）はフキダシ・章扉・黒板・看板の全5問で**Top1 5/5（100%）・期待ページ完全一致5/5（100%）**、英語文字（`visual_text_en`）も**Top1 2/2（100%）**、情景（`visual_scene`）も**Top1 6/6（100%）**、未承認WDタグ日本語意味検索（`wd_tag_semantic`）は**Top1 3/4（75%）・Recall@3 4/4（100%）**を達成。視覚検索全体で**Top1 94.12%（16/17）・Recall@3 100%・MRR 0.9706**を記録（混合combinedモードはテキストRRF希釈によりTop1 58.82%となり、視覚クエリには視覚モードを使う方針と一致）。**画像内文字認識での検索漏れ（content-search misses）が0件**であったことから、**ユーザーの「専用OCR保留」方針の妥当性が決定的に実証された**。[仕様と詳細実測表](representative-asset-evaluation.md)を参照。OCR保留・P0累積1/2は継続。

> **最新：多数本のページ検索CPU測定・物理版確認/guard削減（2026-10-17）**：生成1024冊/65536ページ・768Dで17.560→13.551→10.801秒（変更前比38.49%短縮、256冊は3.938→1.446秒）、catalog guard/物理版確認の合計保持は6.334→6.158→3.345秒（1冊1回保持・最大0.01125秒を維持）。中間list省略・256冊ごとの位置SQL一括取得・`tag_source`時のZIP central directory一括読取/ZipInfo省略を追加し、raw score/根拠/通常順位/root限定512冊と即時の変更/除外検出は完全一致。実精度・全RAM・1TB・UI応答の保証ではない。[固定条件・実測・次課題](page-search-performance.md)と最新handoffを優先。前回取消1PNGの静止画確認は未完、OCR保留/P0 1/2/UI簡潔/機能維持。

> **最新：上限付き複数本のページ追加（2026-10-17）**：右クリックからチェック式選択→範囲確認→開始。最大8冊/16ページずつ/合計128、完了分保持、最後のジョブの同範囲再開をAI設定へ統合。通常のAI buildでは自動処理せず、scope/profile/版を勝手に変えない。[使い方・契約](page-batch-indexing.md)。最終Windows/全体検証は両handoffを優先。

> **最新：ページ準備状況・次範囲への再開（2026-10-17）**：CPUで同版/profileの準備済み数/範囲を確認し、最初の未処理範囲を選択、追加後は次範囲へ。狭幅で状態/結果/取消を固定。Python441 PASS/3 SKIP、Core424、Release0警告0エラー、coverage単独native46 checks/8 PNG確認。続くユーザー指摘のフォーム右端重なり/入力の文字切れも修正し、余白検証native76 checks/16 PNGと、パネル端修正native39 checks/8 PNGと、横並び16DIP余白の最終native43 checks/8 PNGを確認（詳細は最新handoff）。[契約・限界](page-image-search.md)と最新handoffを参照。次は総ページ/冊数上限付き明示複数本job。OCR保留、P0累積1/2。

> **最新：内部ページの直接画像AI検索（2026-10-17）**：本ごとの明示範囲追加/再利用/取消、作品集約、ページ・版・model根拠、WinUI一致ページジャンプを実装。[使い方・API・人工GPU比較・残課題](page-image-search.md)と最新handoffを参照。通常AI buildで全ページを自動処理しない。次はページcoverage/次範囲と上限付き複数本job。OCR保留・P0累積1/2・UI簡潔/機能削減なし。

> **最新・日英タグ（2026-10-17）**：英語のWDタグを保持し日本語の意味で探す方針。承認済みは従来のAI文章索引、未承認は専用の「タグ候補の意味（AI）」へ分離。既存の明示AI buildで準備し、承認/却下後は署名で旧索引を除外。[仕様・固定評価](tag-semantic-search.md)。OCR保留は継続、実行結果は両handoffを優先。


> **最優先の方針更新（2026-10-17、ユーザー決定）**：OCR専用処理は保留。EmbeddingGemma 2の画像/本文ページ直接索引でも検索漏れが多いと確認された場合に実装を検討する。次はWD実利用確認と本の内部ページembedding。古い「OCR adapterを次に接続」の指示より本方針を優先。既存本文API/検索・固定OCR評価は残す。[現在の優先順位](development-priorities.md)を参照。


> **最新（2026-10-17 Open Code更新の統合後）**：既存索引の画像/動画入力版移行、実profile別DBの完全削除、大量削除のSQL上限、古い本文の誤ページ移動を修正。Python412 PASS/3 SKIP・Core370・Release0警告/0error・native37 checks/PNG8枚全目視。日本語OCR固定評価8ページ/10問と採点器を追加、**実OCR接続/精度測定は未完**。[最新handoff](codex-handoff.md)と[OCR評価仕様](ocr-evaluation.md)を優先。

> **最新（2026-10-16 実利用feedback全22件完了・動画時刻付きAI索引＆ページ本文検索WinUI接続）**：動画内容の時間付き代表フレームAI索引・検索集約・一致時刻シーク再生（F12: `ai_video_frames` / `video_match_ms` / `VideoPlayerView`）と、ページ本文検索のWinUI接続・一致ページへの読書ジャンプ（`ModePageText` / `PageTextEvidence<id>`）を実装・Windows実機確認。これにより **[22件の実利用フィードバック対応表](user-feedback-20261016.md)の全22件（F01〜F22）の実装が完了**。全Python **397件実行（394 PASS / 3 SKIP）**、Core **361 PASS**、x64 Release **警告0/エラー0**、実機 `page-text-search-20261016-01` **29 checks PASS / PNG 5枚**・`feedback-video-ai-20261016-02` **106 checks PASS / keys 56 / PNG 24枚**。次はOCR評価/アダプタ接続と代表素材のタグ品質測定。[最新handoff](codex-handoff.md)を優先。

> **履歴（2026-10-16 F07/F08/F11 アニメ再生・54.8MB APNG・代表フレームAI索引・PageEvidenceClient）**：GIF/WebP/APNGアニメーション実フレーム再生と資源解放（F07）、アニメ代表フレームAI索引（F08）、54,802KB級大容量APNGのboundedデコード/転送（F11: 元64MiB/16MP/64frame・転送8MiB上限）、およびページ根拠・本文APIの反射不要Coreクライアント（`PageEvidenceClient`）を実装・Windows実機確認。全Python **396件実行（393 PASS / 3 SKIP）**、Core **359 PASS**、x64 Release **警告0/エラー0**、実機 `feedback-animation-20261016-01` **16 checks PASS / PNG 4枚全目視PASS**。22件のフィードバック対応表のうち未実装は **F12（動画内容の時間付きAI索引）** の1件のみ。[対応表](user-feedback-20261016.md)と[最新handoff](codex-handoff.md)を優先。

> **履歴（2026-10-16 実利用feedback続行・F21実装＆統合実機確認完了）**：前回未完だったフォルダ/読書/設定の統合実機バッチ（`feedback-antigravity-20261016-13` **98 checks PASS / PNG 19枚全目視**）と動画double-click/右クリック実機バッチ（`feedback-video-20261016-04` **102 checks PASS / keys 52 / PNG 22枚全目視**）を完走し、さらに **F21 解除済みフォルダのDB完全削除（`POST /api/library/roots/purge`・`library_root_seq`によるID非再利用・WinUI確認ダイアログ取消/実行）** を実装・検証。全Python **395件実行（392 PASS / 3 SKIP）**、Core **351 PASS**、x64 Release **警告0/エラー0**。残る未実装は **F07/F08/F11（アニメ再生・代表フレーム索引・54MB級APNG）** と **F12（動画内容の時間付きAI索引）**。[対応表](user-feedback-20261016.md)と[最新handoff](codex-handoff.md)を優先。

> **履歴（2026-10-16 実利用feedback）**：左下「設定」、閲覧履歴＋未確認検索条件、wheel/X入力、recursive指定、動画操作等を追加。Python390 PASS/3 SKIP・Core350・Release0warn/error、独立native動画92/検索63/画像入力・履歴16 PASS（PNG28枚全目視）。フォルダ統合nativeはharness待機でFAILED、修正済み未再実行。アニメ/大画像/動画内容索引/DB完全削除は未実装。[対応表](user-feedback-20261016.md)と最新handoffを優先。

> **最新GUI方針とWindows確認（2026-10-16）**：ユーザー指示により簡潔なUIを維持し、機能は削減しない。管理操作は「ツール」、検索説明とタグのモデル詳細は任意展開へ整理。警告/根拠/未保存/検索範囲は見えるまま。Core320・Release0警告/0error、生成素材のnative64＋検索モード63 checks PASS、PNG20枚全目視PASS。前回reader透け/旧token GUI rescan/restartの残gateも確認済み。[AGENTSの恒久ルール](../AGENTS.md)と[最新handoff](codex-handoff.md)を優先。次は本文APIのCore/WinUI接続。

> **Windows統合checkpoint（2026-10-16）**：remote `ad850aa`まで取り込み、Core320 PASS、最終x64 Release警告0/エラー0、全Python384件実行（381 PASS/3 platform SKIP）。フォルダ本のstat/fstat時刻差による誤変更検知を修正。生成フォルダ本の登録/読書/保存/restartは28 runtime checks PASSだが、最終UI修正後nativeはsettings-panel待機不足で停止。待機は修正済み・再実行待ち。**最終GUI完了とはしない**。[失敗・検証境界・次の3手](codex-handoff.md)を優先。本文APIバックエンドを作り直さず、実OCRと専用WinUIは未接続として進める。

> **最新P2/P3ページ根拠（2026-10-16、実機なしで続行）**：ページID・版ごとの索引/根拠画像、任意extractorの本文保存/取消/再利用、明示的な本文検索APIを追加。全Python **383 PASS / 87.094秒 / skip0**。**実OCR adapterとWinUI本文画面は未接続、製品の抽出は既定503**。通常/AI/候補検索と手動タグは維持。[仕様](page-evidence.md)・[最新handoff](codex-handoff.md)を参照。次は固定OCR評価素材/採点→許可されたadapter接続→native根拠表示。Windows/.NET検証なし、CI0・P0改善累積1/2を維持。

> **最新P3補強（2026-10-16、実機なし）**：画像フォルダ本の同番号ページ順を固定、読込前後のパス/handle/ページ一覧確認、プレビュー・タグ入力の画像候補10000件上限、フォルダ単位のスキャン集約を追加。全Python **353 PASS / skip0**。旧一冊モードrootは`folder-book-v2`用に一度再スキャン（作品ID・手動整理は保持）。Windows Release/XAML/nativeは今回未検証。次の実機確認と独立したbackend作業は[最新handoff](codex-handoff.md)・[folder-books.md](folder-books.md)を参照。CI0回、P0改善累積1/2を維持。

> **最新P2 未承認候補の明示検索（2026-10-16 続行）**：確定タグと分離した未承認タグ候補の検索API（`POST /api/library/tag-suggestions/search`）・Coreプロトコル・WinUI検索方法「未承認タグ候補」（`ModeTagCandidates` / `ProposalEvidence<id>`）を実装・Windows実機確認。全Python **337 PASS**、Core **305 PASS**、x64 Release **警告0/エラー0**、native `tag-candidate-search-20261016-02` **24 checks PASS・Light/Dark PNG 4枚全目視PASS**。次は代表素材でのタグ品質・日本語検索寄与の測定、およびOCR/複数ページ根拠への拡張。詳細は[最新handoff](codex-handoff.md)と[タグ候補仕様](tag-suggestions.md)。

> **最新P2レビュー（2026-10-16 狭幅修正済み）**：候補レビューUIの初回縦切り完了。通常/狭幅/live resize/狭幅open/修正承認をWindowsで59 checks PASS、Light/Dark PNG15枚全目視PASS。Release警告0/エラー0。生成素材と偽adapterによるUI確認であり実タグ精度ではない。詳細は[最新handoff](codex-handoff.md)。

> 最新P2 WD導入済み（2026-10-16）：ユーザー許可のもと合計6MB/s上限で導入、既存46package不変・追加6件だけ。実ONNX CPU/API **35 checks PASS・owned worker4/4終了**。精度評価/WinUI承認/OCRは未完了。[実測とライセンス](wd-tagger.md)・[最新handoff](codex-handoff.md)。取得許可を聞き直さず、次はWinUI承認と候補の明示検索へ。

> 最新P2 WD（2026-10-16）：画像分類のCPU adapter/profile/明示的な6MB/s上限導入スクリプトを追加。実導入/実CPU推論の有無は[最新handoff](codex-handoff.md)、[仕様と境界](wd-tagger.md)で確認。mock process/画像前処理のテストを実モデル品質と扱わない。WinUI承認/OCRは未接続。

> 最新P2（2026-10-16）：P2の最初の基盤として、由来付き候補の保存・承認/修正/却下・取消/再実行APIを追加。**実タグ生成adapter・WinUI承認画面・OCRは未接続**（既定生成503、契約検証は生成fixtureの偽adapter）。[実装境界とAPI](tag-suggestions.md)。P0 baseline済み・改善累積1/2は維持。

> 最新：P0新固定baseline v7（24問・実GPU）を測定し、画像候補がないcover検索の無駄なquery推論を省略。改善累積1/2で一区切り、P1/フォルダハブ完了を維持して次はP2。[結果・限界](search-phase-v7-results.md)・[直近の優先順位](development-priorities.md)。

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
