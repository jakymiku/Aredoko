# Aredoko GPT Chat向け引き継ぎ

## 2026-10-17 英語タグを保持した日本語意味検索・未承認候補用索引/API/WinUI

実装commit：`0026b51337539edf60f59de5adcd93e3d93b6e1d`。開始HEAD `ca942766aa2876c87c763322cafb69fe08cea2e8`（clean、既存Draft PR5/production branchを継続）。現在P2。P0 baseline済み/改善試行累積**1/2**を維持。ユーザーが「WDの英語タグをEmbeddingGemma 2で日本語から検索する」方向を承認したため実装。**英語原文を保持・日本語への逐次手動翻訳は不要、OCRは保留のまま。** 既存の本文ページ直接索引の後続目標は維持する。

### 実装・使い方

- 承認済み英語タグは既存の通常AI文章索引で検索可能。今回、**未承認候補を分離した意味検索**を追加。検索方法の7番目「タグ候補の意味（AI）」（`ModeTagSemantic`、index6）。従来の未承認候補の文字一致（index4）、ページ本文（index5）や他検索は保持。確定タグ・却下済み候補・翻訳結果を混ぜない。
- **候補生成→設定「AI検索の準備」で対象範囲のAI索引作成→日本語で検索**。未承認は新モード、英語のまま承認したタグは再索引後「名前・タグの意味（AI）」を使う。自動翻訳/自動承認/生成直後の自動GPU索引化はしない。
- 既存profile別DBの`ai_proposal_vectors`に、最新pending集合の文書vectorを通常text/coverと分離保存。`pending-raw-tags:v1`、batch/source/producer、候補ID/原文/version、物理metadataによるsignature。同一入力は再利用。承認/却下/新batch/元ファイル再scan後の古いvectorを検索から除外。sourceが変わった古い候補しかなければ不足のまま残し、候補再生成を要する。
- 既存の**明示scoped AI build**だけで準備し、coverageへ未準備を反映。共有inference lock、推論中はcatalog lockを保持せず、公開直前の状態/版/scope照合、取消/競合では候補vector未公開、既存per-item再開。root purgeで正規profile別DBとcatalog本体の新テーブルも削除。他root/手動整理/原本を保持。
- APIは既存`POST /api/library/tag-suggestions/search`の任意bool`semantic:true`。省略/falseは旧文字検索。意味応答は`search_mode:'pending-proposals-semantic'`、cosine、pending/indexed/remaining件数、rawタグ/由来/根拠/検索モデル。新たな閾値/順位重みは導入せず、正解なしでも近い候補が返りうる。類似度は正解率ではない。
- GUIは索引不足の警告と根拠/類似度を表示し、通常AIの重複根拠は出さない。既存の検索root選択と保存AI scopeの意味は変えず、範囲・版・未承認を隠さない。詳しい契約とscope差は[tag-semantic-search.md](tag-semantic-search.md)。本の本文ページ/音声内容の索引を実装したとは扱わない。

### 固定評価・対象/全体検証

- 日本語質問18問（正解あり16/正解なし2）と英語タグ16集合を推論前に固定。`tag-language-v1.json` SHA `dc3d32e09b86c6b291807ae350c9bc8b7fade1e7dfcccf9562e29fda6a89ff17`。raw英語/underscoreを空白にした条件を事前固定し、既存offline EG2/CUDAで一度比較。両方**Hit@1/Recall@5/MRR=1.000、Precision@5=0.2125**。前処理変更は採用せず原文のまま。「初音ミク」「東方の巫女」もこの小さなfixture内でTop1。正解なしは候補を返す（raw top0.598310/0.630628）ため拒否成功と数えない。**人工metadataであり、WD画像分類/実ライブラリの品質ではない**。`data/tag-language/v1-20261017-01/report.json`、worker終了確認。
- `.gitattributes`で新fixtureのLFを固定。作業treeとGit blobのSHA一致を確認し、Windows再checkoutでも固定hashが変わらないようにした。既存評価入力/モデル/重みを変更していない。
- 新規`test_tag_semantics.py` **10 PASS**：未索引時推論なし、明示索引/再利用、原文/手動metadata保持、承認/却下/新batch/破損vectorの無効化、取消/レビュー競合、profile差替え、元ファイル変更、範囲/棚/favorite/model、複数profileのroot完全削除、HTTP厳密bool/空query/旧検索維持。
- **全Python425件実行：422 PASS / 3 Windows platform SKIP、194.569秒**（`data/tag-language-python-20261017.log`）。**Core378 PASS**（意味検索のscore/モデル/不足数/改変応答検査8件追加）、**Windows x64 SelfContained Release警告0/エラー0、11.76秒**（`data/tag-language-core-20261017.log` / `data/tag-language-release-20261017.log`）。Python compileall/diff --check PASS。
- **native `tag-language-20261017-02`：33 checks PASS / Light・Darkの7 PNG全目視 / app正常終了2 / 所有embedding worker終了**。既存EG2 CUDAと生成PNG・事前指定の英語候補（偽tagger）を使用。索引不足0結果→明示索引→日本語からblue_hair/twintails Top1、登録root絞り込み、旧英語文字一致、英語のまま承認→索引更新→通常AI日本語検索、app再起動保存、元bytes/mtime/設定不変を確認。**実WD画像分類をこのbatchで測ったとはしない**。前回の実WD CPU GUI48件は別の履歴として維持。
- 初回native `tag-language-20261017-01`は**FAILED**：既存保存AI scopeで1件が正しい通常AI結果をテストが2件と期待し、終了処理も`RecordedSimilarity.proceed`を通常`AISearch`へ要求して例外になった。製品scopeを変えずテスト期待と所有AI終了処理を修正、1回だけ再実行して上記02で合格。初回PNG4枚も全目視しログ/FAILED resultを保持。旧runを成功扱いにしない。一部shotのown-app tooltip/capture chromeは成果物の読み取りを妨げない。
- WinUI設計/コードレビュー：新API仮定なし、既存ComboBox/Theme/AutomationId、反射不要のJSON検証、非同期/古い応答排除/履歴mode復帰/根拠の重複抑制/既存scopeを点検。**未導入WinUIAnalyzerは未実行、High Contrast/Narrator/新規キーボード網羅/大規模pending性能/Native AOTは未検証**。新DL/依存追加・私物scan・外部送信・CI dispatchなし、テストapp/backend終了。

### 次の3手

1. **本文ページ画像の直接embedding索引API→対象テスト**：既存PageIndex・安全な入力取得とprofile/source revision/page IDを再利用。明示scope/ページ上限、同版再利用、取消/再開、変更/部分失敗を設計して最小実装。cover索引/手動整理/今回のタグ意味検索を保持。未実装の本文AI索引をOCRの検索失敗と誤認しない。
2. **ページ一致の作品集約とWinUI読書**：一致ページを検索結果から開く。版違いのジャンプ抑止、生成した日本語ページで検索到達率・時間/容量を測る。OCRはGemma直接索引でも検索漏れが多い場合だけ検討する。
3. **明示選択の代表素材でタグ品質/日英検索を測る**：人工的に分離した16集合の100%を実素材へ一般化しない。Danbooru略語/キャラクター/複合条件の失敗を記録し、必要分だけ関連語辞書を検討。数千pendingのsnapshot/coverage性能、タグ集合全体の意味一致と個別タグ根拠の違いも測る。音声/音楽内容索引・複数ページ文脈タグは後続。

---

## 2026-10-17 WD実モデルのGUI確認・OCR保留のユーザー方針を反映

検証ツール実装commit：`ad426ff652054200fdfd50cde70c60d2da2bbd32`。開始HEAD/検証に使った製品sourceは`d9fc4a6eed1a9c95020c61cbbd4bf30b94fc8825`。ブランチは`feat/winui3-production-mvp-20261011`、既存Draft PR5を継続。**現在フェーズP2、P0 baseline済み/改善試行累積1/2は不変。** 今回は製品GUI/検索rankingを変更せず、既存の実WD導線を検証し次の順序をユーザーと確認した。

### ユーザーが確定した優先順位

「OCR専用の処理はEmbedding gemma2でも内容が引っかからないケースが多く見られた場合に実装を検討」。**OCR adapterの接続/取得/常駐化を次の既定作業にしない。** 先にEmbeddingGemma 2で画像/本の本文ページを直接索引化して到達範囲を広げる。現在の本/ZIP/CBZの通常AI画像索引は主に表紙なので、本文未索引とモデルの検索失敗を区別する。直接画像検索はembeddingであり文字起こしを返す機能ではない。既存本文API/検索と固定OCR評価素材は将来の選択肢として保持し、機能削除しない。

この方針をAGENTS/vision/agent-start/development-priorities/media-content-plan/page-evidence/ocr-evaluationへ反映。**本節と新方針が、下の過去記録の「次はOCR接続」に優先する。**

### WD Taggerの実装状態と今回の検証

- 固定WD SwinV2 v3/ONNX CPUは導入済みで`available:true`。通常backendから使える。詳細「AIタグ候補」→「候補を生成」で画像/本の先頭ページを明示分類し、修正承認/却下/由来/履歴を扱える。確定タグへの自動投入・全登録画像への自動一括タグ付け・自動日本語訳はない。
- `tools/test_tag_review_ui.py --wd-runtime-only`を追加。既存の許可済みモデルだけを使い、生成素材の専用DB・所有app/workerだけを起動・終了する。他のテストモードは引き続き推論なし。通常起動のmodel/profile/ranking/GUIは変更していない。
- **実行 `python tools/test_tag_review_ui.py --wd-runtime-only --output data/ai-ui/wd-native-cpu-20261017-01`：48 checks PASS、初回バッチで完了/修正再試行0、Light/Dark PNG8枚全目視、Aredoko正常終了2、WD worker2/2終了・pipe close。** Windows Sandboxが無効の既存環境のため、許可済みのローカル専用テストウィンドウを使用。
- PNG1枚とCBZ1冊で実CPU候補生成（6件/5件）→モデル版/根拠表示→同一batch再利用（新workerなし）→**日本語へ修正承認→「名前・タグ」で一致**→raw英語pending候補は**「未承認タグ候補」だけで検索**、を実際に操作した。元英語ラベルと修正した承認タグを別保存、既存手動タグ/棚/お気に入りを保持。
- 元生成素材bytes/mtime・model SHA/mtime・AI設定を保持、EmbeddingGemmaの推論/ロード0。新DL/私物scan/外部送信/CI dispatchなし。画像を勝手に登録/タグ確定する挙動は追加していない。
- **これは実接続・GUI操作の確認でありタグ精度評価ではない。** 図形にも`solo`/`1girl`等が出るため、生成成功や分類スコアを正解率にしない。代表イラスト/写真/人物/日本語の検索寄与は未評価。狭幅の編集はスクロール経由、検索shot2枚にはアプリのshortcut tooltip/capture chromeが含まれるが結果は読み取れる。High Contrast/Narrator/大規模性能は今回未検証。

### その他の検証・保留物

- `test_wd_tagger.py` **9 PASS / 6.619秒**、`test_tag_suggestions.py` **21 PASS / 6.682秒**、Python compileallとgit diff --check PASS。全Python/Core/Releaseを今回は再実行せず、変更なし製品の既存Releaseを利用した。直前の全体検証（Python412 PASS/3 SKIP、Core370、Release0警告/0エラー）は前回revisionの記録として維持。WinUI/XAML変更なし、WinUIAnalyzer未実行。
- 作業途中、既存Windows日本語OCRを使うbytes-only workerの小試作を作り、生成済みpage-01の抽出と模擬worker契約9件を確認した。ユーザー方針を受け、**通常serverへの接続は戻し、新規source/testはignoredの`data/ocr-prototype-20261017`へ退避**。新依存/モデル/OS設定変更なし。製品OCR実装/精度測定の完了とはしない。必要性を再確認する前にこの試作を黙って復帰させない。
- `docs/wd-tagger.md`の古い「WinUI未実装」を修正し、実際の使い方と英語候補→日本語修正承認の境界を追記。全体から機能を減らさずUIへ検証説明を追加していない。

### 次の3手

1. **本文ページ画像の直接embedding索引API→対象テスト**：既存PageIndexの安全な取得とページID/source revisionを再利用。明示scope・ページ数上限・profile DBの分離・取消/再開・同版再利用・変更/部分失敗の扱いを実装する。cover-onlyの索引/類似検索/手動整理を保持。まだ製品にこの機能があると報告しない。
2. **作品への集約と一致ページからの読書**：ページごとの根拠を作品単位の検索結果へ集約しWinUIから開く。版違いでは誤ページへ飛ばさず、既存page-text jump policyを参考にする。新規固定の生成素材で検索到達率と処理時間/容量を測る。P0のranking/閾値を根拠なく調整しない。
3. **代表素材のWD品質とGemma検索漏れの記録**：私物はユーザーの明示選択だけで測る。OCRは索引済み内容でも検索漏れが多く確認された場合に検討。音声/音楽内容索引・複数ページ文脈タグは引き続き未実装。

---

## 2026-10-17 Open Code更新の確認・旧索引移行/完全削除/本文ジャンプ補強・OCR評価基盤

修正実装commit：`69d3a52ceb07c27c8721d0000b76dcbedbdfd775`。OCR評価/文書は本節を導入した後続commitを参照。

開始HEAD `8e90a026c96d01b5564e44902b73cec3293df369`、clean・remote差0/0。`a79f0ee`以降のOpen Code6コミット（`bd456f6`/`1f16441`/`0b65d23`/`556f9fe`/`943e45c`/`8e90a02`）を取り込み済みとして、AGENTS/vision/優先順位/両handoff/Issue4/PR5と実装を照合した。フォルダDB purge、アニメ/大APNG、動画時間付き索引、本文検索WinUIを再実装せず維持。以前の全22件完了記録は機能縦切りの到達点で、今回の更新互換性/実DB保存先の欠陥まで保証するものではない。

### 実装・修正

- **旧AI索引を新しい入力処理へ更新**：従来は文章vectorの同revisionだけでfreshと判定し、既存動画が時間付きframe索引へ、既存アニメが代表frame索引へ移行しなかった。各profile DBへ`ai_source_contracts`（`representative-image:v1` / `timecoded-video:v1`）を追加。coverage/buildは入力版も検査し、同じ文章vectorを再利用して画像/動画を一度だけ更新。モデルkey/namespace/rankingは変更しない。[移行手順](model-profiles.md)：**ユーザーが選択した範囲・既存上限内でAI索引作成を明示実行した分だけ更新**し、自動私物推論はしない。
- 動画解析の取消時に部分frameを公開せず旧vectorを保持。前処理失敗でも利用可能な旧索引を消さず、remainingとして再試行可能にする。文章専用profile/音声metadata/既存本の索引はこの入力版の変更で再推論しない。
- **F21の実保存先を修正**：実際のAI索引はcatalog本体とは別の`catalog.ai[.<profile-hash>].sqlite`だったが、以前のpurgeは本体内の`ai_vectors`しか対象にしていなかった。厳密なファイル名＋内部profile keyを照合した通常ファイルだけで、各profileのvectors/video frames/source contractsを削除。他root/無関係DB/原本を保持。catalog内のvideo frames/source contractsも削除。大量item IDをPython配列→SQL変数へ展開せず、temp table/subqueryでSQLite変数上限を回避。
- **複数DBの失敗境界**：派生AIをprofile単位transactionで先に削除し、最後にcatalog内の手動記録をcommit。途中失敗では登録/タグ等を保持して再試行できる日本語エラー。全DBの一括atomic保証はしない。先に削除済みの派生AIは必要なら再作成。[API境界](api.md)も更新。
- **本文の誤ページジャンプ防止**：`PageTextMatch.InitialReaderPage`で`current`かつ根拠revisionとreader manifestが一致するときだけ番号を適用。検索後に本が変わった場合/古い根拠は通常の読書復帰へ。古い本文はstale表示のまま保持。根拠page数/負数/欠損をCoreで検証。
- **OCR評価の固定素材・採点ツール**：[ocr-evaluation.md](ocr-evaluation.md)、`tests/fixtures/ocr-eval-v1.json`、`create_ocr_fixture.py` / `ocr_quality.py` / `evaluate_ocr.py`を追加。日本語8ページ/7作品・10問（正解7/負例3）、縦横/表記揺れ/薄い文字/空白、raw/normalized CER、検索到達率、正解なし誤検出を分けて採点。backendの同一ページAND/作品集約と一致集合を照合。**実OCR未接続・実認識精度未測定**。採点controlを実モデルの成績にしない。fixture SHA `3e731b6bf17d1710b680a4c1b5b85c0c9e7997c5c6c63fc5551c23ee7f1814bd`。

### 今回の検証

- 新規`test_media_upgrade.py`10 PASS：修正前に旧索引スキップ/別DB残留/SQL変数超過を再現後、移行一回・文章再利用・取消/失敗再開・profile間分離・実sidecar/main動画削除・他root保全・途中失敗rollback/retry・不明DB保全を確認。
- 新規`test_ocr_quality.py`8 PASS：perfect/empty control、欠損と空文字の区別、正規化、空白への幻の出力、固定hash/境界、実`PageTextIndex.search`との10問照合。既存AI関連75 PASS、feedback13 PASS、error translation3 PASSも確認。
- **最終全Python415件実行：412 PASS / 3 Windows platform SKIP、188.270秒** (`data/resume-python-20261017.log`)。**Core370 PASS** (`data/resume-core-20261017.log`)、**最終x64 SelfContained Release警告0/エラー0** (`data/resume-release-20261017.log`)。
- **native `page-jump-revision-20261017-01`：37 checks PASS / Light・Dark PNG8枚全目視 / 所有アプリ正常終了2**。本の本文一致2/3へ読書→生成CBZへ先頭page追加＋rescan→queryし直す前の旧current表示でも1/4へ通常復帰→再検索後stale根拠でも1/4、を実際に確認。改版のため変更したのは専用の生成CBZのみ。ベース生成素材bytes/mtime、AI設定不変、推論0、テストapp/backend終了。過去の全GUI batchを今回再実行したとはしない。
- OCR生成8 PNGも全目視、既存Meiryo/Pillowだけを使用。`data/ocr-eval/ocr-v1-20261017`のreceiptへfont/image SHA保存。perfect-controlはCER0/Recall@5=1、empty-controlはCER1/Recall@5=0：**採点器の検算であり実OCR成績ではない**。
- WinUI code reviewで版照合/読書位置保持/取消/既存Theme・AutomationId導線を点検。新しいXAML/常駐説明は追加せず、未導入WinUIAnalyzerは未実行。実GPU/WD/OCR品質やHigh Contrast/新規大規模私物検証ではない。新依存/モデル取得・私物scan・CI dispatchなし、P0試行累積1/2を維持。

### 次の3手

1. 固定OCR素材を使い、許可範囲内のローカルOCR adapterを選んで`PageTextIndex`へ接続。新モデル/依存取得は別途明示許可が必要。取消/timeout/画素数/worker終了とproducerを実装し、実抽出ログ＋CER/到達率を測る。既定抽出503を架空テキストで代替しない。
2. ユーザー明示選択の代表素材でWDタグ品質・日本語検索寄与を測定。複数ページの本文/視覚根拠からの候補契約を設計し、手動確定タグを保持する。合成PNGのruntime成功と実タグ精度を混同しない。
3. 入力版の更新操作を生成素材の大きめscopeで測り、既存対象上限/中断再開/失敗remainingを確認。将来のアニメframe総メモリ/読込遅延や音声/音楽内容索引も残課題として継続。動画は最大4frameの代表抽出であり全場面の網羅/精度保証ではない。F09外部OS起動/F22OS drag注入の過去の未自動実行境界も維持。

---

## 2026-10-16 実利用フィードバック全22件完了＆ページ本文検索WinUI接続（実装 `943e45cbe35992580de7d1cd450b206ab72d5990`、parent `556f9fe`）

開始HEAD `556f9fecb956e1dabcc0927e2461bcd29fd17177`（clean・remote差0/0）。[22件の対応表](user-feedback-20261016.md)の最後の未実装項目だった **F12（P4: 動画内容の時間付き代表フレームAI索引・作品単位の検索結果集約・該当時刻への自動シーク再生）** と、**P2/P3 ページ本文検索（`ModePageText` / `PageTextEvidence<id>`）のWinUI接続および該当ページへの読書画面ジャンプ**を実装し、単体テスト・Windowsネイティブ実機検証まで完了した。これにより **実利用フィードバック全22件（F01〜F22）のコード実装がすべて完了**した。

### 1. 実装内容

- **F12（P4）動画内容の時間付き代表フレームAI索引・検索集約・該当時刻シーク (`app/video_previews.py`, `app/previews.py`, `app/ai_search.py`, `src/Aredoko.Core/Protocol.cs`, `src/Aredoko.WinUI/VideoPlayerView.cs`, `MainPage.xaml.cs`)**：
  - `VideoThumbnailer.representative_frames` と `VectorStore` の `ai_video_frames(item_id, revision, at_ms, vector)` テーブルを追加し、動画から最大4つの時刻付き代表フレームを抽出・ベクトル索引化。
  - 「画像の見た目（AI）」「両方で探す（AI）」検索で各動画の最高スコアフレーム時刻を作品単位に集約し、`video_match_ms` / `動画フレーム一致（0:01）` を表示。動画を開くと `VideoPlayerView` が一致時刻へ自動シークして表示。
- **P2/P3 ページ本文検索のWinUI接続と該当ページへの読書ジャンプ (`src/Aredoko.Core/SearchMethod.cs`, `LibraryApi.cs`, `src/Aredoko.WinUI/MainPage.xaml`, `MainPage.xaml.cs`, `ArchiveReaderView.cs`)**：
  - `SearchMethod.FromIndex(5)`（`ModePageText`「ページ本文」）と一覧行の `PageTextEvidence<id>` を追加し、結果から「本を開く」で一致した先頭根拠ページを直接開くよう接続。

### 2. 検証結果（Windows実機、CI起動0回）

- **全Pythonテスト**：**397件実行 / 394 PASS / 3 Windows platform SKIP（232.045秒）**（`test_library_feedback.py` **13 PASS**）。
- **C# Coreテスト**：**361 PASS**、**Windows x64 SelfContained Release PASS（警告0・エラー0）**。
- **ネイティブGUI実機検証① (`data/ai-ui/page-text-search-20261016-01`)**：**29 checks PASS / PNG 5枚全目視PASS**（`ModePageText` と `PageTextEvidence` の表示を確認）。
- **ネイティブGUI実機検証② (`data/ai-ui/feedback-video-ai-20261016-02`)**：**106 checks PASS / keys 56 / skipped 0 / PNG 24枚全目視PASS**（`動画フレーム一致（0:01）` 表示と動画起動時の `0:01 / 0:02` 自動シークを確認）。

### 3. 残課題と次の3手

- **[22件の実利用フィードバック対応表](user-feedback-20261016.md)は全22件（F01〜F22）実装・検証完了**。
- **次の3手**：
  1. **OCR評価データ/採点ツールと許可されたローカルOCRアダプタの接続**。
  2. **代表素材のタグ品質測定と複数ページ根拠のシチュエーションタグ推定**。
  3. **登録フォルダ管理の後続・音声/音楽内容索引の検討**。

---

## 履歴：2026-10-16 実利用フィードバック続行②：F07/F08/F11 アニメーション画像再生・54,802KB級APNG bounded処理・代表フレームAI索引・PageEvidenceClient（実装 `0b65d23df9bf07cc8544237af91301d43fe13000`、parent `1f16441`）

開始HEAD `1f16441346930b9d1aeed8ddcdb78ee24cd9e652`（clean・remote差0/0）。[22件の対応表](user-feedback-20261016.md)の残課題だった **F07（GIF/WebP/APNGアニメーション実フレーム再生・資源解放）**、**F08（アニメ画像の代表フレームAI索引）**、**F11（54,802KB級APNGのboundedデコード/転送・取消）**、および優先課題の **`PageEvidenceClient`（ページ根拠・本文APIの反射不要Coreクライアント）** を実装し、単体テストとWindowsネイティブ実機検証まで完了した。

### 1. 実装内容

- **F07 / F11 アニメーション画像（GIF / WebP / APNG）と 54,802KB級大容量APNGのbounded処理 (`app/image_animations.py`, `app/library_index.py`, `app/previews.py`, `app/production_server.py`, `src/Aredoko.Core/ImageViewerPolicy.cs`, `ArchiveReaderClient.cs`, `src/Aredoko.WinUI/ImageViewerView.cs`)**：
  - `.apng` 拡張子を `TYPES['image']`・`IMAGE_MIME`・`ImageViewerPolicy`・`TagReviewProtocol` に追加（`.png` 拡張子のAPNGも `acTL` チャンク検査で自動判別）。
  - 一律8MiB制限を無制限に撤去するのではなく、既に同一性・リンク不在を検査したファイルハンドルに対し、**元ファイル最大64MiB・最大16,000,000画素（16MP）・最大64フレーム・長辺最大2048px・1フレーム転送最大8MiB** の厳格な境界を持つ `AnimationInspector` を実装。
  - `GET /api/library/preview/<id>/manifest` と `GET /api/library/preview/<id>/frames/<frame>?revision=<64hex>` を追加。8MiB超〜64MiB以下の大容量画像に対する `GET /api/library/preview/<id>` も8MiB以下の正規化PNGを返すため、一覧/詳細サムネイルも安全に表示可能。
  - `ImageViewerView` でアニメーション画像の全フレームとフレーム別遅延時間・ループ回数に従って再生し、移動・再読込・終了時（`Dispose`）に `StopAnimation()` でタイマーとフレーム配列を確実に解放。
- **F08 アニメ画像の代表フレームAI索引 (`app/image_animations.py`, `app/previews.py`, `app/ai_search.py`)**：
  - アニメーション画像のAI視覚索引（`PreviewReader.read_cover`）およびAIタグ候補入力（`PreviewReader.tag_input`）では、決定論的な代表フレーム `min(frame_count - 1, frame_count // 2)` を最大768pxの正規化PNGとして抽出し、既存のモデル空間を壊さずに索引化・類似検索・タグ候補生成へ接続。
- **ページ根拠・本文APIの反射不要Coreクライアント (`src/Aredoko.Core/PageEvidenceClient.cs`, `Protocol.cs`, `LibraryApi.cs`)**：
  - `PageEvidenceProtocol` / `PageEvidenceClient` と `MediaRow.PageText`（`PageTextMatch`）を反射不要で実装。

### 2. 検証結果（Windows実機、CI起動0回）

- **全Pythonテスト**：**396件実行 / 393 PASS / 3 Windows platform SKIP（183.035秒）**（`test_library_feedback.py` **12 PASS**、`test_previews.py` **14 PASS**、`test_error_text_coverage.py` **3 PASS**）。
- **C# Coreテスト**：**359 PASS**、**Windows x64 SelfContained Release PASS（警告0・エラー0）**。
- **アニメーション＆54,802KB APNG ネイティブGUI実機検証 (`data/ai-ui/feedback-animation-20261016-01`, `--animation-only`)**：**16 checks PASS / keys 4 / skipped 0 / PNG 4枚全目視PASS**。

### 3. 残課題と次の3手

- **[22件の対応表](user-feedback-20261016.md)のうち未実装は F12（動画内容の時間付き代表フレームAI索引）の1件のみ**。
- **次の3手**：
  1. **本文検索（`page-text`）とページ根拠確認のWinUI接続**。
  2. **F12（P4）動画内容の時間付き代表フレームAI索引の最小縦切り**。
  3. **OCR評価データ/採点ツールと代表素材のタグ品質測定**。

---

## 履歴：2026-10-16 実利用フィードバック続行：統合実機検証の完走・動画入口/右クリック確認・F21 解除済みフォルダのDB完全削除（実装 `bd456f6825af834209ba4e12ac643d840e1082d8`、parent `a79f0ee`）

開始HEAD `a79f0ee`（clean・remote差0/0）。[22件の対応表](user-feedback-20261016.md)に基づき、前回未完了だったフォルダ／設定／読書の統合実機テストと動画double-click・共通右クリックメニューの実機検証を完走し、あわせて未実装だった **F21（解除済みフォルダのDB完全削除）** をバックエンド・Core・WinUI・単体/実機テストまで一気通貫で実装・検証した。

### 1. 実装と修正

- **F21 解除済みフォルダのDB完全削除（`app/library_index.py`, `app/production.py`, `app/production_server.py`, `src/Aredoko.Core/ErrorText.cs`, `src/Aredoko.WinUI/MainPage.FileActions.cs`, `MainPage.xaml.cs`）**：
  - `library_root_seq` テーブルによる単調増加root ID管理を導入し、root削除後に新規登録や再登録を行っても**削除済みroot IDが絶対に再利用されない**（古い保存済みscopeが別の新規フォルダを誤って指さない）契約を保証。
  - `ProductionCatalog.purge_inactive_root(root_id, consent=True)` および `POST /api/library/roots/purge` を追加。登録中（`enabled=1`）のrootや `consent!=True`、スキャン中/AI処理中は拒否し、解除済み（`enabled=0`）のrootについてのみ、単一SQLiteトランザクション内で `page_text_heads` / `page_texts` / `page_heads` / `page_entries` / `page_snapshots` / `tag_proposals` / `tag_proposal_batches` / `ai_vectors` / `reader_progress` / `view_history` / `item_locations` / `items` / `library_locations` / `scan_jobs` / `library_roots` を完全削除。PC上の元ファイルは一切変更・削除しない。
  - WinUIの登録フォルダ一覧で「登録解除済み」フォルダ行および右クリックメニューに **「記録を完全削除」 (`PurgeFolder<id>` / `PurgeRoot<id>`)** を追加。確認ダイアログ（元ファイルは残ること・元に戻せないことを明記、既定ボタンはキャンセル）を経て実行。また `FolderStateFilter_Changed` で `RefreshSearchRootsAsync()` を呼ぶようにし、一覧状態切替時に最新の解除済みroot状態を取得するよう改善。
- **実機テストハーネスの待機・スクロール補正（`tools/test_tag_review_ui.py`, `tools/test_image_viewer_ui.py`）**：
  - `--check-ui-cleanup` の `ExpandSearchOptions` 折りたたみで `--action collapse` と `TxtSearchMethodHint --gone` を待機し、直後の `BtnRoots` クリックが検索条件変更の非同期ロード（`CloseFolderHubCore`）で潰されないように修正。
  - 読書ビューア（`ArchiveReaderView`）でのホイール・マウスX1/X2ページ送り検証前に `F10` でオーバーレイ表示を固定し、2.5秒のauto-hideによる `ReaderPageNumber` 非表示化を防止。
  - 旧v1トークンGUI再スキャン後に開いている詳細ペインとフォルダ追加パネルを閉じてから `FolderItem<id>` を `scroll-into-view` し、解除済みrootの検索に `include_inactive=True` を指定。

### 2. 検証結果（Windows実機、CI起動0回）

- **全Pythonテスト**：`395件実行 / 392 PASS / 3 Windows platform SKIP（185.899秒）`（`test_library_feedback.py` **11 PASS**、`test_error_text_coverage.py` **3 PASS** を含む）。F21の全依存テーブル削除・他root保全・root ID非再利用・古いscope拒否・元ファイル不変・HTTP認証/400/404契約を検証。
- **C# Coreテスト**：**351 PASS**（`dotnet run --project tests/Aredoko.Core.Tests -c Release --no-restore`）。
- **Windows x64 SelfContained Releaseビルド**：**PASS（警告0・エラー0）**。
- **統合実機テスト①（フォルダ・読書・UI整理・ユーザーフィードバック・F21 DB完全削除）**：
  - `python tools/test_tag_review_ui.py --output data/ai-ui/feedback-antigravity-20261016-13 --folder-books-only --check-ui-cleanup --check-user-feedback`
  - **98 checks PASS / PNG 19枚全目視PASS / graceful closes 2 / keyboard_tested True**（先にF21追加前の `-09` でも **94 checks PASS / PNG 18枚全目視PASS** を確認した上で、F21確認ダイアログのキャンセル保持＋実行削除を加えた `-13` を完走）。
- **統合実機テスト②（動画再生・double-click入口・共通右クリックメニュー）**：
  - `python tools/test_image_viewer_ui.py --video-seek-only --output data/ai-ui/feedback-video-20261016-04`
  - **102 checks PASS / keys 52 / skipped 0 / PNG 22枚全目視PASS**（F15 動画サムネイルdouble-click起動・draft保持、F19 動画右クリックの共通メニュー表示と画像類似非表示を確認）。

### 3. 未実装・未検証の境界と次の3手

- **未実装（4件）**：**F07 / F08 / F11**（GIF/WebP/APNGアニメ表示、アニメ代表フレームAI索引、54MB級APNGのbounded処理）、**F12**（動画内容の時間付き代表フレームAI索引）。
- **自動テストの安全境界により実機未実行の操作**：**F09**（外部 `explorer.exe`/既定アプリの実起動）、**F22**（OSからの実フォルダDrag & Dropイベント注入）。
- **次の3手**：
  1. **F07 / F11 アニメーション画像（GIF/WebP/APNG）と大容量APNG（約54MB級）のbounded表示・プレビュー**。
  2. **F08 アニメ画像の代表フレームAI索引**。
  3. **P2/P3 本文検索のCore/WinUI接続またはF12 動画内容の時間付き代表フレーム索引**。

---

## 履歴：2026-10-16 実利用フィードバック：操作改善・履歴・登録範囲（実装 `45d699562b912e82c6eb8efa41dbc77c579105b8`、parent `2b3e724`）

ユーザー確定：マウス進む/戻るはviewer内の画像/ページ送り。左ナビの未確認は閲覧履歴へ置換し、未確認filterは検索条件へ保持。[22件の対応表](user-feedback-20261016.md)を正とする。**全22件の完了ではない。**

### 実装

- 画像/reader共通のwheel送り（既定下=次、設定で反転）とmouse X1/X2。zoom中はscroll、修飾キー/操作部上は従来操作を優先。設定は小さなversioned JSONへatomic保存、壊れた設定は既定値。`--viewer-settings`で生成テスト専用pathを指定し、私物設定は触らない。
- 左下「設定」にviewer方向設定・AI検索の準備・関連語編集を集約。検索方法は「名前・タグ」「両方で探す（AI）」「画像の見た目（AI）」「名前・タグの意味（AI）」。豆の例、名前/タグの言い換え、本文/映像未解析を必要時に説明。全機能保持。
- `view_history`と認証付き`POST /api/library/history`、`GET /api/items?view=history`。画像/本/動画の表示成功通知で記録、最近開いた順/重複集約、restart保持、無効root/現在の除外を尊重。履歴内は通常の名前・タグ検索、種類/登録rootを利用（AI/候補modeをsilent fallbackせず無効）。外部アプリを開いただけの音声等の履歴は今回対象外。
- 登録`recursive` bool追加。旧root/省略時は従来通り再帰、直下のみscanと再登録の設定保持。再登録でfalseへ狭めると既存の下位locationを即時excluded。戻す場合はrescanで同じID/手動metadataへ復帰。フォルダ本`./`は直下作品として維持。
- 登録の重複同意checkboxを削除、明示登録ボタン/HTTP consentは保持。folder行single=settings/double=scope内を開く、共通Explorer/default-app menu、properties expander、one-click再登録（設定/metadata保持・自動scanなし）、1folder drop→登録候補を追加。これら一部のnative受け入れ確認は下記のとおり未完。
- 動画double-click入口、canvas click play/pause、右volume slider（既存mute/±と同期）、seek preview cache最大8枚。次frame中も前frameを保ち実表示時刻を示す。late応答排除/取消/既存上限は保持。

### 検証と境界

- 全Python `python -m unittest discover -s tests`: **393実行/390 PASS/3 Windows platform SKIP、207.387秒** (`data/feedback-python-20261016.log`)。新規履歴/recursive/HTTP9件を含む。表示文変更後のAI profile10件もPASS。新しいモデル/依存取得なし。
- Core **350 checks PASS** (`data/feedback-core-20261016.log`)、最終x64 self-contained Release **0警告/0error**。WinUI code review実施、未導入WinUIAnalyzerは実行せず、AOT/High Contrast実機/全私物libraryの品質は未検証。
- 独立した生成素材native：動画 **92 checks/18 PNG** (`data/ai-ui/feedback-video-20261016-initial`)、検索mode **63 checks/6 PNG** (`feedback-methods-20261016`)、画像実wheel/X1/X2＋実閲覧履歴 **16 checks/4 PNG** (`feedback-input-20261016`) PASS。**28 PNG全て目視済み**。画像は700x620、履歴は1200x820（当初narrowだった履歴ファイル名をwideへ訂正、pixels不変）。検索/動画はLight/Dark・通常/狭幅。モデルはcontract fixture、実推論/品質評価を意味しない。
- フォルダ/設定の統合nativeは**FAILEDのまま**。初回は未確認check後の自動collapseで次のcheckbox操作が失敗（製品修正：この操作では条件panelを開いたまま＋未確認title）。cycle1はUIA既定invoke=expandをtoggleと誤解した旧canvas期待、cycle2は閉じたchildをIsOffscreen=Trueで待ちtimeout。最終的に`--action collapse`＋`--gone`へharnessを修正したが**再実行していない**。スキルの最大2 fix/rerunに従い停止。設定保存（Light、隔離path）、履歴入口、未確認75/76件切替までは実機確認済み。失敗/部分成功を全PASSへ変更しない。6 PNG（各回2枚）も全目視。
- readerの新wheel/Xボタン/反転設定適用、folder single/double/直接再登録、GUI recursive登録、Explorer/default menu実起動、properties表示、動画のdouble-click入口/共通context、dropのnative受け入れは**未検証**。backend/Core/Release/コードレビューは成功してもnative成功とは呼ばない。既存のreader/登録/タグreviewの過去実機結果は過去revisionの証拠。
- 原本bytes/mtime・AI settingsを維持。テスト所有アプリを正常終了、user appをkill/attachせず、私物scanなし、CI dispatchなし、P0改善累積1/2を維持。全workflowはmanual_dispatchのみ。

### 次の3手

1. 修正済み`test_tag_review_ui.py --folder-books-only --check-ui-cleanup --check-user-feedback`を**次の作業回で**生成素材から実行し、上記未検証のreader/folder/反転/再登録gateを埋める。UIAで消えたchildは`--gone`。shell実起動やdropは所有テスト先だけで個別確認し、動画double-click/contextも加える。既存の92/63/16成功を失敗隠しに使わない。
2. F07/F08/F11：生成GIF/WebP/APNG＋約54MB入力で、frame数/decoded pixels/転送上限・取消/資源解放を持つanimation読込と代表frame AI入力を実装・検証。8MiB capの単純撤去や静止画1枚表示を完了にしない。新依存/モデルが必要なら既存の明示許可範囲を確認。
3. F21：解除済みroot限定のDB完全削除を確認UI・関連history/progress/AI/tag/page依存cleanup・ID非再利用（古い保存scopeが別rootを指さない）とともに実装。元ファイルは不変。**F12の動画内容索引は引き続き未実装**で`media-content-plan.md`の時間付きframe/embedding/集約が後続。名前/タグ検索や再生と混同しない。

---

## 最新：機能を維持してGUIの情報量を整理・前回のWindows残gateを確認（2026-10-16 JST）

開始HEAD `7ddfb627deb5dfedce149bf9f4d8618df8357c91`、clean・remote差0。AGENTS/vision/優先順位/両handoff/Issue4/PR5と最新コードを確認。**ユーザー指示「UIを複雑にしない。ただし機能削減はしない」**をAGENTSと[WinUI方針](design-vision-winui.md)へ恒久ルールとして追加。テスト都合の長文・内部用語は通常画面へ常駐させず、AutomationId・ログ・文書で検証する。既存feature / base / Draft PR #5を維持。実装commitは本節を導入したgit logを参照。

### 変更と機能保持

- MainPageの **「ツール」→「AI検索の準備」「関連語を編集」** へ管理操作を集約。モデル選択・対象scope・索引作成/中断・メモリ解放/資源設定・関連語の編集/import/exportは既存画面のまま到達可能。再接続・一覧/グリッド・詳細・登録フォルダ・検索モードは保持。
- 検索の常駐メッセージを短くし、AI候補数は上位/参考を表示。全文の検索説明は **「説明」** Flyoutへ、検索方法のヒントは既存の検索条件Expanderへ。警告・検索範囲の不一致・エラー・未保存・候補/stale状態は隠さない。根拠とスコアの正解率でない説明は任意に読める。検索API/ランキング/P0試行を変更していない。
- AIタグ候補の根拠画像・モデル名・対象/変更状態・説明・修正/承認/却下を前に出し、モデル版/adapter版/前処理は **「モデルと生成条件」** へ折りたたむ。履歴・生成・中断も保持。技術情報の削除やAPI撤去は行わない。
- nativeテストを新導線へ更新。`tools/native_ui_tools.py` は所有app PIDのメニューから既存AutomationIdを探すだけの共通helper。短命PopupHostがlist→inspect間で閉じた既知の例だけ再照会し、操作失敗を握りつぶさない。既存profile/関連語テストの移動操作も更新（本turnでその大型全scenarioを再実行したとはしない）。

### 今回の検証

- 最終 **Windows x64 SelfContained Release：警告0・エラー0**。**Core 320 PASS**。UI/XAML・nativeテストhelper・文書だけの変更で、本番Python/API/依存は変更なし。前回Windows Python381 PASS/3 SKIPを今回再実行したとは報告しない。
- **`ui-cleanup-20261016-02`：64 runtime checks PASS / PNG14枚全目視PASS / 所有app正常終了2**。Light/Dark、通常/狭幅、ツールからAI準備・関連語へ到達、検索説明の任意表示、検索方法ヒント、モデル詳細の展開、フォルダ本の登録→scan→自然順読書→手動整理保存→プロセスrestartで2/3復元まで確認。
- **前回の残gateを解消**：reader下端の画像透けが消えたことをLight/Dark狭幅PNGで確認。旧v1tokenを生成DBだけに設定→旧reader409相当→GUI再scan→同一ID/タグ/棚/お気に入り保持→再読書までPASS。元画像bytes/mtime・保存AI設定不変、model推論0。実WD/OCR品質の証拠とはしない。
- **`ui-cleanup-search-modes-20261016-01`：63 runtime checks PASS / PNG6枚全目視PASS**。既存CPU contract encoderのみ、AI文章/画像・表紙/混合の経路、種類/お気に入り/登録scope、未保存変更での取消/破棄、AIエラー後の通常検索復帰、vector/settings不変を確認。実GPU・実検索品質は未測定。
- 初回cleanup01は閉じたPopupHostの古いHWNDをテストが参照して停止。PNG2枚全目視、アプリの画面崩れではなかった。テストの参照待ちだけ修正して02を完走。失敗結果を上書きせず保存。今回のnative修正再実行1回、検索モードbatchは独立した既存回帰。
- WinUI code review：既存標準control/テーマbrush/AutomationId・共有遷移ガード・async取消・dirty保存・検索scopeを維持。新binding/依存・同期blockを追加していない。WinUIAnalyzer未導入、High Contrast/DPI拡大/Narratorと実ライブラリは未検証。CI dispatch0・3workflow manual-only・DL/OS変更/私物scan0・P0改善累積1/2。

### 次の異なる3手

1. **ページ根拠/本文APIのCore client**：版・page ID・source状態・応答上限を検証する反射不要clientとテストを追加。既存backendを作り直さず、保存済み本文はモデル不在でも使う。
2. **本文検索/根拠pageのWinUI縦切り**：既存検索方法・詳細/readerへの導線へ統合し、専用説明パネルや設定を乱立させない。明示scope/取消/古い応答/根拠版と未保存編集を保持する。実OCR未接続の状態を隠さない。
3. **OCR・代表タグの品質評価準備**：固定日本語素材/正解本文/query/期待page、CER・作品/page到達率の採点から進め、許可されたbounded OCR adapterを接続。新取得は別許可。複数ページ文脈推定/動画音声索引と、GUIの残る重複表記整理は機能を保った小さい単位で継続。

---

## 履歴：別開発のバックエンドを取り込み・Windows統合確認とフォルダ本の誤変更検知を修正（2026-10-16 JST）

開始local HEAD `f3fa79384f5affb3d812e1393177f65568624876`、clean。remoteが5commit先行していたため、既存featureへ `--ff-only` で **`ad850aa1fe6118725a53be1e15187c2471f6f9d2`** まで取り込んだ。AGENTS/vision/優先順位/両handoff/Issue4/PR5と実コードを照合。**候補検索・フォルダ本・ページID/根拠・本文保存/明示検索バックエンドは実装済み**として維持し、重複実装しなかった。同じDraft PR #5 / baseを継続。実装commitは本節を導入した `git log` を参照。

### 修正と検証

- **フォルダ本のWindows誤検知を修正**：パス `stat` と開いたhandle `fstat` の `ctime_ns` が約1ms異なる生成fixtureを観測し、未変更ページを `ReaderChanged` とする失敗を2回再現。ファイルidentity/device/size/mtimeの相互照合は維持し、ctimeはパス前後・handle前後の同じ取得方法で照合する。固定回帰テストは旧実装で失敗→修正後PASS。読込中のページ一覧変更・除外・旧token再scan・保存情報の保全も維持。
- **Windows全Python：384件実行 / 381 PASS・3 SKIP / 215.252秒**。3 SKIPはWindowsでのsymlink権限/開いたファイル置換の既存platform条件。新ページ索引/本文の契約も含む。ログ `data/folder-windows-full-tests.log`。対象folder本は16件中13 PASS・3 SKIP。**Core 320 PASS**、最終 **Windows x64 SelfContained Release 警告0・エラー0**。
- **native `tools/test_tag_review_ui.py --folder-books-only` を追加**。生成PNGのみ・一時DB・偽tagger・既存アプリ/portがあれば拒否・所有PID/HWND限定。`folder-books-windows-20261016-02` は **28 runtime checks PASS / 正常終了2 / PNG7枚全目視**：GUI opt-in登録→scan→3画像が1冊、p1/p2/p10自然順、読書左右キー、タグ/棚/お気に入り保存、Light→Darkのプロセス再起動で読書2/3復元、タグレビュー入口、元画像bytes/mtime・AI設定不変、推論0を確認。これは実OCR/WD品質や全P3完了ではない。
- **visual FAILを保持**：02の狭幅readerで下端1pxから画像が透けたため、reader overlayの半透明strokeを0へ変更した。「本を開く（CBZ / ZIP）」も「本を開く」にし、登録の一冊化説明をTextBlockで折り返す。最終03の通常幅/800px登録PNGで説明の可読性は確認。
- **最終nativeは未完了**：初回01はfolder-hub遷移待ち不足。02はruntime PASSだが前述visual FAIL。最終03は登録DB反映後、非同期settings panelの `ScanRoot` 出現前にscrollを実行して停止（runtime FAIL）。その後 `wait-for ScanRoot` を追加し構文確認だけ行った。03のPNG3枚（失敗画面含む）も全目視。**最終reader透け修正の実機再確認・旧tokenのGUI再scan・最終全経路は未検証**（旧tokenのWindows PythonテストはPASS）。結果JSONにruntimeとvisualを別記。WinUI UI testing skillの「Maximum two fix-and-rerun cycles」に達したため、この作業内で追加実機rerunはしていない。
- コードレビュー：同一性/変更検知/リンク拒否を維持、XAMLは既存controlsのみ、a11y名とAutomationId保持、native所有プロセス正常終了を確認。WinUIAnalyzer未導入・High Contrast/DPI拡大・実ライブラリ・実モデルGUI推論は未検証。新規DL・OS変更・私物scan/変更なし。P0改善累積1/2、3workflow manual-only、CI dispatch0を維持。

### 次の異なる3手

1. **Windows実機の残gate**：新しい作業として修正済みwaitを使い `--folder-books-only` を一括確認。最終reader上下端の透け、旧token GUI rescan、Light/Dark restartの結果と全PNGを見て記録。以前の28 runtime PASSを最終GUI PASSへ流用しない。
2. **本文APIのCore/WinUI接続**：ページID・revision・source状態を検証する反射不要clientと、本文検索/根拠page確認の小さな画面を接続。保存済み本文はモデル不在でも使い、既定503と抽出可能を区別する。既存表紙だけのタグ推定を本文解析済みとしない。
3. **実OCR・品質評価**：固定日本語素材/正解本文/query/期待pageとCER・作品/page到達率の採点を準備し、許可されたbounded OCR adapterへ接続。新モデル/依存取得は別許可。代表タグ品質評価・複数ページ文脈推定・動画/音声内容索引はbacklogを保持。

---

## 履歴：ページ根拠索引・本文保存/明示検索まで実装（2026-10-16、実機なし）

開始HEAD `4d7792f0d6285f86672d3af9006e5f85995b8349`、同じfeature / Draft PR #5を継続。正確な実装・検証・次の3手は[Codex引き継ぎ最上段](codex-handoff.md)、契約は[page-evidence.md](page-evidence.md)。

- 画像/ZIP/CBZ/folder本のopaque page ID、版別索引と変更検査付き根拠画像API。ページ追加で番号がずれても同じlocatorのIDを保持し、古い版で新しい画像を表示しない。
- 任意extractorによる本文の版/producer別保存・再利用・取消・全体rollback、同一ページ内ANDの明示本文検索。作品単位に集約し最大20作品/3根拠、current/stale/unavailable/unverifiedを区別。除外/解除/空scopeの境界と手動整理を保全。
- **実OCR adapter・専用WinUI画面・複数ページタグ推定は未接続**。製品の生成は既定503、保存済み本文はモデル不在でも一覧/検索可能。通常/AI/候補検索を維持。
- 全Python **383 PASS / 87.094秒 / skip0**（新規ページ/本文30件）。実OCR精度の検証ではない。C#はエラー辞書のみ、.NET SDK/WindowsなしでCore/Release/native未検証。CI0・model/依存取得0・私物scan0・P0累積1/2を維持。
- 次は固定OCR素材/正解/採点→許可されたOCR adapter→Core/WinUI根拠接続。Windows担当のP3実機確認と代表素材の品質評価も残る。旧folder-book-v2用の一度の再scan条件は前節どおり。

---

## 履歴：実機なしで画像フォルダ本の不具合修正・省メモリ化（2026-10-16）

開始HEAD `c1bfbb96fc8c3209e27a2257bfc6ef8a1074069a`、既存branch/ Draft PR #5を継続。実装・正確な検証結果・次の3手は[Codex引き継ぎの最上段](codex-handoff.md)を正とする。

- 同番号ページ名の順序固定、読込前後のfolder/path/handle/ページ一覧の再確認、preview・tag入力も10000候補上限。
- directory単位のスキャンへ変更し、全rootのページ情報を保持しない。合成12000ファイル/100冊の単回比較でPython追跡peak 1,999,628→884,051bytes（約56%減）。RSS/Windows性能ではない。
- **旧一冊モードrootは一度再スキャン**（`folder-book-v2`）。作品ID・タグ・棚・お気に入りを保持、古い表紙vector/候補/読書位置を誤再利用しない。
- folder回帰 **15 PASS**、全Python **353 PASS / 82.108秒 / skip0**、diff check PASS。**C#/XAML変更なし・.NET SDKなし、Windows Release/native GUIは未検証**。CI0回、model/依存取得0、私物scan0、P0改善累積1/2を維持。
- 次はWindows担当のfolder本実機確認、独立してLinux側のpage ID/根拠保存契約、代表素材品質評価の準備。[仕様](folder-books.md)。

---

## 履歴：P3 画像フォルダを「一冊」（登録時のチェックのみ・自動振り分けなし）（2026-10-16 JST 朝）

開始HEAD `f3fa793`。ユーザー決定：「素材やバラの画像フォルダは今まで通り。取り込み時に『一冊として扱う』にチェックしたものだけ一冊。自動の振り分けはしない」。Hark（Linux sandbox）で実装。**CI起動0回**。仕様は[folder-books.md](folder-books.md)。

### 実装

1. `5157f70` バックエンド：`library_roots.folder_books`（追加migration、既存rootは0）。一冊モードのrootでは画像を直接含む各ディレクトリを1件の `book`（`relative_path` 末尾 `/`、直下は `./`）に。ページ合計サイズと(名前,サイズ,mtime)由来の63bit tokenを保存し、変更でrevision・cache key・AI revisionが変わる。読書manifest/page・プレビュー・タグ入力・読書位置はZIP/CBZと同じAPI。除外ルールとリンク拒否をページにも適用。スキャン後のモード変更は拒否（メタデータが移らないため）。登録時の固定・パスなし検証エラー（重複・入れ子・同意なし・モード変更不可など）を汎用文言でなく具体的に返す（`PUBLIC_FOLDER_ERRORS`）。
2. `9940c51` Core/WinUI：登録パネルに `RootFolderBooks` チェック、再登録prefill、一覧に「一冊モード」、詳細パス表示、一冊は「本を開く」とAIタグ候補の対象（`MediaRow.IsFolderBook`）。`ErrorText`に登録エラー15件の日本語。**バグ修正**：登録後に設定パネルを開く処理がサーバー応答の `root_id` でなく `id` を読み、常に開かなかった。`RegisteredRootRow.Name` がLinuxで `\` 区切りを分割せずCore testが失敗していた。

### 検証（Linux、最小限）

- 全Python **346 PASS**（`test_folder_books.py` 8件：既定は1枚ずつ、一冊化、自然順ページ、直下`./`、再スキャンでID・タグ保持、全画像削除でmissing、除外、モード固定、HTTP登録/読書/具体エラー、リンク不読）。`test_error_text_coverage.py` 3件。
- C# Core **320 PASS**（Linux）、WinUI C#-only compile 0 error。
- **未検証**：Windows Release・XAML・native GUI（チェックボックス配置・一冊の読書・一覧表示）。

### 次の3手

1. Codex/AntigravityでWindows Release＋生成画像フォルダを一冊モードで登録→スキャン→「本を開く」→ページ送り→再スキャンでタグ保持、のnative確認。
2. P3残り：ページ単位ID・ページへのヒット集約・移動追跡・重複候補。
3. 代表素材のタグ品質測定／OCR（いずれもユーザー許可が必要）。

---

## 履歴：P2 未承認タグ候補の明示検索API・Core・WinUI接続とWindows実機確認（2026-10-16 JST 続行）

**現在フェーズ：P2 候補保存・承認API基盤、WDアダプタ導入/実CPU確認、WinUI候補レビュー画面（通常/狭幅/live resize）、および確定タグから分離した「未承認タグ候補」明示検索（`POST /api/library/tag-suggestions/search` / `ModeTagCandidates`）まで実装・Windows実機確認完了。P0 baseline済み・改善試行累積1/2、P1類似検索・登録フォルダ管理ハブ完了を維持。**

開始HEAD `444f9421446898d4c256362153f34a228ffd47e0`。Codexが作業途中で残していた未コミット差分（`app/tag_candidate_search.py`, `app/production_server.py`）を破棄せず保護・検証し、Coreプロトコル・WinUI検索モード・単体/実機テストまで一気通貫で完成させた。既存branch `feat/winui3-production-mvp-20261011` / base `feat/gui-framework-comparison-20261010` / [Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5) を継続。実装commitは **`16c267ea2b5dbe9ce7accbd12a1062debc1a7b76`**。

### 実装と保護

- **バックエンド (`app/tag_candidate_search.py`, `app/production_server.py`)**：
  - `POST /api/library/tag-suggestions/search`（`{query, kind, view, page, root_ids?, shelf?, model?}`）を追加。
  - 通常文字検索（`GET /api/items`）やAI検索に未承認候補を混ぜず、明示的に選択したときだけ各作品の**最新バッチ（`max(id)`）にある `pending` 候補**をNFKC/大小/かな正規化・複数語ANDで検索（空queryでは最新バッチに未承認候補がある全作品を一覧）。
  - 既存の登録フォルダ選択（`root_ids` 1〜256件の和集合、空リスト・重複・未登録/解除済みrootは400で拒否し全件へ拡大しない）、`kind`、`view`（`all`/`favorites`/`unreviewed`/`shelf`）、`shelf`、`model` フィルターを共有。
  - 返却する最大60件について物理sourceの現在revisionと照合し、`proposal_match:{batch_id, source_revision, source_state, state:'pending', tags, producer, evidence}` を付加（モデル起動や推論は一切行わない）。
- **Core / WinUI (`src/Aredoko.Core/SearchMethod.cs`, `Protocol.cs`, `TagReviewClient.cs`, `LibraryApi.cs`, `src/Aredoko.WinUI/MainPage.xaml`, `MainPage.xaml.cs`)**：
  - `SearchMethod.FromIndex(4)`（`IsTagCandidates == true`, `Source == "pending-proposals"`）と、反射不要の `TagReviewProtocol.CandidateSearchRequest` / `ParseCandidateSearch` および `ProposalMatch` を追加。
  - `MainPage` の検索方法コンボボックス（`CmbSearchMode`）に **「未承認タグ候補」 (`ModeTagCandidates`)** を追加し、一覧/グリッドの各行に `ProposalEvidence<id>`（「未承認タグ候補: … / モデル: … · 根拠: 画像または本の先頭ページのみ · 元ファイル一致または元ファイル変更あり（要再生成）」）を表示。

### 検証の事実

- **全Python 337 PASS / 173.064秒 / skip 0**（`test_tag_suggestions.py` **21 PASS / 6.790秒**、`test_error_text_coverage.py` **2 PASS** を含む）。確定タグとの非混入、旧バッチ/承認済み/却下済みの除外、複数語正規化AND、root/shelf/view/modelフィルター、物理source変更時の `stale` 判定、HTTP認証と不正body拒否を確認。
- **C# Core 305 PASS**（`dotnet run --project tests/Aredoko.Core.Tests -c Release --no-restore`、`SearchMethod.FromIndex(4)`、要求正規化、不正 `root_ids` 拒否、`ProposalMatch` 由来/表紙根拠/stale解析、不正応答拒否を追加）。
- **Windows x64 SelfContained Release PASS（警告0・エラー0）**（`dotnet build src/Aredoko.WinUI/Aredoko.WinUI.csproj -c Release -p:Platform=x64 -p:SelfContained=true --no-restore`）。
- **Windows native `python tools/test_tag_review_ui.py --candidate-search-only --output data/ai-ui/tag-candidate-search-20261016-02`**：**24 checks PASS / PNG 4枚（Light/Dark・1200×820および700×620狭幅）全目視PASS / graceful close 2**（初回01はDark側でLight生成item IDと異なるIDを参照したテスト指定ミス1件のみ、アプリ無修正で02完走）。通常文字検索に未承認候補が出ないこと、「未承認タグ候補」モードに確定タグが出ないこと、`ProposalEvidence` のモデル由来・CBZ先頭ページ根拠・stale表示、登録フォルダ絞り込み（`media-1`）、および全未承認候補を承認/却下した作品が未承認候補検索から消えて承認タグが通常文字検索で見つかることを確認。生成素材bytes/mtime・AI設定不変、推論0、CI dispatch 0。

### 次の異なる3手

1. **代表素材のタグ品質と日本語検索寄与の測定**：固定評価で誤タグ/有用性を測る。生成fixtureの動作成功を精度としない。実WDの生成素材GUI smokeも必要時に追加する。私物scanは明示許可の範囲内。
2. **OCR/複数ページ根拠への拡張**：表紙から本文/関係性を断定せず、日本語OCRおよび複数ページ由来の根拠ページ番号を保存してレビューへ渡す。新モデル/追加依存取得は別許可。
3. **P3 画像フォルダの論理作品化・登録フォルダ管理の後続**：画像フォルダを「一冊」として扱うか単体素材として扱うかの分離、検索範囲の名前付き保存・左ナビピン留め、動画/音声内容索引（P4）のbacklogを段階的に進める。

最終実装HEAD **`16c267ea2b5dbe9ce7accbd12a1062debc1a7b76`**。文書込み最終HEADは本節を導入したhandoff commit（`git log -1 --format=%H -- docs/codex-handoff.md`）を正とする。

---

## 履歴：P2候補レビューの狭幅表示を修正・Windows再確認完了（2026-10-16 JST）

**現在フェーズ：候補レビューUIの通常幅/狭幅の最初の縦切りを完了。** 前回の700x620へのlive resizeで詳細が消えるvisual FAILを解消。既存WDの実CPU/API確認と今回の偽adapter UI確認は別の証拠として扱い、実タグ品質/実WD GUI推論の確認とはしない。P0 baseline済み・改善累積1/2、P1、既存検索scopeを維持。

開始HEAD `5b19a4866ba39da5d28e0152ab84b487ce916ca2`、clean・remote差0/0。既存branch/baseと[Draft PR5](https://github.com/jakymiku/Aredoko/pull/5)を継続。最新commitはこの節を追加したgit logを参照。

- 候補一覧/詳細を同じ2列に保ち、狭幅では一覧列を細くする。詳細ScrollViewerを幅0の列・高さ0の行を経由して移動させる処理を除去。根拠画像が未取得/stale/失敗なら空の画像枠を畳み、履歴選択時は詳細を先頭へ戻す。候補の保存・API・索引・ランキングは変更していない。
- Windows x64 SelfContained Release **警告0・エラー0**。`python tools/test_tag_review_ui.py --output data/ai-ui/tag-review-resize-20261016-01` **初回で59 checks PASS**。通常幅1200x820→狭幅700x620→通常幅→狭幅の開き直し、根拠/編集/ボタンの実boundsが非0で可視、狭幅で修正承認しDBへ保存、Light/Dark、既存のdraft/query保持・履歴・未接続表示・stale表示・取消・CBZ先頭表紙を確認。
- **PNG15枚をすべてview_imageで目視しvisual PASS**。前回のFAIL証拠は上書きせず保存。新result.jsonはruntime/visualを分離して記録。所有app2/2正常終了、生成素材bytes/mtime・AI設定不変、モデル推論呼出0。Windows Sandbox無効のまま、前回と同じ所有PID/HWND限定のlocal検証を使用。
- UI/XAML・nativeテスト・文書だけの変更。Python/Core/依存は変更していないため前回の全Python336 PASS/Core PASSを再実行したとは報告しない。WinUIコードレビューで非同期画像の世代確認・取消・テーマ・a11y・編集保持に変更がないことを確認。WinUIAnalyzer/High Contrast/DPI拡大・実WD GUI推論は今回未実施。新規DL・私物scan/変更・OS変更なし。
- CI dispatch0、3workflows manual-onlyを維持。push後のHEAD Actions/checksとremote差分はPR5へ読み取り確認結果を記録する。

### 次の異なる3手

1. **未承認候補の明示検索**：確定タグと分離し、状態/model/根拠・staleを表示する検索API→WinUI。既存のroot/棚scopeを共有し、通常検索を変更しない。
2. **代表素材のタグ品質と日本語検索寄与の測定**：固定評価で誤タグ/有用性を測る。生成fixtureの動作成功を精度としない。実WDの生成素材GUI smokeも未実施のため必要時に追加する。私物scanは明示許可の範囲内。
3. **OCR/複数ページ根拠への拡張**：表紙から本文/関係性を断定せず、ページ由来を保存してレビューへ渡す。新モデル/追加依存取得は別許可。動画/音声内容索引と作品管理のbacklogを保持。

---

## 履歴：P2 WinUIタグ候補レビューの通常幅実装・狭幅の残課題（2026-10-16 JST）

**現在フェーズ：P2の候補レビューUIを実装し、通常幅の生成→根拠確認→修正承認/却下→保存までWindows実機確認。狭幅へリサイズした際の詳細領域が空になる問題が残るため、GUI縦切り全体の完了とはしない。** WD実CPU/API35 checksは前回の実測を維持。今回のnative35 checksは固定候補を返す偽adapterでのUI/API配線検証であり、モデル品質/実WDのGUI推論を測ったものではない。P1を維持し、P0 baseline済み・改善累積1/2・ランキング/閾値/routing変更0を保つ。

開始HEAD `c1aa0510f2a3672438358d2675b66e39e0e48926`。clean・remote差0/0とAGENTS/両handoff/Issue4/PR5を確認して開始。branch `feat/winui3-production-mvp-20261011` / base `feat/gui-framework-comparison-20261010` / [Draft PR5](https://github.com/jakymiku/Aredoko/pull/5)を継続。コミット番号はこの節を追加したgit logを参照。

### 実装と保護

- 画像/CBZ/ZIPの詳細に「AIタグ候補」を追加。ContentDialogで最大10batchずつ履歴、最大30候補、pending/承認済み/却下済み、元タグ/修正タグ、説明、model/revision/adapter/前処理、画像/先頭ページだけの根拠を表示。未接続時も保存済み候補は閲覧・承認可能。stale候補は承認/却下/根拠画像の取得を禁止。
- 根拠用 `GET /api/library/tag-suggestions/{id}/evidence?revision=<64hex>` を追加。既存PreviewReaderの同一handle入力と物理revisionを照合し、変更409/不在404/不正400/Host・token403。8MiB・decode16Mpixel/縮小256pxの既存制限を継承する。revisionは全内容hashではなく既存メタデータtoken。
- 未保存の手動編集があれば閲覧・生成・却下のみ許可し、承認は保存してから再度開く。下のタグ/棚/お気に入りを捨てない。承認要求後は結果の成否にかかわらず最新itemを読み直し、再取得失敗ならそのitemの手動保存を封じて候補画面を開き直すことで再確認。古い編集値で承認タグを上書きしない。
- 検索query/範囲/ページ/選択を変えず、ダイアログ後に詳細へ復帰。生成は普通の40秒clientと別に95秒deadline/100秒transport上限。閉じる操作はrequest IDでserver取消を要求して完了を待つ。HTTPだけを切って取消成功とは表示しない。生成失敗でも履歴/手動検索は保持。

### 検証の事実と失敗

- 全Python **336 PASS / 172.300秒 / skip0**。タグ候補HTTP等は **20 PASS / 6.558秒**。C# Core全契約PASS（reflection JSON無効下、Int64/版/由来/認証/編集承認/応答上限/MIME/取消を追加）。Windows x64 SelfContained Release **警告0・エラー0**。
- Windows Sandbox機能はWin32_OptionalFeature InstallState=2で無効。OSは変更せず、既存ユーザー許可に基づき所有PID/HWNDのローカルテストAredokoのみ操作。port8769/既存Aredokoがあれば拒否するfixtureバッチ `tools/test_tag_review_ui.py` を追加。
- ignored `data/ai-ui/tag-review-20261016-03/result.json`：**UIA runtime 35 checks PASS、PNG7枚すべてview_imageで目視、通常幅5枚は明暗・修正承認/却下・CBZ表紙表示OK、狭幅2枚はvisual FAIL**。Tab/Esc入力、古い履歴、未接続/stale、生成中の閉じる取消（部分batchなし）、通常検索と未保存編集の保持、元fixture bytes/mtime・AI設定不変、モデル推論呼出0・owned app2/2正常終了を確認。sourceは生成76件のみ、私物DB/rootを使わない。
- 初回01はfixtureの同名画像2件を1件と想定したハーネス誤りで停止。02は通常幅機能成功後、狭幅で閉じた後の詳細pane復帰不足で停止。03でテーマ追従・詳細復帰・rootサイズ追従を修正して操作チェックは完了したが、開いたまま700x620へ縮小すると候補詳細ScrollViewer配下がUIA bounds=0となり見えない。これは完了/合格と扱わない。**次回はこの狭幅レイアウト問題を最初に修正する。**
- `winui-ui-testing` skillの「at most two fix-and-rerun cycles」に達したため今回は再試行を打ち切り、visual FAILを残して安全にcheckpoint。次回は候補画面の新しい修正バッチとして、通常→狭幅→通常と狭幅からの新規openを検証する。High Contrast/DPI拡大・実WD GUI推論・承認後の通信断実機試験は今回未実施。
- WinUI code reviewで認証/版固定/上限/非同期/テーマ/a11y IDs/dirty保護を確認。既存構造に合わせ画面イベントをcode-behind、検証/transportをCoreへ分離。WinUIAnalyzer未導入のため未実行、新packageなし。新規DL/OS変更/私物scan/元ファイル操作0、モデル/DB/生結果はGitへ含めない。
- workflows3件はmanual-only、CI dispatch0。push後のHEAD Actions/checks・remote差分を読み取り確認し、PR5の最新記録へ残す。

### 次の異なる3手

1. **狭幅の候補詳細レイアウトを修正・Windows再確認**：動的Grid行/列移動後のScrollViewer子要素のmeasure/boundsを確認。固定レイアウトや適切な再measureなど小さい修正で、開いたまま縮小/拡大・狭幅open・スクロール/キー操作を確認。通常幅の承認/取消を退行させない。WD再導入や同じbackendを作り直さない。
2. **未承認候補を明示選択した検索**：確定タグと混ぜず状態/model/根拠を表示し、root/棚等のscopeを共有するAPI→GUI。stale/履歴を区別し、通常検索は維持。
3. **代表素材の品質評価とOCR/複数ページ**：合成図形のruntime成功を実タグ精度と扱わず、固定代表素材で日本語検索への寄与を評価し、本文/複数ページ根拠へ進む。新モデル/追加依存や私物scanは別途明示許可。P3動画/音声内容索引・P4作品管理・フォルダ操作backlogを保持。

---

## 履歴：WD固定版の承認済み導入・実CPU/API検証とライセンス確認（2026-10-16 JST）

**現在フェーズ：P2のWD導入/実CPU動作gate完了。モデル/追加packageはユーザーが明示許可し、全取得合計6MB/s上限で導入済み。実ONNX CPU→候補/承認API 35 checks PASS、所有worker4/4終了。** WinUI候補/承認画面・候補の全体検索・実タグ精度・OCR/複数ページはまだ未完了。P1のWindows確認済みを維持し、**P0 baseline済み・改善累積1/2・重み/閾値/routing変更0**は変更しない。

開始HEAD **fb65024776698ceea666cf15cf1f2bf896390380**、branch `feat/winui3-production-mvp-20261011` / base `feat/gui-framework-comparison-20261010` / Draft PR5を維持。clean・remote差0/0を確認し、AGENTS/vision/両handoff/Issue4/PR5・導入スクリプトを照合して開始。今回はアプリ/C#/XAMLコード変更なし。測定済み事実とライセンス/次手を文書へ記録するcommitをgit logで参照。

### 許可・導入・既存環境の保全

- ユーザーから「導入してCPU検証まで進めてよい」の回答を受領。許可対象は専用venv/modelsへの固定WDモデル/CSV約468MB＋追加6package約14MB、全取得合計6MB/s以下、生成fixtureだけのCPU確認。**この同じ導入許可を聞き直さない。** 別モデル/追加依存/GPU runtime/私物scanは今回の許可へ含めない。
- `.venv-ai/Scripts/python.exe tools/setup_wd_tagger.py --install-and-download --rate 6000000` **1回成功**。model `SmilingWolf/wd-swinv2-tagger-v3` / revision `627aef95638667ddcaa3ac8ae625e88ea5b02f51`。2artifact固定サイズ/SHA256、wheel hash、pip check前後、CPU runtime import確認済み。model markerを書いて利用可能化。
- 共有TLS proxy上限 **6,000,000 B/s**、実TLS受信 **482,628,627 bytes / 139.813秒**（全体平均約3.45MB/s、瞬間速度計測や新たな帯域保証ではない）。Xet高速経路無効、offline/no-deps install。名目のmodel/CSV467,769,446 bytes＋wheel14,152,326 bytesをTLS overheadと区別する。
- 実inventory比較で、**既存46packageすべて同版**（torch2.9.1+cu128等も保持）、追加はcoloredlogs15.0.1/flatbuffers25.9.23/humanfriendly10.0/onnxruntime1.23.2/protobuf6.33.5/pyreadline3==3.5.4だけ。比較前後JSONとsetup resultはignored `data/wd-setup`。システムPython/ドライバー/OS設定は変更していない。

### 実CPU/API測定

`python tools/check_wd_runtime.py --output data/ai-ui/wd-runtime-cpu-20261016-approved-01` **PASS / 35 checks**。このscriptが作成したPNG2枚・CBZ1冊・破損PNGだけを一時DBへ登録。既存の私物rootや個人DBを使用しない。

| 生成fixture | 候補数 | HTTP所要時間（worker起動・hash・model load・CPU推論込み） |
|---|---:|---:|
| red-shapes.png | 6 | 2265.573ms |
| blue-shapes.png | 6 | 2181.779ms |
| fiction.cbz先頭画像 | 5 | 2119.390ms |

- 実分類→pending候補・model/revision由来、修正承認/却下、二重承認409、最新手動タグとの和集合、保存済み棚/お気に入りの保持、同一batchの再利用で追加workerなし、タグ編集で物理revisionがstaleにならないことを確認。
- 破損PNGは503で部分batchなし。source bytes/mtime・model hash/mtime不変。起動した**owned worker 4/4が終了しstdin/stdoutもclose**。GPU推論は行っていない。
- profile key `921f5736f7fccb4580cbb5e0d5734781827487cb2aea9d3e7d9318332c914ab2`。出力には背景色らしい候補のほか、単なる図形にcomic/solo等も混ざった。**本測定はruntime/API確認であり、実タグ精度・キャラクター・日本語検索・関係性理解の評価ではない。** threshold/topK/ランキングを出力に合わせて変更していない。未承認のまま保持し自動確定しない。

### 回帰・ライセンス・残検証

- 導入後のWD契約 **9 PASS / 6.754秒**。導入後の全Python **335 PASS / 209.176秒 / skip0**。実CPUと全体回帰は同時実行せず、CPU HTTP計測に全体回帰の負荷を混ぜていない。既存source/タグ/検索/scope/reader/videoを含む。
- ユーザーからWDのlicense質問があり、固定revisionの作者README metadataで**Apache-2.0**、ONNX Runtime v1.23.2のLICENSEで**MIT**を公式一次資料から確認。[仕様書のlicense節](wd-tagger.md)に出典と再配布時のlicense/権利表示/変更明示/NOTICE条件等を記録。個人/商用利用・改変/再配布が可能で、Apache2.0自体によるアプリ全体のsource公開義務はない。配布用全依存license/NOTICE同梱を完了したという報告ではない。
- C#/XAML変更なし。Core/Windows Release/native GUIは今回再実行せず前回結果と区別。WinUI承認、実ライブラリ/大規模性能、一般素材/キャラクターのタグ品質、GPU版、OCR/複数ページ/動画・音声内容は未検証/未実装。
- AGENTS/entrypoint/priorities/API/両handoffを実導入済みへ同期。文書リンク/差分確認。許可された固定取得以外のDL、私物scan/変更/送信、OS変更0。model/DB/生結果はGitへ追加しない。3 workflows manual-only確認、CI dispatch0。push後HEADのActions/checksとremote差分は読み取り確認してPR5へ記録する。

### 次の異なる3手

1. **WinUIの候補/根拠・承認/修正/却下**：今回までのadapter/APIを使い、pending/確定/stale・未導入/失敗を区別。draft/scope/検索/readerを保持し、生成fixtureで狭幅/取消/復帰をWindows実機確認。WD導入を再提案/再実装しない。
2. **未承認候補を明示した検索**：通常タグへ自動混入させず、状態/モデル/根拠を明示して対象を選ぶAPIとGUIへ。root/棚等scopeを共有し、古い候補/履歴を区別する。
3. **代表素材の品質/OCR・複数ページ**：分類・日本語検索への寄与を固定した代表素材で評価。図形のruntime PASSを意味精度と扱わず、関係性は本文索引/複数ページ根拠へ。新モデル/追加依存・私物scanは明示許可が必要。P3/P4と登録フォルダ操作backlogを保持。

---

## 履歴：P2 WD分類adapter・固定profile・明示的な上限付き導入手順（2026-10-16 JST）

**現在フェーズ：P2の実adapter接続コードを追加。実モデル/追加packageの取得はユーザーへの確認待ちで未実行、実ONNX CPU推論/モデル品質は未検証。** WinUI候補/承認画面・OCR/複数ページ・候補の全体検索は未接続。P1 Windows確認済みを維持し、P0 v7 baseline済み・改善累積**1/2**・重み/閾値/routing変更0を維持。mock応答や前処理のPASSをモデル実行/精度のPASSとしない。

開始HEAD **6845bd72490462bd2f5c07cb0fce38183c3e7239**。branch `feat/winui3-production-mvp-20261011` / base `feat/gui-framework-comparison-20261010` / 既存Draft PR5を継続。AGENTS/vision/priorities/両handoff/仕様/Issue4/PR5・remoteを照合、clean・差0/0から開始。実装commit **9096aed5c4fc4aa07638f88c85c67058cc03bf8f**、この記録を含む最終HEADはgit log参照。

### 実装

- [WD adapter仕様・制約・導入手順](wd-tagger.md)。`app/tagger_profile.py` / `app/tagger_worker.py` / `app/wd_tagger.py`、`config/tagger-profiles/wd-swinv2-v3.json`。model/revision/2artifact SHA256/入力形状/label数/threshold/topK/timeout/threadを固定、profile hashをproducer版へ。WD互換profileを製品serverの `--tagger-profile` で交換して再起動。公開APIへ任意path/modelを渡さず、起動時の自動取得なし。
- 既存TagSuggestionsへadapter状態を接続し、ローカルasset/runtime markerが未導入なら理由付き503。導入後は画像/CBZ・ZIP表紙のbytesから分類→**未承認候補**まで。raw英語ラベルを保持し、一般>.35/キャラクター>.85/最大30、rating除外、NSFW語による除外なし。説明に分類出力と非確率・画像/表紙のみ/本文・人物関係は未確認を記録。閾値は作者demoの既定を事前採用し、生成図形で調整しない。
- EXIF/最初のframe/白背景alpha合成/正方形余白/bicubic/BGR NHWC float32 0..255、8MiB/16Mpixel、ONNX署名・応答・profile key/有限score境界を検査。モデルはローカル固定SHA、CPU provider4threadsのみ。CPU初版でもAISearch.inferenceを共有し、索引/検索/解放との競合409・終了時last_activity更新。
- 1要求1private worker、90秒timeout・約50ms取消/close監視。自分のPopen instanceだけkill/wait/pipe closeし常駐を残さない。Windows親process handle監視を再利用。main shutdownでtaggerを先にclose。永続queue/複数ページresume/batch/GPU版は未実装。
- `tools/setup_wd_tagger.py`：既定dry-run。明示許可後だけ専用Windows x64 Python3.11 `.venv-ai`で `--install-and-download --rate 6000000`。既存ThrottledProxyで合計6MB/s以下、Xet高速経路無効、wheel hash固定・`--no-deps`・offline install・前後inventory/追加6package限定・pip check/CPU runtime import。既存packageの異なる版は置き換えず停止。既存PyTorch/driver/システムPythonを変更しない。導入完了markerは成功時だけ。
- `tools/check_wd_runtime.py`：許可/導入後だけ使う実CPU/API smoke。固定の生成PNG2枚・CBZ1冊・破損PNG、一時DB、候補/再利用/承認/却下/メタデータ保持・source/model不変・所有worker終了を検査。**スクリプトは準備のみで、今回は未実行**。図形からイラスト/キャラクター精度を主張しない。

### 検証と承認待ち

- 専用venv inventory：EmbeddingGemma2/Laya、torch2.9.1+cu128等は存在、onnxruntime等6packageは未導入。私物/外部model cacheは探していない。公式model card/demo・HF公開metadata・308KBラベルCSV・PyPI metadataを読み取り、revision/サイズ/hash/依存を確定。model重み/wheelは取得していない。
- 新adapter/controller/setup契約 **9 tests PASS / 6.676秒**。模擬JSONの**実子process**で上限/不正/timeout/取消/終了と共有排他、固定profile、設定変更由来、threshold/NSFW除外なし、既定dry-run、mock導入のハッシュ/offline/保全順序を確認。ONNX推論ではない。
- 既存venvで `tools/check_wd_preprocessing.py` **4 tests PASS / 0.299秒**：実Pillow/numpyの生成pixel、BGR/shape/dtype/白背景/EXIF/byte/pixel guard、模擬session形状/不正出力。ONNX runtimeやmodelは未使用。
- 既存候補API **19 PASS / 4.683秒**。途中全Python **334 PASS / 160.395秒**。導入処理のCPU runtime import検査と新mock導入testを加えた後、**最終全Python 335 PASS / 159.459秒 / skip0**。今回の対象/全体テストで未解決failureなし。
- C#/XAML変更なし、Core/Windows Release/native GUIは今回は再実行せず前回の合格と区別。実CPUのタグ出力/速度・GPU・実ライブラリ・OCR・実品質・大規模性能は未検証。文書リンク78件/差分を確認。
- 新規取得の確認をasyncで提示済み：**モデル/CSV467,769,446 bytes + wheel14,152,326 bytes = 481,921,772 bytes（約482MB）**、全取得合計6MB/s以下、専用venv/modelsだけ、生成fixtureでCPU動作確認。追加固定6packageはonnxruntime1.23.2/flatbuffers25.9.23/protobuf6.33.5/coloredlogs15.0.1/humanfriendly10.0/pyreadline3==3.5.4。**まだユーザーの許可回答は届いていない。経過時間や「続き」の一般指示を今回の新規取得承認に置き換えない。** 許可が来たら再確認せず導入→生成smokeへ進める。
- 私物scan/変更/送信0、モデル重み/追加package DL・インストール0、OS変更0、CI dispatch0。3 workflows manual-onlyを確認。push後HEADのActions/checks・remote差分は読み取り確認してPR5へ記録する。

### 次の異なる3手

1. **WD導入/実CPU gate**：今回の取得許可の回答を確認。許可があれば上限付きsetupを専用環境で1回実行し、既存inventory保全・hash・offline CPU workerと生成素材だけのruntime API smoke/全worker終了を実測。失敗は部分導入と未検証を正確に記録し、無断の別モデル/依存取得へ広げない。精度評価は別gate。
2. **WinUIの候補/根拠と修正承認/却下**：既存APIを使いpending/確定/stale・モデル未導入/失敗を区別。draft/scope/検索/readerを保持し、狭幅/取消/復帰を生成fixtureのWindows実機で確認。未承認候補の検索は明示した別条件にする。
3. **代表素材での品質/OCR・複数ページ**：分類ラベル/日本語検索への寄与を固定評価し、未知/誤判定を記録。関係性は表紙で断定せず、ローカルOCR/本文索引と複数ページ根拠へ。モデル/依存追加・私物scanは明示許可が必要。P3論理作品/P4時間付き動画・音声、保存scope/一括除外/キーボードbacklogを保持。

---

## 履歴：P2 由来付きタグ候補・承認/修正/却下APIの基盤（2026-10-16 JST）

**現在フェーズ：P2のバックエンド最初の縦切り。保存・履歴・承認APIと交換可能なadapter契約を実装。実タグ生成モデル・WinUI候補画面・OCR/複数ページ解析・候補の全体検索は未接続。** 製品既定はtagger未設定で生成503。偽adapterの契約検証をAIの品質や製品GUI完成として扱わない。P1類似検索/フォルダハブのWindows確認済みを維持し、**P0 v7 baseline済み・改善累積1/2（採用1）・重み/閾値/routing調整0**は変更しない。

開始HEAD **e7b689053f305ab56c118d44b236b99990aa0da3**、branch `feat/winui3-production-mvp-20261011` / base `feat/gui-framework-comparison-20261010` / 既存Draft PR5を維持。AGENTS/vision/priorities/両handoff/Issue4/PR5とremoteを確認、status clean・remote差0/0から続行。実装commit **efa74b1f7b7cbcd850ecb673dbfe8b2d844042b1**、最終HEADは本節を追加する記録commit（git log）を参照。

### 実装とデータ保全

- [仕様・API・未接続部分](tag-suggestions.md)。`app/tag_suggestions.py`、既存preview/source境界とproduction serverへ接続。既存DBにbatch/proposalの2tableとindexを非破壊追加。adapter/model/version/前処理、物理source revision、画像/表紙、根拠page、元の候補/修正確定タグ、pending/accepted/rejected/version/日時を保存。
- `GET /api/library/tag-suggestions/{item_id}`：認証付きitem固有履歴、stale、available/reason、bounded pagination。`POST .../generate` / `cancel` / `review`：信頼された内部adapterだけ、request IDによる協調取消、原子的な公開/承認。公開APIで任意のpath/model/候補を投入しない。
- 候補を通常タグ検索へ自動混入させない。承認時のみ最新の保存タグと和集合を同一transactionで保存、修正承認/却下・30タグ上限・競合/source再確認失敗時rollback。棚/お気に入り/確認済み/読書位置は変更しない。手動タグ編集はsource revisionと独立し、残り候補をstaleにしない。
- 同じsource/producer再実行は既存batch/決定を再利用（0候補＝未判定も保存）。新source/producer版は別batch、履歴を保全。元ファイルの更新/差替え/除外/解除は古い候補の承認を拒否。revisionはfile identity/size/mtime/ctime等のメタデータtokenであり全内容hashではない。
- adapter入力は検査済み画像/CBZ・ZIP自然順先頭画像の最大8MiB bytes、mime、revisionだけ、根拠page0/最大30候補。初版は動画/音声/PDF/複数ページを解析しない。モデル障害・取消・不正出力・source/adapter変更は部分候補を残さず再実行可。取消は協調式で、永続job queue/強制停止/timeoutはまだない。実adapterは既存AIとのGPU排他・worker timeout/解放を備えてから接続する。
- C#は既存 `ErrorText` 辞書への日本語15文追加のみ。XAML/GUI構造・検索ランキング/AI索引profile/既存viewerは未変更。AGENTS/agent-start/priorities/APIを現在地に同期。

### 今回の検証・失敗履歴・未検証

- P2新規 **19 tests PASS / 6.613秒**：一時DBと生成PNG/2ページCBZ、固定の偽adapter。候補/確定分離、編集承認/却下、手動並行編集、再起動/新producer/再解析/未判定、stale/差替え/rollback/上限、取消/再試行、2service同時公開、scan/除外/解除復元、pagination/ID/HTTP認証/409/503。
- 初回の対象15 testsは読書位置レスポンスを `page`直下と誤認して1error。既存仕様の`progress.page`にテストだけ修正。HTTPErrorを明示closeしてResourceWarningも除去。
- 初回全Python **325実行/193.507秒・1failure**：新server固定エラー3文の日本語辞書登録漏れ。固定/実行時を含む15文を既存辞書へ追加し、新たな実行時エラーcoverageも追加。対象のlocale coverage **2 PASS**。
- **最終全Python：326 PASS / 194.084秒 / skip0**。既存検索・保存・登録フォルダ・類似・preview/reader/videoを含む。`NO_PROXY=127.0.0.1,localhost python -m unittest discover -s tests -p 'test_*.py' -q`。
- `dotnet run --project tests/Aredoko.Core.Tests -c Release --no-restore` **PASS**。`dotnet build src/Aredoko.WinUI/Aredoko.WinUI.csproj -c Release -p:Platform=x64 -p:SelfContained=true --no-restore` **PASS / 0 warnings / 0 errors / 15.73秒**。
- winui-code-reviewスキルに沿い変更したC#辞書をレビュー：新UI/API/非同期/反射処理なし、既存辞書方式に限定しエラー網羅を検証。native GUI操作は今回未実行、WinUIAnalyzerはprojectに参照なく今回未実行/未追加。実モデルのタグ品質/GPU推論/OCR/実ライブラリ/大規模性能は未検証。前回P0 GPUや前回P1 nativeの合格を今回P2の検証に流用しない。
- 私物scan/変更/送信、モデル/依存DL、OS変更、CI dispatchは0。3 workflowsはmanual `workflow_dispatch`のみを確認。変更文書のローカルリンク/差分を検査。push後のHEAD Actions/checksとremote差分は読み取り確認して既存PR5へ記録する。

### 次の異なる3手

1. **実タグ生成adapterの接続**：既存ローカル資産と正式入力仕様を確認し、GPU排他/timeout/解放/取消を持つ交換可能なadapterへ。新モデル/依存取得は明示許可が必要。固定した小規模素材で品質を別測定。既存埋め込みを生成タグモデルと称さない。
2. **WinUIの候補/根拠と修正承認/却下**：今回APIを利用し、pending/確定・stale・未接続/失敗を区別。draft/scope/検索/readerを保持してWindows実機の小さな縦切りを確認する。未承認候補を対象にする検索は明示的な別条件で追加する。
3. **OCR/複数ページ文脈**：利用可能なローカル機能を確認、本文索引とページ根拠へ。表紙から関係性タグを断定しない。保存scope/一括除外/キーボード、P3論理作品、P4時間付き動画/音声索引のbacklogを維持し、理由なくP0を再開しない。

---

## 履歴：P0 新固定baseline実測・空cover候補の推論省略で一区切り（2026-10-15）

**現在フェーズ：P0今回の区切り完了、P1類似検索・登録フォルダハブのWindows確認済みを維持。P0新baseline済み、改善試行累積1/2（採用1件）、品質重み/閾値/routing調整0件。次はP2由来付きタグ候補/承認/OCR。** 残り1枠を埋めるためだけの追加試行はせず、新指示/実運用の失敗/新退行がない限り同じP0を再開しない。

開始HEAD **25034815e45cd3de80866c0056a6e5c2bffa9cfc**、status clean・remote一致を確認。AGENTS/vision/新priorities/folder-library-management/両handoff/Issue4・Draft PR5を読み、OpenCodeのP1とフォルダハブを作り直さず次へ進めた。製品branch/base/既存Draft PR5を維持。今回の実装commit **6747d9a5b4609a8f83b9ac3ab3f75486473cdf54**、文書込み最終HEADは本節を導入する記録commit（git log）を参照。

### 固定入力と実装

- v7：**9dd32b0**で順位観測前に24生成素材・24問を凍結。SHA **8212da5d4c146c8ac1086e04c95a3514d3564a1171cb3f9fe66498389f7e499b**。PNG12/CBZ4/SVG4/無音WAV4、metadata/pixels/一致/意図的矛盾/架空alias/no-answer。旧v1/v2/v6のquery/filenameと非重複・旧入力不変。
- `tools/evaluate_search_phase.py`：literal/related/text/cover/combined × A+B/root-Aの240結果、Top1/Recall@5/MRR/Precision@5/no-answer/latency。scopeで正解が除かれる場合、source非対応、真正no-answerを区別。偽encoderの契約検査には実品質と異なるラベルを付ける。fresh ignored出力だけ、任意source/モデル引数なし。
- 実GPU `search-phase-v7-baseline-01`：**runtime PASS/273 checks/240行、document24/image16/query144、index40.889秒、torch peak allocated931.8MiB**。既存専用venv・固定EG2/auto-bf16のみ、Laya/新DLなし。source bytes/mtime/hash、vector bytes、固定入力不変、owned process-instance handle3件全終了。
- 新しい別確認入力は**c5ca371**で観測前凍結（`cover-empty-v1.json`、5素材/6問、SHA **f7a734f3a720732dfa93e491c358d95f6157222395ce2780e728e6ab1b4aa78a**）。`tools/check_cover_empty.py`で前後各1回を比較。
- 試行1：`app/ai_search.py`のsource=coverに限り、shared cap/明示scope・kind・view適用後の候補を現cover対応image/bookへ制限。空ならquery推論しない。非画像の紛れたcover cacheも拒否。combined/text・通常検索・scope・重み/閾値は維持。前後6件の結果ID/順序不変、query呼出 **6→2**、空4件の時間中央値 **89.591ms→11.132ms**（単発・非隔離の診断）。全source/vector不変・owned worker終了。品質点数の改善ではない。
- AGENTS/agent-start/priorities/READMEをP0区切り→P2へ同期。media-content-planに残っていたP1 Windows未検証表記を実態へ同期。動画/音声内容索引の最終目標を維持。

### 実測の読み方と残課題

[結果表・失敗分析](search-phase-v7-results.md)・[測定前記録](search-phase-v7.md)。all-rootsでは視覚のみ6問でcover Top1 **6/6**、combined **0/6**（Recall@5 4/6）。metadata8問はtext **8/8**、combined **7/8**。label/pixelが矛盾する4問では欲しい根拠で適切なmodeが異なる。真正no-answer2問はliteral/related 2/2空、text/combined 0/2空、coverは有効な画像query1問で0/1空。人工の幾何図形とmetadata設定に重みを過適合させず、既知の混合順位・no-answerをbacklogとして保持。単一正解queryのPrecision@5は5件返却なら最大0.2。audioは無音、CBZは図形で、音声/本文理解ではない。

検索時間は一部ローカル回帰との同時実行下の単発診断。**実ライブラリ精度、UI到達時間/操作回数、多DPI/実GPUのGUI経路、長編/大規模性能は今回未測定**（UI指標はnull）。native GUI/C#/XAMLは今回未変更、Core/Release/nativeは再実行せず前回OpenCodeの合格を今回の検証に流用しない。

### ローカル回帰と失敗履歴

- 新評価契約 **3 PASS**、empty cover **2 PASS**、既存AI検索 **13 PASS**。試行前の全Python **304 PASS/166.427秒**。
- 試行後初回全306は1error：visual/textの独立性テストがaudio placeholderへcover vectorを入れていた。対応kindのPNG2件を生成するfixtureへ直し、逆向きのtext/cover vectorによる元の順位/source/不正modeの検査意図は保持。非画像stray cover拒否は新テストで別に保証。P0新仮説ではなく試行1内の契約fixture修正。
- **最終 `NO_PROXY=127.0.0.1,localhost python -m unittest discover -s tests -p 'test_*.py' -q`：306 PASS/158.807秒/skip0**。既存類似検索・複数root/フォルダ・保存・preview/reader/videoを含む。diffチェック・変更文書リンク確認PASS。
- 私物scan/変更/外部送信0、モデル/依存追加0、OS変更0。生成データ/DB/生ログはignored `data/ai-ui`、コード/固定入力/集計文書のみGit保存。3workflow manual-only、CI dispatch0。push後HEADのActions/checksは読み取り確認してPRへ記録。

### 次の異なる3手

1. **P2由来付き候補/アダプタ/API**：model/version・対象revision・根拠ページ・候補/確定/却下の最小スキーマ。生成fixtureで再解析が手動確定タグを上書きしない、stale/取消/再開を検証する。
2. **WinUI承認/修正/却下と根拠**：推定と確定を分け、未保存draft・scope・検索/readerを保って、小さいWindows実機の縦切りを完成させる。
3. **OCR/複数ページ文脈**：既存ローカル機能とモデル仕様を確認し、ページ文字索引へ接続。新依存/モデル取得は明示許可が必要。関係性を表紙だけで断定しない。保存scope/一括除外/Shift+F10、P3論理作品とP4時間付き動画/音声内容索引はbacklogを維持する。

---

## 履歴：P1 類似検索のWindows実機検証完了＋登録フォルダ管理ハブ・複数root統一検索・一括初期棚の実装（2026-10-15 Windows続行）

**現在フェーズ：P1（アイテム起点の画像・表紙類似検索）Windows実機検証完了＋ユーザー合意の登録フォルダ管理ハブ（単一/複数root統一検索・初期棚単一/一括編集・解除/復元）実装およびWindows実機検証完了。P0新baseline：未実施、P0改善試行累積：0/2を維持。**

開始remote HEAD `4c98bafa3e2703fc6f0355873104bc8e89cbc3b2` → 途中の文書追記 `f6616b9811aeb13097922445d5cfa3c488ddcbb9` をローカル変更を破棄せず取り込み。製品branch `feat/winui3-production-mvp-20261011`、base `feat/gui-framework-comparison-20261010`、[既存Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5) を継続。

### 実装と保存commit

1. **bb1e6c28612f7e8a8d8e8c8c01425d58b4e38667** — P1 類似検索のWindows実機確認で判明した境界を修正：
   - 類似検索から元の検索ページ（例：2/2）へ戻った直後、新しい `ListViewItem` のXAMLレイアウト完了を待って `ScrollIntoView` と `Focus(FocusState.Keyboard)` を行う `FocusRowAsync` を `src/Aredoko.WinUI/MainPage.xaml.cs` に追加。
   - `src/Aredoko.WinUI/MainPage.xaml` の `SimilarityBar` を1行 `Grid` に整理し、狭幅 `700×620` でも一覧領域が潰れないよう改善。
   - `app/server.py` で Windows のクライアント切断例外 `ConnectionAbortedError`（WinError 10053）を通常切断として扱い、`ThreadingHTTPServer.request_queue_size = 128` と `Connection: close` を設定してプレビュー並行要求バースト時のTCP backlog溢れを解消。
   - `src/Aredoko.WinUI/Aredoko.WinUI.csproj` に、Windows Updateで .NET SDK `10.0.402`（`10.0.13`）が入った環境でも既存のローカルNuGetキャッシュ（`10.0.12`）だけで `--no-restore` ビルドが通る条件付きターゲット `UseCachedRuntimePacks` を追加。
2. **a87d6b4fc31ab0cdc08ccf12134657be8c8125d6** — [folder-library-management.md](folder-library-management.md) に基づく登録フォルダ管理ハブ・複数root統一検索・初期棚編集を実装：
   - **API / Python (`app/library_index.py`, `app/production.py`, `app/production_server.py`)**：`GET /api/library/roots` の各rootに索引済み `present_count` を付加（新規スキャンなし）。`GET /api/items` と `ProductionCatalog.search` に `root_ids`（1〜256件の有効な正Int64登録root IDの和集合OR、重複・空・未登録/解除済みroot・`root_id`との同時指定は400で拒否し全件へ拡大しない）を追加。単一 `root_id` は互換維持。
   - **Core (`src/Aredoko.Core/FolderSearch.cs`, `FolderHubState.cs`, `LibraryApi.cs`, `SimilaritySearch.cs`, `ErrorText.cs`)**：複数rootの `LiteralRouteMulti` / `RestrictAIMulti` / `SimilaritySearch.RequestMulti` / `SearchMultiAsync` / `SimilarMultiAsync`、同名末尾フォルダを親ディレクトリ付きで区別する `RegisteredRootRow.ShortPath`、単一/一括初期棚ドラフト `FolderSettingsDraft`（「複数の設定値」「変更しない」「棚なし」「新規棚」の区別、変更項目のみの保存、部分失敗時の残りroot再試行管理）、および検索範囲とAI scope積集合の説明 `FolderScopeDescriber` を実装。
   - **WinUI (`src/Aredoko.WinUI/MainPage.xaml`, `MainPage.xaml.cs`)**：左ナビの動的フォルダ列挙を廃止して単一の「登録フォルダ」（`NavFolders`）に集約。メインビューの登録フォルダ一覧 `FolderHubView`（リスト/グリッド切替、名前/パス絞り込み、登録中/解除済み状態フィルター、チェックボックス複数選択、0件選択時の検索/設定/解除ボタン無効化、単一フォルダ「中を見る」「設定」、新規追加/再登録パネル）と、右詳細パネルの `FolderEditorPanel`（単一/一括初期棚保存、`FillUnsetShelf` 明示適用、単一除外更新・スキャン・中断、単一/複数登録解除、未保存変更の破棄確認）を接続。類似検索からの復帰（`SearchBookmark`）でも複数root選択を保持。

### 正確な検証結果（Windows実機、CI起動0回）

- **全Python 301 PASS / 183.330秒 / skip 0**（`NO_PROXY=127.0.0.1,localhost python -m unittest discover -s tests -p "test_*.py" -q`、`test_folder_search.py` 12 PASS、`test_similarity_search.py` 16 PASS、`test_similarity_sandbox.py` 5 PASS、`test_error_text_coverage.py` 1 PASS を含む）。
- **C# Core 280 PASS**（`dotnet run --project tests/Aredoko.Core.Tests -c Release --no-restore`、類似検索51件＋複数root/フォルダ管理19件を含む）。
- **Windows x64 SelfContained Release PASS**（`dotnet build src/Aredoko.WinUI/Aredoko.WinUI.csproj -c Release -p:Platform=x64 -p:SelfContained=true --no-restore`、0 warnings / 0 errors）、`test_winui_compile_stub.py` **3 PASS**。
- **P1 類似検索 Windows一括検証 (`Check-Similarity.cmd`)**：
  - `similarity-check-20261015-120824-dbfe63`：**PASS（diff-check / Python 300 PASS / Core 264 PASS / Release PASS / native 41 checks PASS / PNG 10枚全目視 / graceful close 2）**（先行診断 `114301-4b31e2`・`115519-ea9b7d` から2修正cycle内で解決）。
  - `similarity-unindexed-01`（`--scenario unindexed`）：**PASS（9 checks / PNG 2枚全目視 / graceful close 2）**。
  - `similarity-text-only-01`（`--scenario text-only`）：**PASS（9 checks / PNG 2枚全目視 / graceful close 2）**。
  - `similarity-doubleclick-reg-01`（`--double-click-only`）：**PASS（22 checks / keys 16 / skip 0 / PNG 8枚全目視 / graceful close 2）**。
- **登録フォルダ管理ハブ・複数root検索 Windows実機検証 (`tools/test_folder_hub_ui.py`)**：
  - `folder-hub-native-07`：**PASS（37 checks / PNG 10枚全目視 / graceful close 2）**。Light/Dark・1200×820と700×620狭幅で、左ナビが単一 `NavFolders` のみであること、0選択時の検索無効化、同名末尾フォルダ（`branch-a/works` / `branch-b/works` / `branch-c/works`）の識別と絞り込み・リスト/グリッド切替での選択保持、単一「中を見る」とハブ復帰、A+B複数root選択での通常文字・AI・類似検索（C除外・自己除外）と類似検索からのA+B復帰、一括初期棚の「複数の設定値（変更しない）」無変更保存（既存値維持）、未保存設定の破棄確認キャンセル、部分失敗（A成功・B失敗）からのB単独再試行成功と個別手動棚の保全、登録解除と解除済み一覧からの再登録によるタグ・棚復元を実機確認。
- 全runで生成mediaのbytes/mtime/hash不変、settings bytes不変、AIモデルロード0、私物scan/変更/外部送信0、依存/モデル取得0、**CI dispatch 0**。

### 残課題・未検証と次の異なる3手

- **未検証範囲**：Shift+F10等のキーボードのみでのコンテキストメニュー起動、検索範囲の名前付き保存・左ナビへのピン留め、除外ルールの一括編集、高DPI/High Contrast/Narrator/Tab全順序、実AIモデル/GPUを用いた新固定評価セット実測。
- **次の異なる3手**：
  1. **P0 検索品質の新固定baseline実測と小改善（最大2試行まで）**：既存v1/v2/v6を変更せず、新しい20〜50問の固定評価セットを結果観測前に確定して一度実測し、根拠のある小改善（0〜2件）でP0を一区切りにする。
  2. **P2 由来付き視覚タグ候補と承認フローの最小縦切り**：自動タグ候補の保存スキーマ（モデル/版・対象revision・根拠ページ・候補/確定/却下）とWinUI承認・修正導線を小さな生成素材で実装し、手動確定タグと区別して検索・保全できるようにする。
  3. **登録フォルダ管理の後続・P3準備**：検索範囲の名前付き保存・左ナビへのピン留め、除外ルールの一括追加/置換、Shift+F10キーボード導線、および画像フォルダを「一冊」として扱う論理作品化の設計・移行テストを進める。

最終実装HEAD **a87d6b4fc31ab0cdc08ccf12134657be8c8125d6**。文書込み最終HEADは本節を導入したhandoff commit（`git log -1 --format=%H -- docs/codex-handoff.md`）を正とする。

---

## 方針追記：登録フォルダ管理・複数選択検索・初期棚編集（2026-10-15 21:10 JST）

**今回：文書のみ。製品コードの変更・新規テスト実行・Windows確認・CI起動なし。OpenCodeはユーザー側で現在開発中。** 文書作成時remote HEADは `4c98bafa3e2703fc6f0355873104bc8e89cbc3b2`、既存の製品branch／Draft PR #5／baseを確認。ローカルの未commit変更・進捗は未観測。本追記は、実装状況やP0試行回数を過去の状態へリセットするものではない。直下の実装記録と、より新しいコード／テストを照合する。

ユーザー合意を [folder-library-management.md](folder-library-management.md) に集約し、AGENTS・vision・agent-start・development-prioritiesから参照した。

- 左側の全登録root列挙を「登録フォルダ」入口へまとめ、メインのリスト／グリッド・名前／パス絞り込みから単一閲覧／複数選択検索を行う。
- 通常／AI／類似検索で選択rootの和集合を共有。他の明示フィルターを維持し、空／解除／未接続で全件へ範囲を拡大しない。検索用の選択でAI索引設定を勝手に書き換えない。
- 登録時の項目はタグではなく既存の「初期棚」。右詳細等で初期棚・除外・スキャン・解除／再登録を編集。一括編集は変更項目だけ保存し、「変更しない／複数値／棚なし」を区別。既存未設定への適用は明示操作、個別の棚と元ファイルを保全。
- 検索範囲の保存／ピン留めは後続。一般的な見た目の全面刷新やサブフォルダ任意範囲検索は初期必須にしない。

### この追記に対する次の3手

1. **作業中のOpenCodeを中断・上書きしない。** 現行タスクを安全に区切り、branch／HEAD／status／未commit差分と最新remoteを確認。文書更新の取り込みはローカル変更を保全して行い、reset／force pushで同期しない。
2. 新仕様と現在実装を照合し、登録フォルダ画面＋既存の単一設定移行→複数root検索→一括初期棚／解除の順に、小さく実装・局所検証。既に進んでいれば残差だけ扱う。
3. 各段階で結果／未検証／次の異なる作業を記録。Windows実操作ができなければ未検証と明記し、P0／P1等の既存進捗・有限な評価枠・manual-only CI方針を維持する。

---

## 最新：P1バグ取り・Windows一括検証の準備（2026-10-15 続行）

**現在フェーズ：P1 API/生成fixtureとWindows検証入口まで実装、Core/Release/nativeは実機確認待ち。P0新baseline：未実施、改善試行累積0/2を維持。** ユーザーの「帰宅後Codex/OpenCode等でテスト・ブラッシュアップできる状態まで」の依頼に対応。開始remote HEAD **80e618e3e45dc4db10bbecd6bd8acb7ad8b4947b**、同じ製品branch/Draft PR5/base・cleanの隔離snapshotを確認。他AIのremote更新なし。ユーザーPCのworktree状態は未観測。

### 追加実装とバグ取り

- **破棄承認→類似検索取得中→戻る**で、既に破棄を承認した旧draftを再度確認しないよう修正。通常のdirty結果から戻る場合は確認を先に行う。取消後のBusy/ItemListの無効状態を回収し、戻る取得中に変更された検索語も再検索へつなぐ。検索欄の名前/placeholderも実際の通常検索モードと一致させた。native再現検証は下記の準備コードまで、今回未実行。
- Coreの類似応答をbounded HTTPへ：10秒deadline、JSON MIME、最大2MiBと長さ、起点/モード/source/profile識別子/revision形式/ページ/件数・重複/自己/非画像混入・cosine範囲を検査。反射不要を維持。Coreに正常/不整合/過大応答の検査を追加したが.NET SDKがないため未実行。
- 非unit/破損vectorを起点はunindexed・候補はskip。画像/本/ZIP以外に不正なcoverが保存されていても候補にしない。HTTP取消後のBrokenPipe/ConnectionResetを通常の切断として扱い、応答を再送しない。
- `tools/similarity_sandbox.py`：新規ignored出力に76件の生成画像/CBZ等と固定3次元vector・2root・専用DB/設定を用意。model/encode0でも72類似結果を2ページで確認。indexed/unindexed/text-onlyと409/503/遅延を用意。既存の8769番やユーザーアプリへ接続しない。
- `Check-Similarity.cmd`→`tools/check_similarity_local.py --native`でPython→Core→Release→`test_similarity_ui.py`のLight/Dark batchを一度実行し、結果/段階log/PNG/UIA treeを新規data/ai-ui以下へ保存。依存install/restore/download・CIは実行しない。所有PID/HWND以外を操作・終了しない。全PNGは目視待ちを明記し、runtime合格と混同しない。
- **[帰宅後の手順と、そのままCodex/OpenCodeへ渡せる指示](windows-similarity-handoff.md)** を追加。AGENTS/agent-start/item-similarityから参照。

### 確定した検証結果と境界

- 最終 `python -m unittest discover -s tests -p 'test_*.py'`：**300 PASS /34.080秒/skip0**。類似API16、sandbox5（ページ/同scope・元bytes/mtime・設定/vector不変・実HTTP・fallback/409/503・切断応答）を含む。初回sandbox HTTPはテスト用subclassのlimit引数漏れで1error、署名をproduction APIに合わせて修正し5件PASS。モデル品質評価ではない。
- AI scaling6 PASS、WinUI名前付きXAML stub3 PASS、Python構文/CLI help、XML整形式、diff/文書リンクを確認。過去のPython294を今回の成功に流用していない。
- **Coreテスト実行/.NET C#コンパイル/Windows Release/native/全PNG目視・キーボード/多DPI/実GPUは未検証。** 新しいWindows runner/native harnessもPython構文とfixture/API確認まで。実機のpopup/selector/focus差は残るので、結果を読まず合格扱いにしない。
- CI dispatch0、manual-only維持。モデル/依存/OS変更・私物scan/アップロード・main merge/force push/new PRなし。テストが印字する既存download案内はmock由来で実取得ではない。

### 次の3手

1. Windowsの作業ツリー/remote/未commitを確認して同期後、`Check-Similarity.cmd`を一度実行。失敗段階のlogを読み、Core/Releaseを直してからnativeへ。既存導入/復元済み環境だけを使う。手順と期待結果はwindows-similarity-handoff.md。
2. native全PNGを目視し、list/grid/詳細・dirty取消/破棄直後取消・復帰/page/focus・scope/fallback/409/503を確認。必要ならShift+F10/既存viewer/Range/seekの回帰を別に確認。最大2修正cycleで未解決なら原因/未完了を記録し、反復で停滞しない。
3. P1のWindows確認を区切り、未実施P0固定baselineを結果観測前に凍結して一度記録（モデル未導入ならその条件を分離）。改善0件または累積2件で区切り、P2の由来/承認付き候補タグ・OCRへ進む。現在P0累積0を勝手に完了扱いにしない。

---

## 最新：P1 画像・表紙のアイテム起点類似検索（2026-10-15）

**現在フェーズ：P1 API/生成fixture/Core/WinUI導線のソース追加済み、Windows検証待ち。P0の新baseline：未実施。P0改善試行の累積：0/2。** 今回はユーザーの明示依頼が類似検索API/右クリックの実装であり、その縦切りへ進んだ。P0完了や実モデルの精度改善を宣言しない。同じ評価ループを再開しない。

開始remote HEAD **73ca81afb6fe2aa0158cafcaccef41f1b874b05f**、製品branch `feat/winui3-production-mvp-20261011`、既存Draft PR #5/baseを確認。AGENTS/vision/priorities/agent-start/両handoff/Issue4を参照。環境に作業ツリーがなかったためGitHubからこのSHAのテキストソースを取得し、比較用experiment/画像assetsを除く隔離snapshotで検証した。ユーザーPCの未commit変更は観測していない。remote反映はこのSHAを親にする差分commitで行い、比較資産/assets/履歴を削除・再生成しない。記録commitは本節を追加したcommitを参照。

- `POST /api/library/ai/similar`：同profile namespace/current revisionのcover vector再利用、scope・root/種類/棚/除外、自己除外、kind/view・paging、1万件shared cap、origin/candidateの処理後再確認。未索引/古い/破損origin、text-only profileは空結果＋明示status。推論/自動索引/source読取/モデル起動なし、encoder未導入でもcache検索可能。scan/index/search競合409、Host/token/Origin・body制限を維持。scope IDのInt64超過をDB到達前に拒否し、壊れたcandidate vectorをskipするよう補強。
- WinUIのlist/grid/詳細プレビューにnative context menu「似た画像・素材を探す」。右クリックしたrowを起点とし、dirty取消なら要求/遷移なし。origin名・cover根拠・cosine表示、元の検索条件/view/pageへの復帰・起点行focus、HTTP取消/versionによる遅延応答排除。動画/音声の類似検索を有効にしない。既存文字/AI検索・根拠・画像/reader/videoコードを維持。**GUI動作は今回未検証**。
- [仕様・API・Windows確認項目](item-similarity.md)を追加。api/agent-start/media-content-planを同期。

### 今回の確認結果

- 最終 `python -m unittest discover -s tests -p 'test_*.py'`：**294 PASS /34.012秒/skip0**（既存279＋新規similarity15）。生成PNG/CBZ/contract vectorで順序・自己除外・scope/profile/revision/前処理分離・未索引fallback・paging/cap・競合・HTTP認証・元bytes/mtime不変・検索時encode0。実モデル精度の証拠ではない。
- 初回similarity14件は13 PASS/1 error（テスト側で存在しないprofileフィールド名を使用）。実profileのnamespace仕様に修正後14 PASS、全293 PASS。その後candidate破損回帰1件とscope ID境界を追加し、対象scope12/similarity15/error対応1 PASS、上記最終全294 PASS。無目的な再実行を続けない。
- CoreにSimilarityTests（JSON/scope/route/token/Origin/取消/旧応答互換/根拠）を追加。**.NET SDKなしのため未実行**。Windows Release/native GUI・実モデル/GPU・多DPI/Narrator/Contrastも未検証。旧Core213/Release/native合格を今回に流用しない。
- `git diff --check`、Python構文、XAMLのXML整形式を確認（XAMLコンパイルではない）。3workflowともmanual-only、**CI dispatch0**。モデル/依存/OS変更・私物scan/外部送信・main merge/force push/new PRなし。

### 次の3手

1. WindowsでCoreテスト→x64 SelfContained Release→生成fixtureのnative右クリック/list/grid/詳細・dirty取消・復帰/page/focus・遅延/取消/close・未索引/503/409を実行。手順はitem-similarity.md。外部環境がない場合は同じ評価再実行で停滞せず未検証のまま保留する。
2. P0の未実施baselineは20〜50問を結果観測前に凍結し、一度記録。実モデルが使えない条件と人工contractを区別し、改善0件または累積最大2件で一区切りにする。
3. P1の残る重大退行がなければP2の承認可能な候補タグ/由来スキーマ→OCRの小さな縦切りへ。動画/音声内容索引・フォルダ本はbacklogを維持。

---

## 最新：大容量動画・シークバー・時刻付きサムネイル（2026-10-15）

開始HEAD `267d4820a06c541d3d71b86155727ef2fcc538da`。range実装 `65d824c`、シーク/UI・内容索引計画 **`91d59c24aa48c7d9b1e4982032613c0d4851b453`**。文書込み最終HEADは本節の記録commit（`git log -1 --format=%H -- docs/codex-handoff.md`）を正とする。既存製品branch/base/Draft PR5を維持。remoteへ他AIの新commitはなく通常fast-forwardのみ。

### 実装

- 動画全体の64MiBメモリcopyを通常再生から除去。manifest＋認証付き1MiB以下のRange、2TiB input上限、独立nativeカーソルと取消、Content-Range/ETag/MIME/長さ照合。[動画範囲再生](video-streaming.md)。互換旧API64MiB・先頭thumbnail512MiBは維持。生成70MiB末尾moovへ実native offset73,400,320を確認（range76requests、最大262,144bytes）。
- **シークバーのクリック/ドラッグ・左右keyboard、現在位置同期、hover位置の時刻と実サムネイル**。hoverだけで再生位置を変えない。320ms debounce・1進行要求・最寄り秒・LRU/取得サイズ/期限で負荷を制限。取得不可は「サムネイルなし」、動画再生/シークを継続。遅延frameは閉じる/別viewer/version境界で排除。[シーク仕様](video-seek-preview.md)。
- 下部帯Stretch/margin0/左右border0/corner0でコンテンツ端に揃える。auto-hide/F10/Tab/Esc、未保存draft/focusを保持。APIのframe取得はsourceの読み取りハンドルをfdで継承し、入力protocol/demuxerを制限。元データを再エンコード/変更/一時copyしない。
- **ユーザーの最終目標を保存**：EmbeddingGemma 2中心の画像・動画・音声/音楽内容解析→DB化→曖昧検索、および右クリック「類似検索」。[内容索引計画](media-content-plan.md)・product-vision・AGENTS参照を追加。モデルの直接入力仕様確認と前処理、交換可能profile、時間区間の出典が必要。**動画/音声のmetadata登録と名前/タグ検索は既存、内容索引とアイテム起点類似検索は未実装**。

### 確定したローカル検証

- `python -m unittest discover -s tests -p 'test_*.py'`：**279 PASS /132.626秒/skip0**。新frame3件では実FFmpegで赤0秒→青1秒の取得/cache/source hash・mtime不変、認証/query/revision/除外/解除/busyを検証。初回Python先読みbufferと子のOS offsetずれを修正済み。
- `dotnet run --project tests/Aredoko.Core.Tests/Aredoko.Core.Tests.csproj -c Release`：**213 PASS**。範囲/EOF/不整合/変更・busy/取消、frame時刻・固定route・PNGサイズ/MIMEも含む。
- `dotnet build src/Aredoko.WinUI/Aredoko.WinUI.csproj -c Release -p:Platform=x64 -p:SelfContained=true --no-restore`：**PASS27.97秒/0error/既存IL2104 2warnings抑制なし**。
- range native03：**73checks/keys30/skip0/PNG12全目視/graceful close2**。01はprefixだけでcodecが足りるfixtureのoffset証拠条件、02は末尾moovで旧thumbnail不可なのに必須にしたテスト前提が失敗。2修正cycleで03完走。
- seek native03：**88checks/keys40/skip0/PNG18全目視/graceful close2/cleanup失敗なし**。Light/Dark・wide/narrowでslider/keyboard・hover青1秒＋再生0秒・preview503でもseek継続・遅延frameのclose後排除、MP4/WMV/非対応/破損、503retry/409、再生/停止/音量、auto-hide/F10/Esc、draft/focusを確認。01は中心時刻の切捨て境界、02はauto-hideしたclosebuttonをfocusする旧テスト前提が失敗。最寄り秒/標準tooltip無効化と常在viewportへのEscapeへ2修正で03完走。失敗証拠全PNGも確認。
- source bytes/mtime・test settings不変、AI/model呼出0、private libraryアクセス0。ログ/生成media/layoutはignored `data/ai-ui`内。コード/仕様/テストだけGit保存。manual code review実施、専用WinUI analyzer未導入/未実行。

### 限界と次の3手

実測は2秒生成動画、range側は70MiB。長編/高bitrate/2TiB実動画・高負荷同時処理・再生中の実更新/切断回復、多DPI/Narrator/Contrast/Native AOTは未検証。frame時刻は24時間まで（超過hoverは上限に留まる）、backend子はHTTP取消で即時killせず10秒deadlineで回収。codec内部RAMの固定保証はない。UI/native検証の2修正cycle上限を完了し、理由なしに同じバッチを追加rerunしない。

1. 既存画像embeddingでアイテム起点類似検索API/右クリックUIを設計し、同一profile・scope・自己除外・未索引fallbackを生成fixtureで検証する。
2. モデル入力仕様と索引形式を確認し、時間付き代表frameの動画内容索引・元itemへの集約検索を縦切りする。
3. 音声認識/音響・音楽特徴の方式を比較して内容索引を拡張する。各段階で新固定検索評価と資源制御、狭幅/多DPI/keyboardの未検証範囲も確認する。

CIは3workflowともworkflow_dispatchのみ、dispatch0。通常push後のHEAD runs/checksは読み取り確認しPRへ記録する。main merge/force push/new PR/shutdownを行わない。古いチャットのshutdown依頼は再適用しない。

---

## 履歴：大容量動画の範囲取得再生（2026-10-15）

開始HEAD `267d4820a06c541d3d71b86155727ef2fcc538da`。branch/base/Draft PR5を維持。認証付きmanifest/range API、1MiB上限・revision・response検査、取消可能なnative独立カーソルstreamへ接続し、64MiB全体copyを通常再生から除去。詳細は[動画範囲再生](video-streaming.md)。

検証：Python276 PASS/138.384秒/skip0、Core208 PASS、Release32.19秒/0error/既存IL2104 2件。`video-range-native-03`73checks/30keys/skip0/12PNG全目視PASS。01はoffset証拠条件、02はthumbnail必須の誤前提で失敗、計2修正で03完走。ソース/設定不変・AI0・cleanup成功。実測70MiB/2秒、2TiB/長編/再生中の実更新/Narrator/多DPI/専用analyzerは未検証。実装SHAはこの節を追加したcommit（git log）を参照。

ユーザーが途中で追加要求した**シークバー・hover時刻とサムネイル・下部帯の左右隙間修正**へ続行する。FFmpeg fdのseek可能な既存ハンドルで生成動画の1秒frame取得を実測確認、追加依存なし。この節時点ではUI未実装、次節に確定結果を残す。

次の3手：1. シークバー/hoverフレームを実装・安全境界/生成色変化動画で検証、下部帯を端まで揃える。2. 狭幅・keyboard/Narrator/多DPIの未検証範囲を詰める。3. 未使用固定検索評価を追加し、検索精度と索引負荷の改善を続ける。CIはworkflow_dispatchのみ、実行0、私有素材/モデル変更0。過去のshutdown依頼は今回へ再適用しない。

---

## 履歴：CBZ/ZIPの読書位置・見開き方向を保存して再開（Windows続行）

開始HEAD **2c97844301bb19b84554454ffff1ba960534c550**。他AIの最新更新（動画thumbnail/再生、語別検索根拠UI、double-click実機PASS、v6評価/タグJSON照合/ID境界）とAGENTS/vision/両handoff/Issue4・PR5を確認し、clean・remote一致から続行。既存製品branch `feat/winui3-production-mvp-20261011`、base `feat/gui-framework-comparison-20261010`、[既存Draft PR5](https://github.com/jakymiku/Aredoko/pull/5)を維持。実装commit **9accf85e27dea0b3a39d3e49ceaf64161af3e59f**。文書込み最終HEADは本節の記録commit（`git log -1 --format=%H -- docs/codex-handoff.md`）を正とする。

### 実装と操作

- **本ごとの最後に読めたページと単ページ/RTL/LTRを自動保存・復元**。`reader_progress`をproduction SQLiteへ追加（既存DBでも初期化時に作成）。タグ・棚・お気に入りとは別tableで、元CBZ/ZIPは変更しない。保存は両表示ページのdecode成功後のみ。破損/取消/先行ページの読み込み中には新位置を書かない。
- **revisionが変わった本/範囲外の古い位置は先頭から**。以前の向きは保持。見開きはpair anchorへ正規化。「最初から開き直す」は明示的にcoverへ戻り、読めた場合にcoverを新位置として保存する。
- `GET/POST /api/library/reader/{id}/progress`。GETはHost/token、POSTはHost/token/Origin・既存body上限。strict revision/page/modeとpositive Int64 ID、scan guard、現manifest・active root/除外/リンク/索引stat/共通preview枠を検査して保存。stale POSTは409で新位置を上書きしない。root解除/除外中は取得・保存不可、再登録で以前の状態を保持。
- Coreの反射不要JSON解析・固定ID経路・JSON応答4KiB/MIME/受信長/取消/5秒deadline。保存中は操作を直列化（最大5秒後に失敗案内）。位置の取得失敗では閲覧を先頭から続けるが、既存の位置を自動上書きせず、実際の移動/方向変更または明示save retryまで保持。
- `ReaderProgressStatus`を追加。保存失敗でも読めた画像を維持し、設定/右クリックの「読書位置を保存し直す」（`ReaderSaveProgress`）からretry。読めないページでは「前に読めたページの位置を保持しています」と表示。検索選択・未保存タグ・閉じた後のopener focusを維持。[操作/API/検証](reader-progress.md)。

### 今回の実測

- **全Python271 PASS /158.203秒/skip0**。初回271は1failure（新しい固定API error3件の日本語mapping漏れ）。`ErrorText.cs`を修正して全271を再実行PASS。新progress7 PASS6.000秒（restart、別本分離、タグ/元bytes保全、入力/ID/Origin/token、real revision/stale write、root解除・除外、scan/worker busy、旧DB）。古い全264の数字を今回に流用していない。
- **Core188 PASS**（従来168＋progress20）。復元revision/短縮本/spread anchor/null、厳密JSON、固定route/認証/Origin、送信JSON、範囲外page、false save ackを確認。
- **最終Windows x64 SelfContained Release PASS28.99秒/0error/既存IL2104 2warnings（抑制なし）**。`--no-restore`。GUI02のbuildは30.20秒、以後のGUIコード変更なし。最後のbuild差分はAPI error対応表3件のみ。手動WinUI review/Python構文/diff PASS、専用WinUI analyzer未導入/未実行、AOT/installer検証なし。
- **reader-progress-native-02 PASS55 checks /実入力34/skip0/10PNG全個別目視/正常close2/cleanup warning0**。Light/Dark、700×620のRTL spread、開閉とappプロセス再起動での位置/向き復元、RTL右キー、明示cover、503保存失敗→手動retry、503取得失敗の旧位置保全→正常再open、破損spreadの旧位置保全、loading取消、未保存tag/BtnOpenBook focus復帰。生成bookを明示的に変更して**実rescan後のrevision reset**も確認。nativeのbackend自体は同じprocess、backend DB再初期化は別のPythonテストで確認。
- native01も構造assert55 PASS/keys34/skip0/10PNG/close2/warning0だが、目視で破損後の直前「保存しました」が紛らわしいと判断。1 fix-and-rerun cycleで上記の保存保持表示へ修正し02を確認。両runの全20PNGを個別目視。最終は02、旧01のUIを最終として扱わない。
- 生成5file中、book.cbzのみ各themeでrevision fixture用のtext entryを追加（readerを閉じてから実rescan）。他PNG/ZIP bytes・mtime/hashは不変、bookの最終状態も許可したexpected snapshotと一致。settings bytes不変、AI推論/worker0、private scan/変更/外部送信/モデル・依存取得/OS設定変更/CI dispatch0。3workflowはmanual-only。テストで印字されるDL案内は既存mockテストの出力で実downloadではない。

### 次の3手・継続境界

1. **64MiB超の動画再生**：revision/範囲/Host-token/枠/取消/seekを保つRange/stream設計と小さな縦切り。現動画は64MiBまでのmemory streamのまま。
2. **狭幅とキーボード/アクセシビリティ**：500px未満toolbar overflow、高DPI/Contrast/Narrator/全Tab、native titlebar X/Alt+F4、実JSON save/open pickerを独立batchで確認。今回55checksはこれらの合格を意味しない。
3. **検索評価を新入力で継続**：v6短alias/partial候補について新しい固定入力を検索前に凍結し、precision/correct-emptyを比較してから辞書/fallback方針を決める。今回モデル/順位/辞書の変更なし。

画像pageまたぎ/全画面/元解像度、読書zoom/scrollの保存・履歴UI/位置削除、複数同時clientの進捗競合、フォルダ本/OCR/VLM/Komga/動画音声索引、実素材1TB/数万件、実検索品質は未確認/未実装。以前の動画GUI70/thumbnail50/根拠30/double-click22は他AIの実測履歴として保全し、今回は全batch再実行していない。`test_hark_ui.py`とreader旧回帰modeは生成DBの位置だけを初期化するよう更新・構文確認（105/88の全batch再実行なし）。今回はシャットダウン依頼なし、実施しない。

---

## 履歴：Windowsネイティブ動画再生の実装・語別検索根拠のWinUI表示・サムネイル/動画実機検証（2026-10-14 Windows続行）

開始remote HEAD **b5b65966df51720c669f081d8773df130d09504b**（ローカル `bb8b154` をfast-forward同期し、別worktreeの未コミット変更を破棄せず保護して取り込み）。製品branch `feat/winui3-production-mvp-20261011`、base `feat/gui-framework-comparison-20261010`、[既存Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5)を継続。AGENTS→product-vision→agent-start→両handoff最新節・Issue #4・Draft PR #5を確認。旧branch・PR #6の再取り込みなし。

### 実装と保存commit

1. **68f73899c1b4193c57e55038ad5924323fa4672a** — Windows checkoutで`tests/fixtures/literal-related-v6.json`がautocrlfによりSHA256変化する問題を`.gitattributes`（`eol=lf`）で修正。`tests/test_video_previews.py`の子process出力テストをraw bytes出力に統一し、Windowsの開いた読み取りhandleによるrename拒否（`PermissionError`）を検証。
2. **836044c1a7900ba34a8ce4ff092902ce2f610cd8** / **fc40e660397ceefb981e513337ef513cdf036181** — `src/Aredoko.Core/Protocol.cs`に反射不要の`SearchEvidence`（`Direct`/`Related`/`Missing`、合計最大16語・1語最大64文字、サロゲートペア境界保護、`AllDirect`は`Direct.Length > 0 && Related.Length == 0 && Missing.Length == 0`）と`DescribeEvidence`（各区分4語＋「ほかN語」）を追加。`src/Aredoko.WinUI/MainPage.xaml.cs`の一覧/グリッド行で`row.Evidence is { AllDirect: false }`のとき`SearchEvidence<id>`として「入力語で一致：… / 関連語で一致：… / 一致なし：…」を表示（全語直接一致では余分な行を出さない）。`tools/compile_check_winui.py`のWindows UTF-8出力対応、`tools/test_image_viewer_ui.py`の専用読書window（`ArchiveReaderDialog`）待機修正および`--evidence-only` / `--video-and-evidence-only`検証モードを追加。
3. **ef1ca99a884a4093a757c949935c7110b68cfec7** — Windowsネイティブ動画再生の縦切り（`GET /api/library/video/<id>`、`VideoPlayerPolicy`、`ArchiveReaderClient.VideoAsync`、`VideoPlayerView`、`BtnOpenVideo`）を実装。active root・除外・present・symlink/reparse・open handle前後のstat一致・playlist偽装拒否（`#EXTM3U`/`[playlist]`/`<asx`）・64MiB上限・40秒deadline・共通2枠を維持し、メモリ上の`InMemoryRandomAccessStream`と`MediaSource`/`MediaPlayerElement`で再生（元動画のパス直接open・ロック・変更なし）。再生/一時停止（Space）、1秒戻る/進む（←/→）、音量増減・消音（M）、手動再試行、マウス静止2.5秒auto-hide、F10/Tab保持、Esc終了、未保存編集draftの保持、非対応codec/破損・503・409時の日本語案内を実装。

### 正確な検証結果

- **全Python 264 PASS / 155.322秒 / skip 0**（`NO_PROXY=127.0.0.1,localhost python -m unittest discover -s tests -q`）。Windows実機のFFmpeg/ffprobeによる`test_video_previews.py` **21 PASS / 9.694秒 / skip 0**（`/api/library/video/<id>`の認証・境界・playlist拒否・変更検知409を含む）と`test_error_text_coverage.py` PASSを含む。
- **Core 168 PASS**（`dotnet run --project tests/Aredoko.Core.Tests -c Release`、従来147＋`SearchEvidence` 9＋動画行viewer非対象1＋`VideoPlayerPolicy`/`VideoAsync` 11）。
- **Windows x64 SelfContained Release PASS**（`dotnet build src/Aredoko.WinUI/Aredoko.WinUI.csproj -c Release -p:Platform=x64 -p:SelfContained=true --no-restore`、0 error、既存IL2104 2 warnings抑制なし）。`python tools/compile_check_winui.py` **exit 0 / diagnostics 0**。
- **`viewer-doubleclick-01` PASS 22 checks / keys 16 / skip 0 / PNG 8全目視 / graceful close 2 / cleanup warnings 0**。Light/Darkで未選択状態の一覧サムネイルdouble-click（詳細pane展開によるレイアウト移動を含む）、グリッド、詳細プレビュー、未保存draft編集中の別作品double-clickキャンセル、CBZサムネイルからの専用読書ウィンドウ起動・Esc終了を確認。
- **`search-evidence-01` PASS 30 checks / keys 0 / skip 0 / PNG 6全目視 / graceful close 2 / cleanup warnings 0**。Light/Dark・1200×820と700×620狭幅で、全語直接一致（`a.png`）での`SearchEvidence`非表示、直接＋関連（`入力語で一致：東方 / 関連語で一致：巫女`）、関連のみ（`関連語で一致：東方、巫女`）、直接一致が関連一致より先に並ぶ順序、partial時の`一致なし：未知`、未保存draftの検索キャンセル保持、および`魔法"少女`・`C:\textures`タグ検索と`[`検索の0件（JSON配列構文の誤ヒット除去）を実機確認。
- **`video-native-01` PASS 50 checks / keys 0 / skip 0 / PNG 10全目視 / graceful close 2 / cleanup warnings 0**（中間`video-evidence-02` FAIL 5 checks / PNG 2、`03` FAIL 8 checks / PNG 3の履歴も[viewer-reader-validation.md](viewer-reader-validation.md)に保持）。Light/Dark・wide/narrowで720×480 SAR 8:9動画（`anamorphic.mp4`）の`DetailPreview` 4:3表示比率、`clip.mp4`/`clip.mkv`/`clip.webm`のリスト・グリッド「動画の先頭フレーム」、破損動画（`broken.mp4`）の「プレビューなし」、503単発fallbackと再接続後の再取得成功、検索切り替えによる遅延動画プレビューの取消、動画サムネイルdouble-clickで画像/本viewerが開かないこと、および語別検索根拠・引用符/バックスラッシュ/`[`検索まで完走確認。
- **`video-player-01` PASS 70 checks / keys 30 / skip 0 / PNG 12全目視 / graceful close 2 / cleanup warnings 0**。Light/Dark・1200×820と700×620狭幅で専用window（`VideoPlayerDialog`）の上下帯端dock・library無効化、生成MP4（H.264）とWMV（WMV2）の再生・一時停止・前後1秒seek・音量増減/消音、FFV1 MKV（FFmpeg先頭フレームは表示しつつWindows標準再生は非対応案内）と破損MP4の案内表示、503手動retry、409更新案内、背景Ctrl+S抑止、未保存タグdraftと`BtnOpenVideo` focus復帰、auto-hide/マウス移動再表示/非表示時Esc終了を実機確認。
- 全runで生成mediaのbytes/mtime/hash不変、settings bytes不変、AI推論/worker 0、正常close・cleanup warning 0。私物scan/変更/外部送信、model/依存取得、OS変更、**CI dispatch 0**（3 workflowすべてmanual `workflow_dispatch`のみを確認）。

### 次の3手と残課題

1. **検索評価の継続**：v6で見えた短alias/partialの参考候補を、新しい固定入力またはユーザー明示の小サンプルで比較してから辞書・fallbackの変更方針を決める。
2. **閲覧/動画の拡張**：64MiB超の大容量動画に対する安全なRange/stream再生設計、読書位置/設定保存、画像pageまたぎの設計検討。
3. **アクセシビリティ・周辺残gate**：500px未満toolbar overflow、高DPI/High Contrast/Narrator/Tab全順序、native titlebar X/Alt+F4、実JSON save/open picker、フォルダ本/OCR/VLM/Komgaは後続。

最終実装HEAD **ef1ca99a884a4093a757c949935c7110b68cfec7**。文書込み最終HEADは本節を導入したhandoff commit（`git log -1 --format=%H -- docs/codex-handoff.md`）を正とする。

---

## 履歴：固定評価v6・語ごとの検索根拠API（2026-10-14 夜）

開始HEAD **b59a4bc215dd8a165995a74a7b794b2c02b453a2**。製品branch `feat/winui3-production-mvp-20261011` /base `feat/gui-framework-comparison-20261010` /[既存Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5)を継続。開始git status clean、PRも同じHEAD・Draft/open/unmerged。AGENTS/製品vision/agent-start/両handoff最上段・Issue4/PR5を確認。旧branch/PR6を取り込んでいない。

### 実装と保存commit

1. **313b08200ac04a141b5623926c8bae1ef3edd90c** — v6評価セットを**初回検索前**にlocal commitで凍結（後で同じtreeをGitHubへ保存）。架空metadata/placeholder16件、24query、SHA256 `6ac38d61d0703eb9e3e5a69f9f2de78e198574313f9ebd29d9ebf73d1a30d9b3`。旧v3/v4/v5は不変。
2. **0c26633e9dbf935e2a8bbc9429c8882815430fb1** — 共有評価指標に実際のtop最大5件を分母とするPrecision@5を追加。literal evaluatorにv6と、no-answerをMRR/Recallから分離したcorrect_empty_rateを追加。CLIは過剰候補・false answerも表示。v6にはJSON構文の意図的な誤一致除去があるため、旧superset契約はv3/v4/v5に維持し、v6は新しい構造/diagnostic検証へ分離。
3. **34a35616a506af40c13b145efc32ba894b6c8e7b** — queryあり通常検索の各itemへ `search_evidence:{direct_words,related_words,missing_words}`。SQLと同じnormalization/alternativesで検索語を分類。最大16語のpartition、返却行のみで追加計算。match/partial/expansions/順位/filter/root/pagingは維持。queryなし/個別GET/AI検索にはこの新fieldを追加しない。保存tags/schema/model/vectorは変更なし。**WinUI/Coreのfield解析・表示は未実装**。

製品ビジョンの「曖昧な語から目的のローカル素材・作品に到達」「根拠を説明」を支えるAPI/評価基盤。今回は順位・辞書展開・partial fallbackを評価結果に合わせて調整していない。大きなUI刷新・実model導入・自動taggerは追加していない。[詳細と結果](literal-search-v6.md)。

### 測定した結果と限界

- 辞書ありv6は正解あり19queryのRecall@5/MRRが各1.000。ただし関連語4query Precision@5 **0.875**、過剰展開3query **0.833**、表記ゆれ2query **0.750**。正解なし5queryのcorrect_emptyは **3/5=0.600**。`潮騒 魔王`は1件、`雨 砂漠`は2件のpartial候補を返した。結果を保持し、100%の実素材品質やconfidenceと呼ばない。
- 辞書なし正規化のcorrect_emptyは4/5、旧LIKE参考も4/5だが、失敗caseは異なる（旧はJSON `[`の16件、現行辞書なしはpartial）。正解なしqrelsに参考partialを出すことをfalse answerとして測るが、既存の参考候補方針を直ちに不具合と断定しない。
- 同じ作者の辞書/query/qrelsであり開発寄り。初回実行前の凍結でも独立holdout/実素材/AI品質の証拠ではない。v6を見てretrievalを調整していない。旧評価の失敗やv3-v5を改変していない。

### このturnの検証

- 固定評価 **3 PASS0.132秒**、共有metrics **5 PASS0.157秒**。根拠 **6 PASS0.543秒**、文字検索 **10 PASS0.689秒**（生成50,001行2語 **0.219秒**、Linux単発）。
- **全Python263 PASS28.142秒/skip0**：`NO_PROXY=127.0.0.1,localhost python -m unittest discover -s tests -v`。新v6 diagnostic1＋根拠6を追加。HTTPのpartial/related/missing、語正規化/dedup、quote/backslash、root/kind/favorites適用、作品ごとに異なる欠落語、SQL判定との一致、source/保存metadata不変を確認。
- API追加後のv6を再評価し、追加前baseline JSONと**全72行・指標・順位・flagsが完全一致**。説明の追加をランキング改善として扱わない。CPU/生成fixtureのみ、実model/GPUなし。
- Python構文・diff/review PASS。追加/更新行のrelative link **9件 PASS**。**Windows/.NET/Core実行・Release/XAML/native GUI/analyzer/AOT/installerは未検証**。WinUI/Core sourceは今回は変更なし。静的に現clientのknown-field JSON解析を確認したが、実機互換確認の代用ではない。

### 次の3手と保存境界

1. **Windows gate**：Core/Releaseと、未完了のthumbnail double-click独立batch。動画の比率/取消/fallback/元bytes不変、quote/backslash検索、Light/Dark/narrowを確認。前回FAILとfix-and-rerun制限を保持。
2. **根拠のWinUI接続**：Coreの反射不要・bounded解析、欠落語/関連語経由の作品別表示を小さく追加しnative確認。現画面には新fieldが表示されると宣言しない。保存draft/旧API/keyboard/読み上げを維持。
3. **別の固定入力で検証**：v6で見えた短alias/partialの参考候補を、新入力や明示された小サンプルで比較してから変更方針を決める。高DPI/Contrast/Narrator/実JSON picker・読書位置/設定保存、フォルダ本/OCR/VLM/Komga/動画音声索引/installerは後続。

前回のpartial checkoutを継続しbinary9 assetの元treeを保全。ユーザーPCの未コミット状態は観測不可。3commitをexpected SHA付き非force fast-forwardで同じbranchへ保存、localもcanonical remote SHAへ同期。**CI dispatch0**、3workflowはmanual-only。main merge/force push/branch削除/比較generated変更、依存/model取得、私物scan/変更/外部送信、OS変更/shutdownなし。使用量%は取得不可。

最終実装HEAD **34a35616a506af40c13b145efc32ba894b6c8e7b**。文書込み最終HEADは本節を導入したhandoff commit（`git log -1 --format=%H -- docs/codex-handoff.md`）で、確定SHAをPR5/終了報告へ記録する。

---

## 履歴：タグ検索・動画比率・ID境界の修正（2026-10-14 続行）

開始HEAD **6a4d904a49fe288daf829a4d14ccd3efedc278dc**、製品branch `feat/winui3-production-mvp-20261011`、base `feat/gui-framework-comparison-20261010`、[既存Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5)を継続。開始時git statusはclean、PRも同じHEAD/Draft/open/unmerged。AGENTS→製品vision→agent-start→両handoff最新節、Issue #4/PR #5を再確認。旧branch・PR #6を取り込んでいない。

### 再現した不具合と実装

1. **d7845966ddac1a856d745e9fc75f9e4aa7f28aee** — 動画thumbnailの表示比率。720×480/SAR8:9を旧filterで取得すると256×171に歪んだ。SARを反映した表示寸法から256px以内へ縮小し、正方画素PNGへ変換。小さな映像・縦長・SAR未指定も確認。新しい`reset_sar` optionに依存せず、既存FFmpeg6.1.1で動作。元source・10秒/共有2枠/出力/cacheの上限を維持。
2. **10e2a0b41e4fa255babada48ab936a55f7915431** — 通常文字検索とAI検索の文字一致根拠は、実タグを使う共通`normalize_tags`へ変更。旧実装はJSON文字列を検索し、`魔法"少女`や`C:\textures`を見落とし、`[`だけでタグなし作品も一致した。JSONを復元し、値ごとに正規化/field区切りを入れる。引用符/backslash/Unicode escapeを正しく検索、保存JSON構文だけの一致を除外。SQLタグ復元はquery-local LRU4096件で再利用。関連語・partial・明示filterを維持し、AIのliteral_hits/literal_onlyも修正。保存tagsの書き換え、vector/model/順位統合方式の変更なし。
3. **3de22438cd5cd8c136bcf624944e51af57084e11** — 作品GET・混在batch更新・root除外・scan開始にも巨大IDでSQLite **OverflowError**になる経路を実再現。Catalog/ProductionCatalog/LibraryIndexでpositive Int64を事前検証し、invalid/bool/0/負数は400、範囲内unknown itemは404。batchを全体拒否し、部分更新・除外変更・scan job作成なし。locations offsetもSQLite整数範囲へ制限。デモAPIの共通catalogも回帰確認。

JSON構文による偶然のヒットを除去したため、`[`/`,`/引用符だけの検索は、**実際の名前/タグにその文字がある作品だけ**を返す。実タグ内の記号は引き続き検索可能。通常の日本語検索・NFKC/case/kana・16語AND・関連語/partial・保存metadataは保持する。[検索の詳細](related-terms.md)・[動画](video-thumbnails.md)・[API](api.md)。

### このturnで実行した検証

- **動画20 PASS /3.122秒/skip0**。生成MP4/MKV/WebMの既存3codec＋SAR8:9 720×480→256×192、SAR1:2 80×60→40×60、SAR2:1 16×12→32×12、縦長360×720→128×256、SAR未指定。元bytes/mtime不変、出力/dimension/deadline・pipe制約・cache・外部参照拒否の既存回帰も通過。
- **文字検索10 PASS /0.640秒**（新4）・**AI候補4 PASS /0.027秒**（新1）。タグJSON bytesを変えずquote/backslash/escaped Unicodeを検索、JSON構文の誤ヒット除去、tag跨ぎ防止、related/direct順・partial・kind/favorites、AI文字根拠/文字filterと同一vector順位を確認。生成50,001行2語検索 **0.193秒**（Linux単発、実素材/Windowsの速度・品質ではない）。
- **ID境界4 PASS /1.046秒**。実HTTPのproduction/demoでGET/update/excludes/scanの400、unknown最大IDの404、誤tokenの403、batch全体拒否・metadata/source/除外保全・job未作成・その後の正常updateを確認。
- 中間全Python **252 PASS /26.441秒/skip0**（最初の2修正後）。最終全Python **256 PASS /27.328秒/skip0**（ID修正後）：`NO_PROXY=127.0.0.1,localhost python -m unittest discover -s tests -v`。既存固定manifest v3/v4/v5の回帰も含む。新holdout/検索精度評価は追加していない。生成データ・CPU契約encoder/manual vectorsのみ、実model/GPUではない。
- Python構文・diff whitespace・手動差分review PASS。追加/更新行のrelative link **15件 PASS**。今回WinUI/Core sourceは変更なし。ただし**Windows/.NET/Core compile/run・Release/XAML/native GUI・専用analyzer/AOT/installerは未検証**。前回GUI/Release成績を今回のPython変更へ流用しない。

### 保存状態と未完了

前回のpartial checkoutを継続（binary9 assetはlocal未materialize、元tree SHAを保全）。ユーザーPCの未コミット状態は観測していない。小分けcommitをGitHub APIで作り、expected SHA付き非force fast-forwardで同じbranchへ保存し、localもcanonical SHAへ同期。main merge、force push、branch削除、比較generated変更なし。実際の3workflowはmanual `workflow_dispatch`のみ。**CI dispatch0**、依存/model取得・私物scan/変更/外部送信・OS変更・shutdownなし。使用量%は取得不可。

最終実装HEAD **3de22438cd5cd8c136bcf624944e51af57084e11**。文書込み最終HEADは本節を導入したhandoff commit（`git log -1 --format=%H -- docs/codex-handoff.md`）で、確定SHAをPR #5説明/終了報告へ記録する。

### 次の3手

1. **Windows最初のgate**：Core/Release buildと、未完了のlist/grid/詳細thumbnail double-clickの独立実機batch。dirty/取消/選択/open/focusを確認。前回のFAILとfix-and-rerun制限を保全する。
2. **動画・文字検索のnative回帰**：生成3形式＋SAR付き動画の比率、Light/Dark/narrow、取消/503/fallback、元bytes/mtime不変。quote/backslash/Unicodeタグの通常検索・AI根拠/文字filterを確認。seek可能な安全入力・512MiB超対応・native playbackは後続の独立実装。
3. **固定評価・閲覧残gate**：新しいholdoutで関連語の過剰展開/取りこぼしを測定し、今回の再現テストを実素材の品質保証へ広げない。高DPI/Contrast/Narrator/Tab・極狭幅・実JSON picker・読書位置保存は未完了。フォルダ本/OCR/VLM/Komga/動画音声索引/installer・全体visual刷新は別段階。

---

## 履歴：動画thumbnailの基盤・プレビューAPIの安定化（2026-10-14、Linux続行）

開始HEAD **bb8b154155232448e420dc4864bf37d73d6a012d**。製品branch `feat/winui3-production-mvp-20261011`、base `feat/gui-framework-comparison-20261010`、[既存Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5)を継続。Issue #4、製品branchのAGENTS→product-vision→agent-start→両handoff最新節→spec/resource policyを確認。PR #6の再取り込みなし。

### 実装とコミット

1. **5ad7a23af4facb545e8333d312c0831955413726** — 動画の先頭frameを既存preview APIへ追加。既存PATHのffmpeg/ffprobeのみ、登録/active root・除外・present・索引size/mtime・reparse/link検査後の読み取りhandleをstdinへ渡す。元pathはchild argvへ渡さずshellなし、pipe-only protocol/限定demuxer、FFREPORT除去。10秒（probe+frame）・共有2枠・512MiB入力/16M画素・各1thread・PNG256px/512KiB・probe16KiB・memory LRU32枚。cache hitもsource/rootを検査し、取得後の変更/差し替えを拒否。元動画/展開/PNG cacheのdisk保存なし。
2. **79aa08069a3849bc886e99f726e66b384afb7ada** — WinUIの既存list/grid/詳細thumbnail serviceへvideoを追加し、成功時「動画の先頭フレーム」。既存decode/取消/LRUを再利用。画像/本のdouble-clickやviewer対象を動画へ拡張していない。**ソース接続のみ、Windows build/native未検証**。
3. **9eb204fa7e2d250703de32167e4b3b82d2c98486** — preview routeを正規形ASCII ID・1..Int64.Max・query/path追加禁止へ統一。不正URLは400 `Invalid item`。旧sourceで`read(2**63)`のSQLite **OverflowError**を実際に再現した。内部readerにも範囲検証、HTTPの巨大値/負数/先頭0/nested/query/Unicode等の回帰追加。

検索順位・関連語辞書・model/profile/vector・タグ/棚/設定schemaは変更なし。作品/画像/動画/音楽/素材の横断検索ビジョンを維持。大きな見た目の刷新は前倒ししない。詳細：[video-thumbnails.md](video-thumbnails.md)、[API](api.md)。

### このturnで実行した検証

- Linux/Python3.12.14／既存FFmpeg・ffprobe **6.1.1**。動画 **19 PASS / 2.333秒 / skip0**（最終focused、sentinel回帰込み）。生成MP4(MPEG-4/faststart)、MKV(FFV1)、WebM(VP8)を実decodeし、PNGの赤い先頭pixel・256×144・元bytes/mtime/ファイル一覧不変を検証。偽playlistに対するloopback sentinelのHTTP要求0。
- previewは追加前 **12 PASS0.926秒**、ID修正後 **14 PASS1.462秒**。reader **16 PASS2.605秒**。動画境界テストはauth/no-store/404/503、解除/除外/stale/link/欠損、変更/差し替え、cache/PNG/dimension/deadline、ツール不在、FFREPORT非継承を含む。時間/出力超過は小さな実Python childを停止・回収して確認。
- 最終全体：`NO_PROXY=127.0.0.1,localhost python -m unittest discover -s tests -v` **246 PASS / 33.085秒 / skip0**。新19＋preview新2、既存225。生成fixtureのみ。Python構文・diff whitespace・手動差分reviewを確認。文書の追加・更新行に含まれるrelative link **16件 PASS**。
- **今回.NET/Core実行、WinUI C# compile/XAML、Windows x64 Release/native GUI/GPUは未実行**。Linuxにdotnet/Windowsなし、依存を取得していない。前回Core147/Release/画像110・reader88は歴史上の証拠で、今回変更の合格へ流用しない。専用analyzer/AOT/installerも未検証。

### 作業環境と保存

通常cloneは認証不可だったため、接続済みGitHubから固定SHA treeと223 text blobを復元し、各blob SHAとtree/開始commitを照合。9個のbinary app assetはconnectorが取得不可でlocalにmaterializeせず、元tree SHAを保全したpartial checkout。**ユーザーPC側の未コミット変更・実環境は観測していない**。このlocal checkoutの開始/終了作業treeは変更なし（文書保存前は実装commit時点でclean）。APIから小さな3commitを作成し、expected SHA付き**非forceのfast-forward**で同じbranchへ保存、localもcanonical remote SHAへ同期した。binary assets/比較generated/古いbranchを変更・削除していない。

**CI dispatch0**。実際の3workflowはすべてmanual `workflow_dispatch`のみ、trigger変更なし。私物scan/変更/外部送信、model/dependency取得、OS変更なし。以前の一時的なshutdown許可を再適用していない。使用量%はこの環境から観測できず、5%到達を宣言しない。

### 限界・次の3手

1. **Windowsの最初のgate**：Core/Release buildと、最優先で残っている画像/本thumbnail double-clickの独立batch。前回FAIL履歴と2 fix-and-rerun上限の記録を維持し、list/grid/詳細の選択・dirty取消・openerを確認。今回fallback実装は変更していない。
2. **生成動画native gate**：既存Windows ffmpeg/ffprobeでMP4/MKV/WebMの取得、list/grid/詳細、Light/Dark/narrow、fallback/503、取消/別selection、元bytes/mtime不変、ツール不在を確認。512MiB超/末尾moov等は現状fallback。seek可能な安全入力・大動画対応やnative playbackは、その後の独立した小さな変更へ。
3. **閲覧・検索品質の残gate**：高DPI/Contrast/Narrator/Tab全順序、極狭幅overflow、native X/Alt+F4、実JSON picker、読書位置/設定保存。関連語の過剰展開は新しい固定holdoutで測定。1TB/数万件・実素材の精度は未評価。フォルダ本/OCR/VLM/Komga/動画音声内容索引は後続。

512MiB入力上限・seek不可stdinは今回の小さな実装の制限であり製品の長期対応目標ではない。frameは代表シーンでなく最初のdecode frame。ネイティブ総heap/CPU/帯域の厳密な上限やsandboxは保証しない。clientが閉じてもbackendは最大deadlineまで処理を続ける。

**最終実装HEAD：9eb204fa7e2d250703de32167e4b3b82d2c98486**。文書込み最終HEADは本節を導入したhandoff commit（`git log -1 --format=%H -- docs/codex-handoff.md`）；その確定SHAをPR #5説明と終了報告にも記録する。Draft/base/unmergedを維持する。

---

# Aredoko — GPTチャットへの最新引継ぎ

## 履歴：画像・読書ビューアの共通ウィンドウ（2026-10-14）

開始HEAD `fc38394ec346f238c937f0dd7980d1c96af0d6fb`、実装commit **ed943b7703718085d05004c99dcc3393d1bf06df**。製品branch `feat/winui3-production-mvp-20261011`、base `feat/gui-framework-comparison-20261010`、[既存Draft PR5](https://github.com/jakymiku/Aredoko/pull/5)を継続。最終HEADはGit/PRを正とする。

### できること

- 詳細の「画像を大きく表示」「本を開く」から**共通の専用WinUIウィンドウ**を開く。Windowsの上部タイトルバーを残し、ContentDialogの太い外枠/余白を除いた。暗い画像canvasが左右・下端まで広がり、上下の不透明な操作バーは端に接する。Honeyviewの画像中心の操作感を参考にし、アプリ全体の刷新はしていない。
- マウス静止2.5秒で操作バーが隠れ、移動で再表示。Tab/F10はkeyboard操作部を保持、失敗時も操作可能。Escは操作部が隠れた状態でも閉じる。ズーム1–4倍、fit、scroll、手動retry。
- 画像は**現在の検索結果ページ内**だけを←/→で順に閲覧。既存root/棚/query/AI順序を保ち、端で停止。背景の選択/タグdraftを変えず閉じると元の詳細・openerへ戻る。loading中の移動/閉じるはcancelと単一load loopで古い応答を排除。
- CBZ/ZIPも同じ外観。設定アイコン/右クリックから**単ページ・見開き右→左・左→右**。表紙は単独、以降2ページずつ、余った最後は単独。RTLは左キーが次、LTR/単ページは右キーが次。設定は閲覧session内のみ、永続化なし。2枚のdecodeを完了してからまとめて表示し、失敗時は双方を消す。
- 閲覧中は所有libraryウィンドウを無効化し、閉じると元のenabled状態と編集draftを復帰。owner設定/resize/closeはアプリ自身のWindowだけ。既存loopback認証、active root/除外/reparse/索引stat、CBZ manifest revision、画像8MiB/16M画素/派生長辺2048px/40秒body deadlineを維持。元画像1:1表示やprivate source直接openではない。

### 正確な検証結果

- **Core147 PASS**（画像HTTP/policy・結果snapshot・見開き12・thumbnail click tracker7を含む）。Python preview12 PASS2.363秒、reader16 PASS8.584秒。backend未変更、全Python225/関連語15/旧folder50・reader105の全batchは今回は再実行していない。
- **最終Windows x64 SelfContained Release PASS25.47秒**、0error、既存IL2104 2warnings（抑制なし）。`--no-restore`。app refsのWinUI API確認、手動WinUI review、Python構文/diff確認。専用WinUI analyzer未導入/未実行、AOT/MSIX配布試験ではない。日本語resource化は既存MVPと同じく未完了。
- 専用window画像最終 **PASS 110 checks / keys 56 / skip 0 / PNG 24 / graceful close 2 / cleanup warnings 0**。Light/Dark、1200×820/700×620、上下帯の端/中央fitのUIA実寸、library無効化、左右/端/filtered singleton/破損、zoom/scroll、503retry、cancel/late response、dirtyとCtrl+S/F抑止、Esc/opener、auto-hide/mouse/F10、単ページCBZ入口。全24PNGを個別目視。
- 専用window読書最終 **PASS 88 checks / keys 24 / skip 0 / PNG 24 / graceful close 2 / cleanup warnings 0**。Light/Darkのsingle/RTL/LTRの番号・実物理順、cover/端/unpaired、settings/実右click、zoom/scroll/reset、corrupt pair消去/skip、503retry、**注入409**によるmanifest無効化と直接Reopen、遅延close→別本、dirty/Ctrl+S/Esc/focus、auto-hide/F10、上下帯の端/library無効化。全24PNGを個別目視。このbatchでは元bookを書換える実revision/rescanをしていない（Python reader16/前回native履歴と区別）。
- 最初の専用window画像runはFAIL30/5PNG/keys8/skip0/owned termination fallback1。閉じたviewer HWNDに対するwait-forでrunnerが停止。所有window inventoryで終了を確認してmain HWNDへ戻す修正後、画像02でPASS。全失敗PNGも目視。古いmodal overlay/readerのPASSを最終windowの証拠へ流用しない。[全run履歴と限界](viewer-reader-validation.md)。
- 最終runで生成4/5file bytes/mtime/hash、settings bytes不変、AI推論/worker0、正常close2ずつ・warning0。ユーザー素材scan/変更/外部送信、model/dependency取得、GPU/OS設定変更、CI dispatch0。添付参考画像/PNG/DB/設定/modelはGitへ含めない。3workflowはmanual-only。

専用window読書01はFAIL12/1PNG/keys1/skip0/fallback1。操作帯はIDのみでUIA peerが生成されず停止し、アクセシブル名を付けて02で検証した。手動レビューで一覧全体のdouble-tap旧選択入口を除き、thumbnail自身のIDを持つ経路だけを残した。画像02以後の変更はこの未検証入口の限定とreader帯Nameのみで、画像button/viewport実装は変更なし。専用windowの修正再実行は計2cycleで終了。

### 未完了と次の3手

1. **サムネイルのdouble-click実機確認が最優先**。list/grid/詳細のDoubleTappedと、OS既存interval/距離をread-only取得するPointerPressed/Core trackerを追加済み。最初の3runはFAIL2ずつ（viewer未open、foreground guard、viewer未open）。初回選択でthumbnailのlayoutが動く観測への追加fallbackはCore/buildのみ、最終GUI未検証。通常button入口は上記で確認済み。WinUI UI testing skillの最大2 fix-and-rerun cyclesに到達したため、このfeatureの実機再実行は本turnで停止。別のwindow/spread検証にdouble-clickを混ぜて回避していない。前面化auto-review拒否はユーザーがtest Aredoko限定を明示許可して解消済み。
2. **動画thumbnailの小さな縦切り**。既存PATHのffmpeg/ffprobe（存在のみ確認、起動/decode未確認）を生成videoで検証し、時間/並列/出力/cacheを制限した代表frame取得を実装。次にWindows native playback。どちらも今は未実装。
3. **閲覧/アクセシビリティの残gate**。500px未満の極狭幅でtoolbar overflow、高DPI/High Contrast/Narrator/全Tab順序/修飾左右、横長・透明・全codec、native titlebar X/Alt+F4によるclose、実JSON save/open picker、読書位置/設定保存、画像pageまたぎ・全画面・元解像度/大画像。現在の左右送りは当該結果pageのみ、GIFは静止、SVG/PDF対象外。

`tools/test_hark_ui.py`も専用reader windowへのtarget切替/closeをソース更新・py_compile確認。ただし旧105checkの全batchを再実行したとは宣言しない。大規模1TB/数万件・実素材検索品質・confidence校正は未評価。検索model/順位は今回未変更、自動候補境界は正解率ではない。全文OCR/動画音声索引/フォルダ本/Komga/全体visual刷新/installerは後続。

ユーザーの今回の依頼により、このcheckpointをGitHubへ保存した後に通常シャットダウンを実施する。将来turnにシャットダウン許可を引き継がない。強制アプリ終了は要求していない。

---

## 履歴：画像ビューア・検索結果内の左右送り（2026-10-14）

開始HEAD **fc38394ec346f238c937f0dd7980d1c96af0d6fb**。製品branch `feat/winui3-production-mvp-20261011` / base `feat/gui-framework-comparison-20261010` /既存Draft PR5を継続。実装commit **ed943b7703718085d05004c99dcc3393d1bf06df**（後続の記録commitで固定する）。最終HEADはGit/PRを正とする。

### 実装と使い方

- 詳細の **「画像を大きく表示」** からネイティブmodalを開く。画像中心の暗いcanvas、中央fit、ファイル名、画像位置、compact icon操作バーに整えた。Honeyviewは見た目の参考で、同機能・形式対応を再現したという意味ではない。[画像ビューア](image-viewer.md)。
- **← / → と前後buttonで、現在表示中の検索結果ページの画像だけを検索順で送る**。本/video/非対応/未接続を除外し、root/棚/query/AI候補groupなど既存の絞り込みと順位を維持。最初/最後は止まり循環しない。別pageを自動取得しない。broken imageは表示して手動で次へ進める。
- `ImageViewerSequence` がID/タイトル/順序をsnapshot化。MainPageの選択itemと編集draftは変更せず、閉じると元の詳細/openerへ復帰。ズーム1–4倍、縮小/拡大/fit、scroll、Esc/閉じる、手動retryを実装。100%は画面fit基準で元画像の1:1 pixel表示ではない。
- ScrollViewerの左右キー消費に先行するmodalの `PreviewKeyDown` で未修飾左右を処理。Ctrl/Shift/Alt/Win付き左右は画像送りしない（除外条件はソース確認、実入力での修飾左右は未検証）。loading中も移動可能。先行要求をcancelし、version比較と**単一load/decode loop**で最新targetだけを表示。旧画像は移動/失敗時に消去。
- 既存loopback session/preview安全境界を再利用。fixed numeric item ID、画像MIME、Content-Length/stream一致、8MiB、40秒body deadline、16M画素、派生PNG長辺2048px。active root/除外/reparse/索引statのbackend検査を維持。privateファイル直接open/保存/変換なし。画像previewは索引更新検査であり、CBZのfrozen manifest revision protocolを新設したわけではない。

### 実測と検証範囲

- **Core128 checks PASS**。新しい画像policy/認証固定route/受信上限・不正MIME・切断/取消に加え、snapshot順序、範囲外選択拒否、端の停止、戻る、欠損・非画像除外、重複除去を確認。先行画像基本形119から追加9。
- **Python preview12 tests PASS /2.363秒**。backendは今回未変更。全Python225、reader API16/関連語15、旧folder50/reader105を今回は再実行していない。旧実測は[前回記録](native-folder-reader-validation.md)の履歴として維持。
- **最終Windows x64 SelfContained Release PASS30.66秒 /0error/既存IL2104 2warnings（抑制なし）**。`--no-restore`。app refsのScrollViewer/KeyboardAccelerator/PreviewKeyDown/InputKeyboardSource/BitmapImage APIとGalleryを確認。構文/diff/手動WinUI review通過。専用WinUI analyzer未導入/未実行。hardcoded日本語は既存MVPに準じ、国際化は未完了。AOT/MSIX配布試験ではない。
- **image-viewer-navigation-03 PASS88 checks /実入力30/skip0/20PNG全個別目視**。Light/Dark、1200×820/700×620、左右（viewport/Close focus）、端、破損から戻る、1件query scope、中央fitの実寸、zoom/scroll、retry/503、loading移動cancel/閉じるcancel、late response排除、dirty保持、Ctrl+S/F background抑止、Esc/opener復帰、単一page CBZ入口回帰。正常close2、cleanup warnings 0。物理キーskipはこのrunの値を正とする。
- 失敗/中間履歴：基本形native01 **FAIL15/3PNG/実入力0/skip3**（Windows foreground拒否後、runnerのopener focus要求で停止）；基本形native02 **PASS56/12PNG/実入力14/skip0/owned termination fallback2**。追加navigation01 **FAIL17/2PNG/実入力1/skip0/fallback1**（RightがScrollViewerで消費；footer案内切れも目視）；navigation02 **PASS86/20PNG/実入力30/skip0/正常close2/warning0**（画像が左寄りなので中央fitを追加）。すべてのsaved PNGを個別目視。基本形3+12、追加2+20+20＝**57PNG**。画像送りの追加要求は別の新機能batchとして実施、最後は2度目の修正後runで終了。以後のGUI変更を自動保証しない。
- 全runでgenerated4fileのbytes/mtime/hash不変。最終settings bytes不変、AI inference/worker0。ユーザー素材scan/変更/外部送信、model/依存取得、GPU/OS設定変更、CI dispatch0。保存PNG/DB/設定/モデルはGit対象外。

### 残る境界と次の3手

1. **動画thumbnail**：既存PATHのffmpeg/ffprobe利用可否を実行確認し、生成videoだけで時間/並列/出力/cacheを制限する代表frame取得を実装。元動画を変更しない。無断導入しない。
2. **動画再生の基本形**：native play/pause/seek/volumeと非対応案内、生成videoの形式別検証。現時点では未実装。
3. **閲覧の残gateを小分けに**：画像送りのpageまたぎ・全画面・元解像度/大画像対応の設計、画像viewer高DPI/Contrast/Narrator/Tab/修飾左右/横長・透明・各形式確認、reader zoom/直接Reopen/実JSON pickerなど。現在の左右送りは当該page内に限定。GIF等は静止表示、SVG/PDFは入口対象外。

大規模1TB/数万件負荷、実素材品質、検索confidence校正は未評価。モデル/AI検索順位変更なし。自動候補境界は正解率ではない。全文OCR/動画音声内容索引/フォルダ本/Komga/全体のvisual刷新/installerは後続。

---

## 最新：フォルダ設定gate通過・読書画面の修正と実機確認（2026-10-14 続き）

開始HEAD **ff87f99a35f4027dc172d9d3d1e0f837a1a22038**。AGENTS/vision/design/両handoff/Issue4/既存Draft PR5を確認。同じ製品branch/baseを継続。実装commit **83851e1b7582772695786ee1376c046cb1ed1963**。続く記録commitでこのSHAを保存し、最終HEADはGit/PRを正とする。

### できるようになったことと修正

- **folder-finish-03 50 checks PASS**。Lightのsidebar右クリック→当該root設定、root切替時の空棚一括適用checkbox解除、初期棚の実表示、解除root自身の除外prefillと再登録後一致、タグ・棚保持まで確認。Light/Darkのfolder検索・全体復帰・AI上位/参考/全候補・手動境界・dirty取消/破棄・list/grid・700×620狭幅も完走。実モデル品質の評価ではない。このbatchはreader修正より前。
- 読書を狭幅で閉じると詳細paneが隠れたため、**元と同じ選択itemの詳細paneとopener focusを復帰**。未保存のタグを保存/破棄せず保持する。readerのGridを有限高さ＋先頭star rowへ変更し、画像だけを伸縮、wideで切れた再試行/再openを表示内へ収める。
- **reader-followup-03 105 checks PASS /実入力14/skip0**。Light/DarkでCBZ自然順（page2赤→page10青→page20緑）、最初/最後の前後disabled、ZIP破損ページの旧画像消去/スキップ、503手動retry、生成CBZ更新による実409→閉じる/rescan/再openで4ページ、遅延要求cancel→別本へのlate response混入防止、タグdraft保持とEsc/opener focus、modal内Ctrl+S/Ctrl+Fを確認。
- 関連語のLight/Dark保存・busy入力disable/close延期・再起動保持、direct-before-related理由、partial説明、17語の日本語errorも通過。**JSON save/open pickerは今回操作していない**。辞書と検索順位/model/worker/APIは変更なし。
- runnerはowned popupを優先し、expired auxiliaryを記録、window/tree証拠を保存。検索は既存300ms debounceのrender後にready/inspectしてから明示button操作する。失効したpeerは画面更新後のAutomationIdで取り直す。

### ローカル検証・失敗履歴・限界

- **Reader API16 PASS8.007秒 /関連語15 PASS10.211秒 /Core107 PASS**（Coreは既存Releaseのno-build）。全Python225やfolder/group14は今回は再実行していない。backend/Core/model未変更のため前回のfull成績を今回へ移さない。
- **x64 SelfContained Release PASS27.16秒/0error/既存IL2104 2warnings、抑制なし**。app refsのGrid/IsPaneOpen/Control.Focus API、Gallery ContentDialog例、layout-reviewを確認。Python構文・diff check・手動WinUI差分レビューPASS。専用WinUI analyzer未導入/未実行、AOT/installer未確認。
- folder01 **FAIL24/6PNG/正常close1**（menu候補判定；初回候補数の記録なし）、02 **FAIL37/7PNG/正常close2**（Light設定完走後、Dark検索buttonのpeer失効）、03 **PASS50/10PNG/正常close2**。**計23PNGを全て個別目視**。補助popupに同じmenuが重複していたとは初回の証拠だけで断定しない。
- reader01 **FAIL1/0PNG/アプリ未起動**（query helperのインデント誤りでowned HWND取得前のreadyを実行）。02 **FAIL40/9PNG全目視/実入力3/owned termination fallback1**（狭幅readerを閉じるとTxtTagsが非表示；タグ削除ではない。wide下部actionの切れも目視）。03 **PASS105/24PNG全目視/正常close2/cleanup warning0**。**reader計33PNG、今回全体56PNGを全て個別目視**。前回失敗と旧AppX dependencyの履歴も保持。
- 両batchともUIスキルの **“Maximum two fix-and-rerun cycles”** の範囲で終了。最後のrunはPASS。追加GUI再実行なし。readerの最初/最後・破損/503/409・cancel後とLight/Darkを目視し、操作/状態/閉じるが表示内に収まることを確認。辞書のnarrow bodyは意図した縦scroll、footer Closeを保持。
- **実DPI96 /High Contrast off**。High DPI/Contrast/Narrator/Tab全順序/reader zoomと直接Reopen button/元解像度品質・大規模負荷は未検証。今回は小さな生成素材の接続/状態確認で検索精度の証拠ではない。
- folder全3runで生成9file bytes/mtime/hash不変、03終端でsettings bytes不変。reader全3runでsource境界確認、03では明示した生成book.cbzの4ページ化/テーマ前resetのみ許可、他PNG/ZIP bytes/mtime/hashとsettings bytes不変。AI推論/worker0、ユーザー素材scan/変更/外部送信、model DL/依存導入/OS変更/CI dispatch0。最終owned appなし。3workflow manual-only、Draft PR5/base未マージ。

### 次の3手

1. **次の機能追加：単体画像ビューアの基本形**。現在はthumbnail/高さ160の詳細previewのみ。既存reader/codecを再利用し、大きな表示・zoom/scroll・Esc・タグdraftとopener focus保持を生成画像で検証。registered active root/revision/読み取り上限を維持。基本形を次の実装枠の目標にし、完了日を確約しない。
2. **動画thumbnail**。PATH上のffmpeg/ffprobeを確認済み（起動/decodeは未検証、個人環境の絶対パスは保存しない）。明示登録videoだけから代表frameを取得し、時間/並列数/出力/cacheを制限、元videoを変更しない。新規導入や本編AI解析はこの計画の実装済み機能ではない。
3. **動画再生の基本形**。Windows nativeの再生/pause/seek/volumeと非対応案内を実装・形式ごとに生成videoで確認する段階。実動画への無断アクセス・codec/OS設定の無断変更を行わない。

継続gate：辞書の実JSON save/open picker（export count/import merge・replace/cancel・invalid・上限）、reader直接Reopen/zoom/Tab、検索方法/AI profile回帰、高DPI/Contrast/Narrator、新しい固定入力での検索境界/関連語の評価は未完了として保持。フォルダ本/OCR/VLM/Komga・将来ビジュアル刷新は別段階。

---

## 最新：フォルダGUI確認・設定状態の修正（2026-10-14、追加確認は一部残る）

開始HEAD **e4a7bc98631c845862f4f60b38b90c20f3b6d688**。Issue4/既存Draft PR5・AGENTS/両vision/両handoffを確認し、同じ製品作業ブランチを継続。実装commit **d29d3fe340cca937ae9dc3a3d7f27728482c5e14**。続く記録commitでこのSHAを保存し、最終HEADはGit/PRを正とする。

### 今回確認できたことと修正

- 新batch `folder-resume-01` **46 checks PASS**。生成9 PNG/隔離DB・settings/CPU契約encoderのみ。最終flat sidebarからfolder検索、全体へ戻る、AI画像・表紙の上位3/参考3/全6とmanual境界、未保存取消/破棄、Light/Dark・list/grid・700×620狭幅、およびLightで既存/新棚への登録、空棚への明示適用、解除/再登録とタグ・棚復元を通過。実モデルの精度評価ではない。
- 目視と手動コードレビューで、登録直後に棚choicesを作り直して「棚なし」へ表示が戻る問題を発見。**棚choices更新後に登録rootを選び直す**順序へ修正。修正後の02/03は新棚「背景」の実表示まで確認。
- 再登録prefillが別のactive rootの除外設定を使う問題を修正し、**解除root自身の保存済み除外を表示**する。root変更で**空棚一括適用checkboxを解除**し、別rootへ操作を引き継がない。これら2点はsource/Release確認、追加GUI assertionsは未到達。
- 追加runnerはsidebar右クリック→当該root設定、初期棚表示、root変更のcheckbox解除、再登録前後の除外一致を検証する。既定の保護除外を含む全リストを期待値にする。

### 検証結果と限界

- `python -m unittest discover -s tests -p test_folder_search.py -v` **11 PASS /5.789秒**、`test_ai_result_groups.py` **3 PASS /0.240秒**、`dotnet run --project tests/Aredoko.Core.Tests -c Release` **107 PASS**。変更はWinUI/runnerでPython実装・model・rank未変更のため全225件は今回再実行していない（前回225 PASSは履歴）。
- `dotnet build src/Aredoko.WinUI/Aredoko.WinUI.csproj -c Release -p:Platform=x64 -p:SelfContained=true --no-restore` **PASS35.25秒/0error/既存IL2104 2warnings、抑制なし**。手動差分レビュー・Python構文・git diff check PASS。専用WinUI analyzer未導入/未実行。AOT/installer未確認。
- 01 **PASS46/10PNG/正常close2**、02 **全体FAIL24/6PNG/正常close1**、03 **全体FAIL24/6PNG/正常close1**。**22PNGを全て個別目視**。01のLight/Dark、後続Lightの候補/grid/狭幅・棚状態と失敗時context menuを確認。modalの設定は意図した縦scrollでfooter Closeを保つ。名前/類似度は色以外でも区別し、raw scoreを正解率にしない。高DPI/High Contrast/Narrator/physical keyboardは未検証。
- 02はright-click後に列挙された補助HWNDのUIA inspectで`AppNotFoundException`。main/PopupHostへ対象を絞って03でも同じ失敗（missing HWNDはmainと異なり、失敗画像には別の有効menu popupが見える）。**メニューから設定へ入る操作は未完了**。最後に当該エラーの補助HWNDだけを記録して除外するrunner修正を加えたが、これ以降のGUI再実行はしていない。mainの不達・他CLI error・menuが見つからない場合は引き続きFAILとする。
- インストール済み`winui-ui-testing/SKILL.md`の **“Maximum two fix-and-rerun cycles”** に従って03で停止。01の成功を、追加修正の未到達assertionや全体GUIの成功へ流用しない。前回native01/02/03のfailed evidenceも保持。
- 全3runで生成9 sourceのbytes/mtime/hash不変。01ではsettings bytes不変も終端で確認、02/03は終端assertion未到達。cleanup warning0、正常終了後に所有appなし。個人素材scan/変更/外部送信、model DL、GPU/Laya、依存追加、OS変更、CI dispatchなし。3workflow manual-only、既存Draft/base未マージ。

### 次の3手

1. 最終runnerで新native batch：有効context menuからroot設定へ入る、root変更の空棚適用checkbox解除、再登録時の当該root除外・棚・タグ一致を確認。FAILED補助HWND記録と既定除外の期待値を保持。
2. Hark追加reader/関連語の残gate：17語日本語error、Light/Dark辞書・JSON picker、CBZ/ZIP readerのページ/破損/retry/revision/late-response/dirty/keyboard。今回のfolder Dark確認と辞書/reader Darkは別。
3. 検索方法/AI profile回帰と固定の新入力で候補境界の取りこぼし評価。自動区切りをconfidence/キャラ精度として扱わず、OCR/VLM・フォルダ本・Komgaは別工程。

---

## 最新：フォルダ検索・棚設定・登録解除・AI候補の表示分離（2026-10-13、GUI部分確認）

開始HEAD **35cd6f43f3e0ba7c2232d94a15ec271be0a7b189**。既存Draft PR5/baseを継続。実装・テストcommit: **fe92117354b170eacde30b26a92ec18527fef5a1**。この後の文書commitでSHAを記録し、最終HEADはGit/PRを正とする。ユーザーから実ファイルのキャラ名・NSFW語・画像内文字でヒットした報告あり。これはユーザー観察で今回の精度評価ではない。添付画像/私物/パスをテスト・保存・外部送信していない。

### 追加した実装

- 通常検索`root_id`をcount/順位/ページング/関連語/partialより前に適用。未指定は全体、登録フォルダの全サブフォルダを含む。未知/解除済み/不正IDは400、全体へfallbackしない。GUIの選択rootはAIのsaved scopeと積集合（空/非交差を保持）。AI対象・索引上限10,000・モデルnamespaceは既存のまま。
- rootの`default_shelf`/`enabled`を追加移行（旧rootは棚なし/enabled=1）。登録時に既存棚か新規棚を選択。初期棚は新しく作るitemだけへ適用、再scan/再起動は個別棚の変更・解除/タグ/お気に入りを上書きしない。選択rootの初期棚編集と、**明示的なcheckboxで既存の棚未設定present itemに一度適用**するAPI/UIも追加。この操作は個別に空へ戻した棚を含むことを表示し、既存の非空棚や他rootは変更しない。
- 登録解除は`enabled=0`。元ファイル、location/item、整理情報、vectorは削除しない。通常/AI/preview/readerから外し、scan中は409。解除済みルートの再登録は同じroot/itemを利用し、整理情報を復元。復元時も全active rootとの重複/入れ子を検証。変更/移動した別ファイルの同一性追跡機能を追加したわけではない。
- 左ナビに登録rootと解除済みroot、root設定のcontext menu、解除済みrootからパス・初期棚をprefillする再登録入口を追加。GUI修正の最後に**階層menuを直接並ぶnative項目/見出しへ変更**。広幅/狭幅のpane制御、未保存取消の検索条件rollbackを維持。最終ナビ/設定/再登録の実GUI確認は残る。
- AI画像・表紙/文章は**上位の類似候補・その他の参考候補・すべてのAI候補**を別表示へ切替（GUI初期値leading、既存API既定all）。検索結果内のcosineの落差から表示境界を提案し、手動境界[-1,1]にも対応。先頭32件の最大gapが0.03以上かつgap中央値の4倍以上の場合のみ、その隣接値の中間を提案。**未校正の表示heuristicでありキャラ判定の確度/正解率ではない**。明確な落差なしは自動で切らない。同値を分断しない。全件を分類/絞り込みしてからpagingし、元のscore順位を維持。RRFはcosineの閾値を受け付けず、別尺度として表示。
- 名前/タグの全語一致・一致語数とraw scoreを表示。文字一致フィルターは任意/既定offで、名前を持たない画像ヒットに必須にはしない。score表示を2行にし、検索範囲/候補設定をExpanderへまとめて狭幅の一覧を圧迫しない。model/weights/embedding/vector/rankingの変更なし。

### 実施した検証と限界

- **Python225 PASS139.602秒/skip0**（前段223 PASS106.547秒）。新folder11 PASS5.996秒、group3 PASS0.212秒。旧schemaのテスト初回9でSQLite接続を閉じずWindows cleanup error→テスト接続を修正して9 PASS4.365秒。その後棚編集/解除済みrouteの2件を追加。scope/paging・related/partial・初期棚/個別解除/再起動・旧schema・再登録/preview拒否/重複・認証・AI境界/同値/尺度/解除後のvector不可視を確認。
- **Core107 PASS**（従来97＋request/protocol/evidence10）。最終 **x64 SelfContained Release PASS29.27秒/0error/既存IL2104 2warnings、抑制なし**。中間Release32.43/29.99/28.94/30.46/30.40/30.29秒もPASS。左ナビ追加直後はCS0136＋付随XAML errorでFAIL6.52秒→変数修正。C#source/XAML、既存refsのComboBox/NumberBox/Expander/NavigationView/header APIとcached sampleを確認。手動差分レビュー済み。専用WinUI analyzer未導入/未実行、AOT/installer未確認。
- **native01 FAIL7checks/1PNG全目視/正常close1**：閉じたpaneで階層root peerが現れず。02 **FAIL15checks/4PNG全目視/正常close1**：Lightのfolder filter、上位3/参考3/全6切替、score/根拠、gridまで確認。manual0.850は画面に表示したが、最後の要求値の完全等値assertがFAIL（失敗時の要求ログ未保存のため原因は断定しない）。比較を許容誤差へ変更、以降は失敗時も要求を保存。03 **FAIL7checks/1PNG全目視/正常close1**：変更したpane表示でroot peer未出現、AI要求0。
- 合計**6PNG全て個別目視**。native03後に階層を直接項目へ変更しbuild確認、追加GUI起動はしていない。**最終flat nav・棚選択/一括適用・解除/再登録・dirty rollback・Dark・narrow・最終2行scoreは実GUI未完了**。これらをnative PASSとしない。全3runの生成PNG9ファイルbytes/mtime/hash不変、正常終了・cleanup warningなし。終端のsettings bytes assertionは未到達。DPIはtree96、High Contrast/読み上げ/physical keyboardは未検証。
- UIスキル`winui-ui-testing/SKILL.md`の **“Maximum two fix-and-rerun cycles”** に従い03で停止。修正後の最終GUIは次の独立batchで確認する。backend/Core/build成功をGUI成功の代わりにしない。
- runtimeはCPU契約encoder＋手動の生成vector、実GPU/検索精度の証拠ではない。私物scan/元メディア変更/依存追加/model DL/GPU/Laya/OS変更/CI dispatchなし。workflow3本はmanual-only。前回のHark reader等のGUI未到達は今回も未完了。

### 次の3手

1. `tools/test_folder_ui.py --output data/ai-ui/folder-native-new`を新batchで実行し、flat nav・棚設定・解除/再登録・dirty/Light/Dark/narrow・候補切替と手動境界を実機確認。初期tree/失敗ログを保持、floatの差を内容判定の失敗と混同しない。
2. 既存の検索方法/keyboard/AI profile GUI回帰、およびHark reader/JSON pickerの未完了gateを別に確認。解除rootを含むsaved AI scopeは明示的に選び直す（全体へ黙って広げない）。
3. 候補境界の便利さ・取りこぼしを新しい固定評価とユーザーが明示選んだ小サンプルで測る。現在のheuristicをconfidenceや実キャラ分類精度として扱わず、自動内容索引/OCR/VLMは別工程として進める。

---

## 最新：Hark更新をWindowsで確認・不具合修正（2026-10-13、一部GUI確認）

開始HEAD **e406ef257d429289ed18a4f07cd9fa48676c304f**。ローカル8fddcfaから43ファイルをff-only同期。ユーザー追加のAGENTS/vision/agent-start/design-vision・両handoff最新節・Issue4/PR5を確認。今後も「曖昧な手がかり→目的のローカルファイル」、本と素材の両方、交換可能モデル、主要機能安定後のnative UI改善を維持。実装・テスト・記録commit: **dae08a967b1981cef6e56030210c242b4980d6c9**。この後の文書commitでこのSHAを記録し、最終HEADはGit/PRを正とする。

### 維持したHark実装と修正

- CBZ/ZIP reader、関連語辞書/JSON import-export、NFKC等の正規化・複数語/部分一致検索・順位、ErrorText日本語化を保持。新しい評価manifest/順位/model/AI接続・デザイン刷新は行わない。
- Windowsの大きな不正Origin辞書POSTで403前にTCPが切断された。拒否本文を**最大16MiB/64KiB chunk/全体1秒**だけ捨て、JSONとして処理せず元の403/413を返す。遅い/未完uploadもdeadlineで打ち切り、認証・Origin・サイズ制約を維持。新HTTP3/関連語15の回帰PASS。
- ErrorTextはobject以外のJSON error bodyを状態コード案内へfallback（配列/数値/bool/stringのCore4回帰）。未知/既存日本語の扱いは維持。
- RelatedTermsEditorはbusy時に入力3欄/ボタン/listをdisableし「処理しています…」を表示。完了後restore、busy中のdialog closeはCancelして結果の見落としと編集競合を防ぐ。Root.ChangedでScrollViewer高さを更新し、狭幅でdialog全体が画面外へ出ないよう調整。modal中Ctrl+Fを背景へ送らないguard。
- **CoreにあったMatch情報がnativeの手動row描画で使われていなかった**。MatchLabelを共有し、localized kind/availabilityの前へ「関連語の候補」「一部の語のみ一致」を表示。metadata順位/filters/APIは変更しない。Light実機で表示とdirect→related順、partial説明を確認。
- **実行用AppXのdeps.jsonが10月11日のまま**で、Regex DLLは存在してもruntime dependency表にないため日本語エラーがFileNotFoundになった。Rebuild単独では更新しなかった。新しいlayoutへ`winapp run --no-launch`で配置するとdependency表にRegexが入り、旧/新のwindowless比較で欠落/解決を確認。
- `tools/winapp_layout.py`でapp/Core DLL・deps/runtimeconfig・resources/assets・manifest・project/publish設定のbytesをhash化。`start-winui.ps1`は先にbuildし、content hashごとに分かれたignored layoutで起動。変わらないpayloadは再利用。native Python suitesはfixture内のtheme layoutを使用。旧登録AppXを削除/上書きするcleanupはしない。GUIでの新launcher一連の再確認は未実施。

### Windowsで実行した検証

- **全Python211 PASS /127.403秒/skip0**。直前の208 PASS103.079秒にlayout3回帰を追加。最後のproject/publish設定をhash対象へ含める小修正後は対象3 PASS0.010秒と実layoutの起動なし配置を確認。初回205はauth拒否で1error/96.732秒、他204成功。失敗履歴と期待値を維持。
- **Core97 PASS**（Hark93＋error JSON4）。x64 SelfContained Release初回34.39秒、修正後27.26/30.73秒、最終 **Rebuild31.75秒/0error/既存IL2104 2warnings、抑制なし**。Windows XAML buildを今回確認。専用WinUI analyzer未導入・未実行、手動WinUI/transport/deployment差分レビュー済み。
- **native01 全体FAIL15 checks/1PNG全目視/keys0/skip0/正常close0/owned termination fallback1**：2件目saveの前回と同じstatus文字を早く成功判定した。DB待ち/busy状態を補強。02 **全体FAIL21 checks/3PNG全目視/正常close1**：related reasonがUIに未表示。03 **全体FAIL26 checks/5PNG全目視/正常close1**：Lightの辞書保存、busy入力/close guard、direct/related順と理由、partial説明まで確認後、17語エラーで旧AppXのRegex欠落が発生。
- 合計**9PNGを全て個別目視**。Light wide/narrowの辞書と検索理由/partial、各失敗画面のみ。narrowのfields/actionsは独立scrollの境界で一部表示、footer Closeは見える。Dark/reader/JSON pickerには**未到達**で成功扱いしない。DPI96/Contrast off。01のcleanup警告を除き02/03は警告0。3run全て生成sources bytes/mtime/hash不変。終端のAI/settings assertionsは未到達。CPU stub設計で実GPUは使わない。
- UIテストスキルの **“Maximum two fix-and-rerun cycles”** に従い03で停止。新配置にした後のGUI/native再試行はしない。導入済みの`winui-ui-testing/SKILL.md`参照（個人環境の絶対パスはリポジトリへ保存しない）。未到達のGUI gateを全体PASSへ書き換えない。
- **error-runtime-04 windowless PASS**：古いAppX depsでRegex FileNotFoundを再現、新layout depsで検索語制限/入れ子の別名error/object以外503案内の日本語3行が一致。GUIを起動しないC# probeでreader/visualの代替ではない。01はuntrim probeのSystem.Runtime facade欠落、02はtrim runtimeにないFile.WriteAllLines overload、03は生成改行の構文ミスでFAIL。04はappと同じtrim形・File.AppendAllTextを使い期待outcomeを確認。probeは作った1DLLだけを削除し、既存payloadを変更しない。
- `--no-launch`配置2種と最終hash配置でRegex dependencyを確認、元のpackage identityを維持。Python syntax/help/path guard、PowerShell AST、diff check PASS。変更後のnative suites（検索方法/AI profile/keyboard）と通常launcherを実起動で再検証していない。過去のGPU/native成績を今回へ流用しない。
- 生成PNG2/CBZ1/ZIP1・隔離DB/settingsのみ。今回のnativeはreader前で停止し、予定したCBZ revision変更も未実行。model DL/依存追加/OS設定変更/私物scan/CI dispatch/GPU/Laya起動なし。workflow3本manual-only、Draft PR5/base/unmergedを維持。前回shutdown依頼は一時的な完了済み作業として今回へ再適用しない。

### 次の3手

1. 新しい配置を使って独立したnative batchを開始。まず17語日本語error、Light/Darkのrelated/partial/dictionary、JSON save/open picker、busy/dirty保持を確認。今回FAIL履歴を維持。
2. 生成CBZ/ZIP readerのnatural order/画像・ページ番号/前後/破損/503 manual retry/real409/rescan/close cancel/別作品へのlate response/タグdraft/keyboardを確認。`tools/test_hark_ui.py`はその候補runnerだがreader部分は未観測。
3. 上記安定後、別途固定したv6で関連語の過剰展開を測定。AIとの文字側統合、フォルダ本/Komga、実DPI/Contrast/Narratorは段階を分ける。大きな見た目の刷新を前倒ししない。

---

## 最新：エラーの日本語表示と検索エラーの具体化（2026-10-13 夜3）

開始HEAD 3df8cf8。ユーザー指示「更に進めて」。**CI起動0回**。

1. `d972b38` WinUIでサーバーの英語エラーを日本語表示（`src/Aredoko.Core/ErrorText.cs`）。固定文言の対応表と、関連語の検証エラー（「3件目: 別名に空白は…」等）のパターン変換。日本語・未知の文言はそのまま。HTMLや空の本文でも例外にせず状態コードで案内。`LibraryApi`のGET（検索・書き出し・一般GET）もPOSTと同じ扱いに統一（以前はGETの失敗が英語の`HttpRequestException`文言）。`tests/test_error_text_coverage.py`がサーバーの固定英語エラーすべてに日本語訳があることを静的検査。
2. `f470804` **バグ修正**：`GET /api/items`の検証エラーが常に`Invalid request`になり、17語以上の検索などで理由が分からなかった。`Use at most 16 search words`・`Invalid paging`（負数・非数字・`²`等）・`Invalid filter`を返す。

テスト（Linux、最小限）：Python **205 PASS**、C# Core **93 PASS**、WinUI C#-only compile 0 error。**未検証**：Windows Release・XAML・native GUI（エラー表示の見え方を含む）。

次の3手：(1) Codex/AntigravityでWindows native確認。(2) 新しいv6で現在の関連語規則を判定。(3) 部分一致で欠けた語を作品ごとに示すか検討。

---

## 最新：途中一致展開・順位バグ修正・部分一致の空表示修正（2026-10-13 夜2）

開始HEAD db80c18。ユーザー指示「どんどん改善、バグがあれば直す」。**CI起動0回**。

バグ修正：
- `20ff690`（v5凍結commit内）部分一致フォールバックが**0件でも`partial`を返し**、WinUIが「1語に一致する作品を表示しています」と0件で誤表示する問題を修正。
- 同commit：関連語の書き出し完了メッセージが、dialog内の**古い件数**を表示し得た問題を、書き出した文書の件数に修正（Core `CountExport`）。
- `62b54fb` 短い別名が別の名前に含まれるだけの作品（「ナギ」⊂「ナギサ」）が、見出し語で一致した作品より**先に並ぶ順位バグ**を修正（入力語一致→長い表記→ID順）。部分一致フォールバックで直接一致より関連のみの作品が先に出る問題も同時に解消。

改善：
- `62b54fb` 3文字以上の語は見出し語・別名の**途中**でも展開（「セレナーデ」→「聖夜のセレナーデ」）。
- v5 holdoutを実装前に凍結。関連語群MRR 0.600→1.000（同じ作者なのでdevelopment寄り）。
- `ebc6e9b` 一致判定・部分一致・順位を1行1回の採点に統合し、重い検索を最大1.15秒→0.94秒（Linux単発）。

テスト（Linux、最小限）：Python **204 PASS**、C# Core **89 PASS**、WinUI C#-only compile 0 error。**未検証**：Windows Release・XAML・native GUI。

次の3手：(1) Windows native確認（関連語dialog・書き出し/読み込み・部分一致ラベル）をCodex/Antigravityで。(2) 新しいv6で現在の規則を判定し、実ライブラリに近い語彙で過剰展開を確認。(3) サーバーのエラーメッセージ（英語）をWinUIで日本語化。

---

## 最新：関連語の展開拡張と部分一致フォールバック（2026-10-13 夜）

開始HEAD baac57e。ユーザー指示「テストは後でCodex/Antigravityにやらせるので、今は進められる改善を」。**CI起動0回**、workflow無変更。

1. `d1c2068` 関連語展開：2文字以上の**先頭部分一致**（「星灯り」→「星灯りの社」）と、**別名経由の関連**（「ほしあかり」→「星灯りの社」→関連キャラ）。1文字は展開しない。連鎖はしない。
2. `ad05e70` v4 holdoutを**変更後・実行前**に凍結。`1fb273f` 評価器が`--manifest v3|v4`に対応。v4関連語群MRR：変更前0.400→変更後0.800（同じ作者なのでdevelopment寄り）。
3. `bca1496` 全語一致0件・2語以上のとき**1語欠けの作品**を`match:"partial"`/`partial:{words,required}`で返し、WinUIは「一部の語のみ一致 ·」と案内文で明示。v4結果を見た後の追加なのでv4の数字（MRR 0.900）は参考値。仕様変更：以前の「全語AND・不一致は0件」から変わった。

詳細と残る失敗（見出しの途中部分「アステリア」は展開しない）は[related-terms.md](related-terms.md)。

テスト（Linux、最小限）：Python **202 PASS**、C# Core **88 PASS**、WinUI C#-only compile 0 error。**未検証**：Windows Release・XAML・native GUI（関連語dialog、picker、部分一致ラベル、reader）。後でCodex/Antigravityが検証予定。

次の3手：(1) Windowsでnative確認（関連語dialog・書き出し/読み込み・部分一致ラベル）。(2) 部分一致フォールバックが実利用でノイズにならないか、新しい凍結v5で判定（語の途中一致展開の是非も）。(3) GPU環境でv3/v4にAI条件を追加。

---

## 最新：関連語の固定評価v3とJSON読み込み/書き出し（2026-10-13 後続）

開始HEAD **5b88c56**（ユーザーのAGENTS.md/デザイン方針更新を取り込み済み）。AGENTS.mdの新CI方針（枠枯渇中は起動しない、後も根拠付き1回・自動再実行なし）とWindowsデザイン方針（現GUIはPoC、今は改修しない）を確認。**CI起動0回**、workflow無変更（3本ともworkflow_dispatchのみを確認）。

1. `159c202` 固定評価manifest `tests/fixtures/literal-related-v3.json` を**実行前に凍結**（SHA256 c4fa0d94…5091）。
2. `783a31a` `tools/evaluate_literal_search.py`：生成placeholder＋一時DBで旧LIKE/新・辞書なし/新・辞書ありを比較。結果と観測された失敗4件は[related-terms.md](related-terms.md#固定評価-literal-related-v32026-10-13linux)。関連語群MRRは0.000→0.400→0.800。辞書は評価者が書いたので実品質の証拠ではない。
3. `34783ee` 関連語のJSON書き出し/読み込み：`GET /api/library/terms/export`、`POST /api/library/terms/import`（全件か0件、同じ見出し語は置換、16MiB）。Core `CheckImport`/`DescribeImport`、dialogにpickerボタン2つ。

テスト（Linux）：Python **199 PASS**（`NO_PROXY=127.0.0.1,localhost`）、C# Core **86 checks PASS**、`tools/compile_check_winui.py` **0 error**。**未検証**：Windows Release・XAMLコンパイル・native GUI（関連語dialog、picker、reader）。

次の3手：(1) Windowsで関連語dialog（保存・削除・書き出し・読み込み）と「東方 巫女」型検索、readerをnative確認。(2) GPU環境でv3にAI条件を追加して比較。(3) 観測された失敗（部分一致展開・2段展開・汎用語）の改善案を新しい凍結holdoutで判定。

---

## 最新：文字検索の正規化・複数語AND・関連語辞書、Linux C#検証（2026-10-13）

開始HEAD **dd31e6385932f439a9bf48435fa3022e0dfbdf59**（clean、同じ`feat/winui3-production-mvp-20261011`/Draft PR #5/base `feat/gui-framework-comparison-20261010`）。AGENTS→vision→agent-start→両handoff最新節→Issue #4/PR #5を確認。PR #6（ビジョン）は取り込み済みのため再取込みなし。今回の環境は**Linux sandbox**（Windows/GPUなし）。GitHub接続で直接clone・通常pushが可能になり、以前の部分snapshot方式は不要。**CI起動0回・workflow変更なし**、main/他PR無変更、force push・branch削除なし。

### 実装したこと（コミット順）

1. `0d665e2` **Linux用C#のみWinUIコンパイル検査** `tools/compile_check_winui.py`：XAMLの`x:Name`から型付きfield stubを生成し、Windows App SDK 2.5.1参照で`data/`配下（ignored）にだけbuild。XAML markup・binding・資源・event配線・packaging・実行時は**検証しない**。故意の型/名前誤りでFAILすることを確認済み。stub生成の回帰3件。
2. `97b9b72` **文字検索の正規化と複数語AND**（`app/search_terms.py`）：NFKC＋casefold＋カタカナ→ひらがな、空白区切りの全語AND（語順不問、上限16語）。旧来のLIKE連続一致は通常そのまま一致（上位集合）。デモ`Catalog`は不変。
3. `e942298` **ユーザー関連語辞書**（`app/term_relations.py`、DB表`term_relations`）：見出し語/別名/関連語。検索語ごとにOR候補を追加するだけで元の語・フィルターは保持。直接一致を先に並べ、関連語だけの一致は`match:"related"`、展開内容は`expansions`で返す。1語の候補256表記まで、入力語の多くに関係する見出しを優先し超過は`truncated`で開示。API `GET/POST /api/library/terms`、`POST /api/library/terms/delete`（既存token/Origin保護）。
4. `2e4bcfa` WinUI client：Protocolに`Expansions`/`Match`を追加（reflectionなし）。一覧の「関連語の候補 ·」表示と、文字検索案内に追加語（1語3表記＋「ほか」）を表示。
5. `3435dd9` WinUI「関連語」ボタンとdialog（`RelatedTermsEditor.cs`、C#契約`RelatedTerms.cs`）。既存の`transitions`/`dialogOpen`ガード、未保存draftがあるときは閉じた後の再検索をしない。
6. 文書：[related-terms.md](related-terms.md)（新規）、api.md、archive-reader.md、両handoff、agent-start、PR #5説明。

「東方 巫女」の評価シナリオ：辞書なしでは`東方`/`巫女`タグの作品だけ、辞書`博麗霊夢←東方、巫女`を登録すると博麗霊夢タグだけの作品が直接一致の次に出ることを生成fixtureで確認（`test_vision_case_tohou_miko_finds_reimu_after_direct_hits`）。**辞書はユーザーが登録する前提で、自動知識・AI精度の実証ではない。**

### テスト結果（Linux sandbox）

- `python -m unittest discover -s tests -q`：**195 tests PASS**（178＋compile stub3＋search_terms6＋term_relations8）。注意：sandboxのHTTP(S)_PROXY環境変数があると既存HTTPテスト13件が404/接続エラーで落ちるため、`NO_PROXY=127.0.0.1,localhost`で実行。製品コードの問題ではない。
- `dotnet run --project tests/Aredoko.Core.Tests -c Release`：**81 checks PASS**（.NET SDK 10.0.401をsandbox内の作業フォルダにだけ導入。ユーザーPCには何も入れていない）。以前「未ビルド」だったreader C#契約テストも今回初めて実行・PASS。Core build 0 warning。
- `python tools/compile_check_winui.py`：**exit 0、0 error/0 CS warning**（C#のみ）。`MainPage.xaml`はwell-formed確認のみ。
- 生成5万件の2語検索 約0.30秒（count＋1ページ）、関連語300見出し時 約0.65秒（sandbox単発、Windows/1TB/GUI込みは未測定）。
- **未検証**：Windows x64 SelfContained Release、XAMLコンパイル、native GUI（関連語dialog・案内文・一覧表示・再検索、既存reader UI）、高DPI/Contrast/Narrator、実GPU。過去のWindows合格記録を今回の証拠に流用しない。

### 残課題

- 上記Windows/native検証一式。resize時の詳細pane自動保持は未修正のまま。
- 関連語辞書はAI混合/意味検索には未接続（文字検索のみ）。JSON import/export、作品の自動関連知識は未実装（自動DL・同梱なし）。
- 「東方 巫女」を固定評価セットに組み込んだRecall@k/MRR比較は未実施。

### 次の3手

1. Windowsで`dotnet build src/Aredoko.WinUI/Aredoko.WinUI.csproj -c Release -p:Platform=x64`とCore tests、生成fixtureで「関連語」dialog保存→「東方 巫女」検索→「関連語の候補」表示・draft保持、reader UIのnative確認（[related-terms.md](related-terms.md)、[archive-reader.md](archive-reader.md)）。
2. 生成素材の固定評価セットに「東方 巫女」型シナリオ（名前・タグ完全一致なし）を追加し、文字/辞書あり/AI混合のRecall@k・MRRを比較。
3. 辞書をAI混合検索の文字側根拠として扱う設計（フィルター優先・根拠表示）と、ユーザー明示のJSON import/export。

Linux環境の再現：.NETがない場合は公式`dotnet-install.sh --channel 10.0 --install-dir <作業用>`をsandbox内だけで使い、PATHを通してから上記コマンド。HTTPテストは`NO_PROXY`を設定。

---

## 最新：プロダクトビジョンとAI入口を作業ブランチへ統合（2026-10-13）

開始remote HEAD **2ceafafa81a21e3eb8f97aa4e80678d1903d86c2**。ビジョン作成branch `docs/product-vision-20261013` の **14660b644d013be48e528743203b85bab420eceb** を固定して確認。ユーザーの「他のAIへAGENTS.mdを読ませれば目的が伝わるよう整理」の依頼で、docs/product-vision.mdを**本文変更なし**で製品作業ブランチへ選択的に取り込む。別branchのコード・過去handoffを丸ごとmergeしない。

- ルートAGENTSに全AI共通の読む順序、目的と実装状態の根拠、現行branch確認、既存Draft PR #5継続、CI必要時のみを明記。
- docs/agent-start.mdを追加し、正本/仕様/最新handoff/コード・テスト/PRの役割と優先関係を整理。mainや比較branchの古い説明で現状を判断しないことを明記。
- READMEを現行WinUI開発版の入口へ整理し、保存済みWeb demoと比較kitの説明を区別。古い「GUI未決定」を解消。追加readerのWindows未ビルド/native未確認は維持。
- docs/spec.mdの目的参照と決定済みWinUI/Python+SQLiteを更新。提案機能を実装済みと見せない。
- **文書だけの変更。** リンク/参照先・正本byte一致・diffを確認。CI起動0回・コード変更/ビルド/フルテスト再実行なし。直前Python178PASSは過去sliceの成績で、追加C#/Windows/nativeは未検証のまま。
- 同じfeature/Draft PR #5/comparison baseへ通常fast-forward。main・他PRはmergeしない。AGENTS自動発見の可否は各AI次第だが、「この作業branchのAGENTS.mdと参照先を読め」で辿れる入口をそろえる。

### 次の3手

1. docs/agent-start.md→vision→両handoff最新節→Issue #4/PR #5の順に読んで再開する。
2. Windowsで追加reader C#tests/Release buildと生成fixtureのnative操作を確認する（docs/archive-reader.md）。
3. 以後の機能選択は曖昧な日本語から目的のファイルへ到達するビジョンと実測を基準にする。「東方 巫女」ケースは今後の品質評価目標で、既存モデルの合格実績としない。

---

## 最新：ZIP事前検査と自然順の境界修正（2026-10-13）

開始remote HEAD **c38a7952fc1954e92f1e57d05da222ef83a77e7d**（読書UI候補checkpoint）。同じfeature/Draft PR #5/comparison base。使用量残率は取得できず5%到達を確認したわけではない。**CI起動0回・workflow変更なし**を継続。最新提出SHAはPR #5 headを確認する。

- 実際に再現した2件を修正：5000桁の数字を含むページ名でPython整数変換上限に達する例と、`²1.png`のような非十進数字記号を整数に変換して失敗する例。十進数字を桁数＋文字列で比較し、Unicode decimal/先頭0/同順位のdirectory順を維持。Python全体の整数上限設定は変更しない。
- ZIP64 locatorはlegacy EOCDの件数/サイズが小さくてもstdlibが採用し、先に確認した値を置き換えることを確認。locatorを明示拒否し、legacy値だけで除外したつもりになる経路を閉じた。ZIP64は従来どおり非対応。
- ZipFile/ZipInfoの生成前に固定46byteのcentral-directory headersを走査。実件数10000上限・申告件数一致・可変長fieldのdirectory内境界・signature・entryのZIP64 sentinel/multidiskを検査。directory4MiB/総512MiB/画像8MiB/圧縮比200と共有2枠を維持。prefix付きZIP/通常commentを許容する回帰も確認。
- 新規自然順3件（修正前2件FAILを記録）＋ZIP preflight7件。reader16/preview12/preflight7の対象テストPASS後、**全Python178 tests PASS /16.628秒/skip0**。生成10001entry fixture/hidden ZIP64 locator/破損header等だけを使い、実モデル・私物・ネットワーク取得なし。fixture期待hashは変更なし。
- XAML/GUI/C#はこのsliceで変更なし。前checkpointで追加した読書画面とC#testsは**未ビルド・native未確認のまま**。Linux環境に.NET/Windowsなし。Python178PASSをGUI合格に流用しない。前回Windows93checks等も今回の証拠ではない。
- docs/api・archive-reader・両handoffを更新。GitHubの元tree/parentへ変更ファイルだけをexpected head付きfast-forwardで反映し、local snapshot履歴はpushしない。Draft未マージ、モデル/順位/Laya/依存/OS/個人設定/私物・元メディア無変更。

### 次の3手

1. Windowsで追加C#契約テストとRelease buildを実行（[archive-reader.md](archive-reader.md)）。CIはローカルで実行できない必須gateに限り、反復dispatchしない。
2. 生成CBZ/ZIPでreaderの明暗/狭幅/前後/破損/409/close中断/タグdraft保持をnative確認し、必要な修正のみ行う。検証まで読書UIを完成と扱わない。
3. resize時の詳細pane閉鎖は未修正。実機で明示close/light dismissと競合しない方式を検討し、高DPI/Contrast/Narratorも独立確認。

---

## 最新：WinUI読書画面の接続候補・ローカル回帰確認（2026-10-13）

開始remote HEAD **2542aa701451b0f41f041944f0c2bdadf322d238**。同じfeature/Draft PR #5/comparison base。ユーザーは残り使用量5%まで継続改善し引継ぎを残すよう依頼したが、使用量残率を取得する機能がないため5%到達を判定できない。変更ごとのcheckpointを残す。**CIは必要時だけ**という追加指示を保持し、今回CI起動0回・workflow変更なし。

- 詳細の「本を開く（CBZ / ZIP）」からmodal読書画面を開く実装を追加。presentかつ対応拡張子だけ有効。タグの未保存draftは保存/破棄せず保持、既存transition/dialog guardで同時操作を抑止。前/次・ページ数・再試行・明示的な開き直し・拡大scroll・閉じるを実装。
- C#のArchiveReaderClientは既存loopback/sessionを共有。reflection-free manifest検証、item ID/revision/page範囲、JSON4KiB/画像8MiB/Content-Type/Content-Length/受信長、bodyを含む40秒deadlineを検査。409/403はreader manifestを無効化、404は壊れたページを飛ばして前後へ移動可能、503は明示retry。自動retryやprefetchなし。
- 読書画面は1要求ずつ。閉じるとHTTP cancel・保持画像破棄、decode後もキャンセル/作品/pageを検査。既存codecを再利用し入力16M画素/8MiB・読書画像長辺2048pxに制限。旧thumbnailは既定256pxのまま。保存cache/展開なし。TextBlockの動的読み上げ名を固定しない。
- **全Python168 tests PASS /17.242秒/skip0**（既存155＋reader13）。取得した追加53ファイルはGit blob SHAでupstream byte一致を確認。最初のfull runはsnapshot転送時にfixture末尾改行が増えてhash guard5件が失敗した。upstreamと同一byteへ直した再実行が168PASS。テスト/fixtureの期待hashを変更していない。setup系のモデル保存メッセージはmock試験出力であり実モデル取得なし。
- **Windows Release/Core C# tests/native GUIは未実行・未合格。** このLinux環境に.NETなし。追加C#契約テストはソース作成のみ。XAML well-formedとgit diff checkはPASSだがコンパイル/WinUI動作の代替ではない。新読書画面のレイアウト/フォーカス/実decoder/高DPI等は検証待ちで、製品完成と扱わない。詳細は[archive-reader.md](archive-reader.md)。
- 既存resize自動open保持は未変更。モデル/順位/Laya/依存/OS/個人設定/私物/CI workflow変更なし。Draft未マージ。GitHubの元tree/parentへ変更ファイルだけをfast-forward適用し、部分snapshotのローカル履歴はpushしない。

### 次の3手

1. WindowsでCore契約testsとx64 SelfContained Release buildを実行。新readerのLight/Dark・幅700/1200・前後/破損/409/close中断/未保存タグ保持を生成fixtureで確認。未検証コードを合格扱いしない。
2. archive名の自然順・境界条件を追加レビューし、必要なPython回帰だけで改善する。CIはローカルで確認できない必要なgateに限る。
3. resize/open-stateと高DPI/Contrast/Narratorは実機で独立確認。フォルダ本/Komga/見開き/読書位置保存は別段階。

---

## 最新：CBZ/ZIPページ閲覧APIの最小実装（2026-10-13）

開始時のremote HEAD **8fddcfae19a309ff4a9561d691ee97bbb6b85bcb**、同じ `feat/winui3-production-mvp-20261011` / Draft PR #5 / comparison base。AGENTS・Issue #4・PR・両handoff最新節・ai-resource-policyを確認。今回の環境はLinuxでWindows/.NETなし。Gitの直接clone認証は利用できず、GitHub接続から固定SHAの必要ファイルを取得した部分snapshotで検証した。ローカル検証用git履歴をupstreamへpushしない。変更する6ファイルだけを元のremote tree/parentへ適用し、expected head付きのfast-forwardで反映する。提出SHAはPRで確認。

- 次のreader項目をbackendだけ小さく実装。既存PreviewReaderにmanifest/read_pageを追加し、登録item IDからCBZ/ZIPのページ数・revisionを取得して0始まりの任意ページを読む。自然順・同名時のdirectory順を固定、ZipInfoから読む。展開保存・全画像の事前decode・モデル起動はしない。既存表紙readは同じ先頭ページとbyte/MIMEを返す。
- manifest/page/既存previewが同じ2枠を共有。root・除外・present・reparse/symlink・索引size/mtime・open handle検証、archive512MiB/directory4MiB/entries10000/image8MiB/圧縮比200を維持。ZIP64/multidiskは非対応。manifestは画像候補件数であり全ページの正常性を保証しない。暗号化/CRC破損/過大ページはそのページ取得時に拒否する。
- `GET /api/library/reader/{id}` → `{item_id,page_count,revision}`。`GET /api/library/reader/{id}/pages/{page}?revision={revision}` → image bytes。Host/token検証・no-storeを継承。400不正要求/403認証拒否/404利用不可/409変更検出/503共通枠busy。任意path指定は受け付けない。
- revisionはfile identity・size・mtime・ctimeのSHA256で、内容全体のhashやsnapshot保証ではない。変更された未再scanファイル・古いrevision・読取中のmetadata変更を409にする。再scan後も古いページ番号をそのまま別revisionへ使わない。新規GUIはまだ接続しておらず、読書機能完成とは扱わない。
- **新規reader13 + 既存preview12 + production6 = 31 tests PASS / 3.085秒 / skip0**。一時生成PNG/CBZ/ZIPとDB、実production HTTPのみ。自然順/同名ページ/manifest非展開/再起動/注釈・元bytes/mtime維持/非先頭ページの暗号化・CRC・圧縮比・byte制限/除外・link・stale/同時枠/認証・要求検証・旧previewを確認。今回の部分snapshotで `python -m unittest discover -s tests -p 'test_*.py' -v` を実行。全repoスイートを31件と誤記しない。再現は各 `test_reader.py` / `test_previews.py` / `test_production.py` の3スイート。
- WinUI/モデル/順位/CI workflowは変更なし。Windows Release・Core・native GUI・実GPU・高DPI等は今回未実行。前回editor-native-03の成績は履歴であり今回の証拠ではない。私物・個人設定・依存・OS変更なし、モデルDLなし、Laya既定無効・CI manual-only・Draft未マージを維持。前回一晩のshutdown依頼は今回へ再適用しない。

### 次の3手

1. WinUIのread-only reader画面を追加。明示「開く」、前/次とpage count、既存ThumbnailCodecのbyte/pixel/decode制限、古い非同期応答の破棄、409再open案内を接続し生成素材でnative確認する。
2. Windows実機でresize時のpane自動保持を独立調査。今回コード変更なし。前回の即時open再設定/close-switch-reopenが不安定だった履歴と明示close/light dismissを尊重する。
3. 実高DPI/Contrast/Narrator・全面keyboardを別確認。フォルダ本/Komga/見開き/読書位置同期は後続。

---

## 最新：保存focus・高さを使う詳細と固定保存欄（2026-10-13）

開始HEAD **d93bf21d5a88d8ae8a1ee89b63814ed0e0fa907f**。同じfeature/Draft PR #5/comparison base。今回の実装・検証・仕様commitは **93f90c7244bfa9cea497fbfdd6d11fcf850852ce**。このSHA記録は文書だけの後続commit。通常push後の最終HEAD/CI観測はGit/PR head・PR説明で確認。

- 詳細をNavigationView内の利用可能な高さ全体へ配置。狭幅overlayでも作品名・表紙・編集欄を広く表示し、不透明背景を維持。保存ボタン/編集状態は下部固定、詳細/編集fieldsだけ縦scroll。toolbarの折返しはwindow幅ではなく実content幅で選び、wide Inlineの320幅を引いた場合にも対応。
- SaveAsyncはeditor内の元controlとfocus state、disable直後の退避先を記録。完了時にfocusがそのまま・同一作品・pane openの場合だけ成功/失敗とも復帰。成功後にSaveがdisabledならタグ欄へ。保存中に検索欄へ移った場合はfocusを奪わない。エラーでは編集内容と再試行を維持。モデル/API/順位/source変更なし。
- **editor-native-03 構造化PASS / 93 checks / 実キー入力50 / skip0 / 12PNG全目視 / 指定pane・footer・dialogのvisual PASS / 正常close2 / cleanup警告0**。Light/Dark1200x820と700x620、DPI96/Contrast off。生成65PNG/1root・隔離DB/settings・CPU契約encoder、認証済み実production HTTP＋Release GUI。
- 各themeで成功保存後Shelf focus、意図的409後タグ/DB不変とTags focus、Enter再保存とdisabled Save→Tags、応答を遅延した保存中のUIA Query focus維持を確認。fixtureはcatalog.updateだけをテスト内で置換し、実handlerのHost/token/Origin/body検証と実WinUI response handlingを維持。失敗2件・遅延2件が終端で消費されたことを確認。UIA Query focus移動を物理keyboard成功として数えない。
- 既存Ctrl+F/Tab/Shift+Tab/文字検索/前次ページ/list・grid選択/favorite/Ctrl+S/Esc/dirty cancel・discardも完走。終端AI calls/resident workerなし、settings bytes/source bytes/mtime/hash不変。狭幅Save onscreenをUIAで確認し、wide error/saved・narrow list/grid/dialog/closedを各themeで全目視。thumb/gridのviewport境界で行が一部見えるのは既存scroll。WinAppがtooltipを同時captureした画像には外枠ラベルが付いたが、これは製品UIではない。全面UI/A11y auditではない。
- **editor-native-01/02は各FAIL38checks/実入力17/skip0/4PNG全目視/正常close1**。Lightの保存成功・失敗・retry・選択focus維持は確認したが、overlay→inline resizeでpaneが閉じてTxtTags待機が停止。open値の即時再設定とclose-switch-reopen案はいずれも安定せず最終版から除いた。03は既存BtnDetailsから明示的に再open。**リサイズ時の自動open保持は未実装/既存挙動のまま**で、03 PASSに含めない。2 fix-and-rerun cyclesで終了、追加native試行なし。
- Fresh **Core35 PASS / production Python6 PASS1.918秒**。Release初回25.95秒・修正後24.91秒・最終 **x64 SelfContained Release PASS24.86秒 / errors0 / 既存IL2104 2warnings（抑制なし）**。syntax/help/path/negative focus guards/diff・手動WinUIレビュー済み。project scoped FocusManager.GetFocusedElement(XamlRoot)/Control.FocusState/ContentControl.VerticalContentAlignment/Grid.SetRow等を確認。専用WinUI analyzer未導入・未実行。全Python155/AI/GPUは今回は再実行なし。
- 高DPI/HighContrast/Narrator/全面Tab順/保存中の別ウィンドウ操作は今回未検証。依存/OS設定/モデルDL/私物scanなし。Laya既定無効/元ファイルread-only/CI manual-only/Draft未マージを維持。README/statusを実装済み開発版の案内へ更新、旧Web demoを保持。

### 次の3手

1. resizeのpane自動保持を独立sliceで調査。未保存内容を失わず、明示close/light dismissと自動復帰が競合しない設計にする。
2. 実高DPI/Contrast/Narrator・全面keyboardを別確認。OS設定は明示許可なしで変更しない。
3. CBZ/ZIPのread-onlyページ閲覧を次の小さな縦切りへ。既存PreviewReaderのroot/reparse/stale/ZIP directory/byte/worker制限を引き継ぎ、フォルダ本・Komga・見開き・読書位置同期は別段階。Laya gateは既定無効のまま。

### シャットダウン依頼

ユーザーが就寝中の実装完了後shutdownを明示依頼。テスト・引継ぎ・commit/通常push・PR更新と所有テストapp/server終了を確認後、最後に非表示helperから45秒後 `shutdown.exe /s /t 0` の通常shutdownを要求する予定。`/f`なし、強制終了を暗黙に行う正のshutdownタイムアウトも使わない。helper開始/要求のlocal receiptはignored `data/ai-ui/overnight-shutdown-20261013.json`。電源offの完了はこのセッションから確認不可、開始/受付状況と区別する。

---


## 最新：狭幅詳細パネルの透けを修正・keyboard完走（2026-10-13）

開始HEAD **76a4393c67f1c65aa2ad2422e38a32066f5a60e2**。同じfeature/Draft PR #5/comparison base。今回の実装・検証・仕様commitは **7386ab13e04746ff2816911105ab6dda5bdea670**。このSHA記録は文書だけの後続commit。通常push後の最終HEAD/CI観測はGit/PR head・PR説明で確認。

- ユーザーの狭幅詳細が一覧に重なって見づらい指摘を確認。SplitView.PaneBackgroundを半透明CardBackgroundFillColorDefaultBrushから不透明SolidBackgroundFillColorBaseBrushへ変更。既存の境界線/角丸、wide Inline/narrow Overlay、編集/保存/未保存確認は維持。復元済みWinUI2.3.9 resourcesでLight #F3F3F3/Dark #202020/HighContrast SystemColorWindowColorを確認し、ThemeResourceのまま追従。HighContrast実機は未検証。
- キー送信前に所有process-instance/HWND/PID/foregroundと実HasKeyboardFocusを再確認。focus後のsend-keysで再度--targetを指定しない。入力guardは維持、過去peer失効の根本原因が確定したとは扱わない。
- **native06 構造化PASS / 74 checks / 実入力40 / skip0 / 10PNG全目視 / scoped visual PASS / 正常close2 / cleanup警告0**。Light/DarkでCtrl+F/Tab/Shift+Tab/文字検索/前次ページ/list・grid選択/タグ入力/favorite/Ctrl+S DB保存/Esc一覧focus復帰/dirty dialog cancel・discardを完走。DPI96/Contrast off、生成65PNG/1root/隔離DB・settings/CPU契約encoderのみ。終端AI calls/workerなし・settings byte不変・source bytes/mtime/hash不変も到達。
- 1200x820の保存済みlist、700x620の開いたlist drawer/開いたgrid drawer/未保存dialog/閉じたgridを各themeで撮影。詳細の下へ一覧の画像/文字が透けないことを目視。詳細は縦scroll、狭幅では表示領域が小さくscroll位置でタイトル/プレビューの一部が見える。list/gridのviewport末端で一部の行が見えるのは既存scroll境界。今回のvisual PASSは背景の不透明化と指定controls/dialogに限定し、狭幅の情報密度/表示領域や全面accessibility auditの合格ではない。
- **native04 構造化PASS70checks/実入力40/skip0/6PNG全目視/正常close2**。両themeの操作は完走したが、狭幅画像で透けが見つかりvisual FAIL。**native05 FAIL28checks/実入力12/skip0/3PNG全目視/正常close1**。サイズ切替でpaneが閉じたためTxtTags focusが見つからず停止、narrow list画像はdrawerが閉じた未成立証拠。06では既存BtnDetailsから開き直し、タグ値を待って撮影。04/05と以前01/02/03の失敗履歴は保持、06まで2 fix-and-rerun cyclesで終了。
- Fresh **Core35 PASS**。背景変更前Release PASS28.27秒、最終背景変更後 **x64 SelfContained Release PASS26.38秒/errors0/既存IL2104 2warnings（抑制なし）**。syntax/help/path/negative-focus guard/diff・手動WinUIレビュー済み、project scoped PaneBackground APIと実package theme resources確認。専用WinUI analyzer未導入・未実行。production Python6/全Python155/AI・GPU suitesは今回再実行なし。
- API/モデル/順位/既定Laya無効は変更なし、実GPU/検索品質/高DPI/HighContrast/Narrator/全面Tab順/保存後editor focus保持は今回未確認。OS/依存/ダウンロード/私物scanなし。生JSON/DB/設定/PNG/素材はignored。CI manual-only・Draft未マージを維持。

### 次の3手

1. 保存後editor内のfocus保持を独立sliceで改善・検証（既存SaveAsyncの一時disableでfocusがページボタンへ移る観測あり）。
2. 実高DPI/Contrast/Narratorと全面keyboardを別検証。OS設定は勝手に変更しない。
3. reader/Komga/フォルダ本の仕様から次の小さなsliceを選ぶか、未観測の固定品質入力を準備。Laya既定無効を維持。

---

## 最新：詳細のEsc・フォーカス復帰とnative keyboard（2026-10-13、一部確認）

開始HEAD **e9d88f78ddd6cddbf5ad95d64dd5796565f5cc4b**。同じfeature/Draft PR #5/comparison base。今回の実装・検証・仕様commitは **d81053e36ef3420a1df0f7ab5ea95c37626acdbb**。このSHA記録は文書だけの後続commit。最終HEAD/CIはGit/PR head・PR説明で確認。

- 詳細内の未処理Escを追加、close buttonと同じ既存未保存確認を使う。transition guardで直列化し、閉じた後に一覧へkeyboard focusを戻す。タグ/棚の明示NameとEsc tooltip。モデル/順位/API/source変更なし。
- Core **35 PASS**、production Python **6 PASS / 2.161秒**、初回Release PASS / 40.27秒・最終 **PASS / 31.42秒 / errors0・既存IL2104 2warnings**。syntax/CLI/diff・手動WinUIレビュー済み。専用analyzer未実行、全Python155/AI/GPUは今回再実行なし。
- native03は**全体FAIL / 50 recorded checks / 実入力26 / skip0 / 4PNG全目視 / 正常close2 / cleanup警告0**。生成65PNG/1root・隔離DB/settings、Light/Dark DPI96/Contrast off。Lightで検索/Tab/ページ/list/grid選択/Ctrl+Sタグfavorite保存/Escフォーカス復帰/未保存cancel・discardを実キーで確認。Darkは検索/次ページまでで `send-keys --target BtnPrevious` のUIA peer失効により停止。Dark editor/保存/Esc等は未確認。
- native01 **FAIL17checks/実入力7/skip0/1PNG全目視/正常close1**：ListView本体から子へのfocusにCLIが対応できず停止。native02 **FAIL14checks/実入力4/skip4/1PNG全目視/正常close1**：Homeが未選択行を選択しないためeditor待機停止。03でSpaceへ修正した。2 fix cyclesで停止、後続native再試行なし。Windows activation拒否のguardは維持。
- 3runのsource bytes/mtime/hash不変、owned app正常終了。03のend-of-batch counter/settings-byte/全体PASSは未到達。全成功と報告しない。高DPI/HighContrast/読み上げ/全面keyboard未確認。保存後focus保持は改善候補。詳細：[keyboard-accessibility.md](keyboard-accessibility.md)。CPU stubのみ、私物/モデルDL/依存/OS変更/GPU/Layaなし。CI manual-only・Draft未マージ。

### 次の3手

1. peer失効を分析し、owned focus後の再target等の入力経路を見直してDark未到達分を独立確認。既存ガードと失敗履歴を維持。
2. 保存後focus保持、実高DPI/Contrast/Narratorと全面keyboardを別検証。OS設定を勝手に変えない。
3. reader/Komga/フォルダ本か未観測の固定品質入力を次sliceへ。Laya既定無効維持。

---


## 最新：検索方法の実CUDA・文章専用profile（2026-10-13）

開始HEAD **20bdc2c1bad33d8b0feadb9b132a9183e44194d2**。同じfeature/Draft PR #5/comparison baseを維持。実装・検証・仕様commitは **433e2566bde3678df5956ee30597803d96f7ea31**。このSHA記録は文書だけの後続commit。通常push後の最終HEAD/CI観測はGit/PR head・PR説明で確認。

- 画像非対応案内の旧「AI意味検索」を「AI文章」へ訂正。既存nativeハーネスへ明示 `--cuda` / `--text-only` を追加し、CPU契約と実GPUの結果を分離。モデル/順位/自動routing/WinUIコード変更なし。
- 実CUDA **画像対応 75 checks・要求19件・document/image/query=2/2/15 / 文章専用 75 checks・要求19件・document/image/query=2/0/13**。各6PNG全目視/scoped visual PASS/正常close2/owned handles6全終了/cleanup警告0。Light/Dark wide/narrow、DPI96/Contrast off。固定生成3PNG/2rootだけでproduction HTTP/AISearch/Release GUIを確認。検索品質の評価ではない。
- saved scope/種類/favorites/page0、空query/restart literal、dirty cancel/discard、error件数/ページ番号/前次disabled・文字検索復帰を確認。文章専用profileではcoverを推論前に拒否しGUI案内を表示、AI文章へ復帰可能。2profileのkey/store分離・vectors/元bytes/mtime/hash/設定byte不変。
- 両themeでworker解放→保存索引再利用は追加encode/再ロードなし。実queryで必要なworkerのみ再起動、全所有process-instance handlesの停止を確認。後処理の失敗が成功JSONにならないよう補強し、最終版を文章専用runで検証。
- Core **35 PASS**、Python profiles **10 PASS / 0.400秒**・retrieval **13 PASS / 5.003秒**、Release **PASS / 37.28秒 / errors0・既存IL2104 2warnings**。syntax/CLI/diff・手動レビュー済み、専用analyzer未実行。全Python155/scope12は前回履歴で今回未再実行。各GPU native初回PASS、失敗/再試行なし。
- physical keyboard/高DPI/Contrast/読み上げ・検索精度は今回未検証。私物/モデルDL/依存/OS変更/Layaなし。詳細・測定境界は[実GPU検索方法](search-methods-gpu.md)。CI manual-only・Draft未マージ。

### 次の3手

1. 高DPI/HighContrast/読み上げ・全面keyboardの独立確認。OS設定を勝手に変えない。
2. 未観測の固定品質入力とLaya日本語gateを別実験で準備。Laya既定無効を維持。
3. 読書/Komga/フォルダ本の仕様から次の小さなsliceを選ぶ。

---



## 最新：GUIの明示的なAI文章検索（2026-10-13）

開始HEAD **f792d6a334834f1f8281509e74bfeb940b06919d**。同じfeature/Draft PR #5/comparison baseを維持。今回の実装・検証・仕様commitは **03acb7598b41507632a24a594662336cb5768b52**。このSHA記録は文書だけの後続commit。通常push後の最終HEADとread-only CI観測はGit/PR head・PR説明で確認。

- 検索方法に「AI文章」（API source=text）を追加。「AI意味検索」は「AI混合」へ改称、既存index0/1/2とIDs/literal/all/coverは維持、textをindex3へ。種類・検索方法のvisible labelsと根拠説明を追加。名前・タグの意味だけを使い本文/音声は読まないことを表示。
- saved scope/coverage/filter/page/stale/dirty規約を維持。未保存のモード変更をcancelするとmode/query/kindとhint/placeholder/accessibility nameが同期して戻る。モデル/順位/自動routingは変更しない。session-only・初期literal。
- Core **35 PASS**、Python scope12 PASS / 14.098秒・retrieval13 PASS / 4.625秒、最終Release PASS / 30.23秒 / errors0・既存IL2104 2warnings。syntax/CLI/diff PASS。手動WinUIレビュー済み、専用analyzer未実行。全Python155は前回履歴で今回未再実行。
- native03 **65 checks PASS / 6 PNG全目視 / scoped visual PASS / 正常close2 / cleanup warnings0**、Light/Dark wide/narrow・DPI96/Contrast off。実HTTP/AISearch/Release GUI、生成PNG3/2root・隔離設定、CPU契約stub encoderで実GUI sourceとscope/kind/favorites/page0の要求20件、blank/literal復帰・dirty cancel/discard・source bytes/mtime/hashと設定byte不変を確認。実GPU/検索品質・physical keyboard・高DPIは今回未確認。
- native01/02はUIA peer失効/名前substring曖昧でFAIL、各2PNG全目視・正常close1。03まで2 fix cycles、失敗履歴は[検索方法](search-methods.md)。ignored artifacts/DB/私物/credentialsはcommitしない。CI manual-only・Draft未マージ。

### 次の3手

1. 小さな生成fixture＋実CUDAで新mode/nativeとtext-only profileのcover非対応案内を確認。
2. 高DPI/HighContrast/読み上げ・全面keyboardの独立確認。OS設定は勝手に変更しない。
3. 新規固定品質入力/Laya gateを別実験で準備。Laya既定無効、reader/Komgaは後続slice。

---

## 最新：text/pixel根拠別の新規固定評価 holdout v2（2026-10-13）

開始HEAD **7d7facc749103eaf7798a3d0345831fc4163fd33**。同じfeature/Draft PR #5/comparison baseを維持。入力/コードをGPU観測前commit **82427c528fcc273edb601cd62f69fe3c3251ab5e**で凍結し、結果後にqrels/queries/items・モデル・順位・GUIを変更しない。結果・テスト・仕様記録commitは **873bd5ad12a7c9684e3d6c81d93ffdc21d4f825e**。このSHA追記は文書だけの後続commitで、通常push後の最終HEAD/CI観測はGit/PR head・PR説明で確認。

- v2 SHA256 **021e0984797727c6a79c97fb588165ce49db7c4e12fcdb1f265e02a7793b08fa**、30素材（PNG12/CBZ6/灰SVG8/無音WAV4）・日本語30問・220相関行/160query推論。全18unique coversを推論前に目視。metadata/pixel/一致/誤タグ/filename/no-answerを別集計。external statistical holdoutや製品quality gateではなく、以後developmentとして扱う。
- 実CUDA `search-holdout-01` **runtime PASS / 258checks / index27.155秒 / document30/image18/query160**。元bytes/mtime/hash、frozen manifest/Git blob、検索前後vectors不変、所有handles3件全終了。私物/モデルDL/OS変更/Laya/GUI操作なし。
- 種類なしmetadata text12/12・combined10/12、pixel cover6/6・combined0/6・text0/6。一致4問はAI各4/4。kind指定metadata combined11/12だがpixel combined0/6。誤タグのpixel検索cover2/2・combined1/2、分類タグ検索text2/2・combined0/2。no-answerでもAIは最近傍候補を返すためconfidence/存在保証/閾値は未実装。詳細は[search-quality-holdout.md](search-quality-holdout.md)。
- 新規CPU5 PASS / 0.570秒、旧quality CPU5 PASS / 0.187秒、全Python155 PASS / 106.705秒、Core29 PASS、Release PASS / 40.75秒 / errors0・既存IL2104 2warnings。syntax/CLI/diff PASS。GUI source/nativeは今回変更/再実行なし、旧keyboard partial/DPI等の境界は維持。
- CLIは `--suite holdout-v2`、既定baseline-v1とv1 SHA/入力/結果を維持。任意のmanifest/private path入力はなし。評価DB/メディア/結果/weights/handle IDsはignoredでcommitしない。CI manual-only・Draft未マージ。

### 次の3手

1. GUIでtext-onlyを明示選択できるmodeを設け、混合/画像との違いを説明しnative検証する。自動routing/既定順位変更なし。
2. v1/v2以外の根拠を持つ新規固定入力で次の品質判断を行い、観測した小図形へfusionを過適合させない。
3. Laya日本語gateは別実験で再評価し既定無効維持。reader/Komga/高DPI/全面keyboardは別slice。


---

## 最新：検索可能なフォルダ選択・全文パス・疎な分布（2026-10-13）

開始HEAD **5b4ac4c79c3a012cea72ba2fdaf85acb68f6f716**。同じfeature/Draft PR #5/comparison baseを維持。実装SHAは後続提出記録/Git/PR headで確認。

- 全登録rootを名前/パスで絞り込み32件ずつ表示。256番目以後の未選択rootも新規選択可能。Coreで非表示の選択を保持し、256選択上限/空scope/JSON DOM/保存freeze・古い応答規約を維持。表示のみの変更はdraftを変更しない。
- 「パス」で読み取り専用・折返しの全文欄を表示。狭幅でも全文を目視。tooltip/32行native controlsを使用し、危険なmanaged ItemsSourceを再導入しない。
- Core29 PASS、全Python150 PASS / 101.163秒、Release PASS / 34.02秒 / errors0・既存IL2104 2warnings。手動WinUIレビュー済み、専用analyzer未実行。
- native03 **51 checks PASS / 6 PNG全目視 / scoped visual PASS / 正常close 2回**、keyboard=partial、cleanup warnings=0。 OSが所有窓の前面化を拒否した操作は入力せず、同じowned HWNDのUIAで機能確認を続行。keyboard_skippedへ明記し、全キーボード経路PASSとは扱わない。01ではSpace選択/Enterページ送りが観測済みだが途中失敗の別履歴。
- native01/02はforeground拒否でそれぞれFAIL16checks/2PNG・FAIL5checks/1PNG、全画像目視、owned PID終了fallbackを記録。03は生成901 metadata/75実PNG/258rootで検索・隠れた選択/保存/restart/未保存破棄・全文パスを確認しGPU未ロード。詳細とkeyboard/cleanup境界は[root-picker.md](root-picker.md)。
- 5万生成metadataの疎な2root分布（前方2/後方2/分散500）は最終CLI03 10checks PASS、ID順/件数/上限/元PNG不変。5回median/maxは詳細文書。私物走査/GPU索引/1TB性能保証ではない。
- CI manual-only・Draft未マージ。push後HEADのruns/checksをread-only確認してPR説明へ記録する。

### 次の3手

1. 高DPI/High Contrast/読み上げ・全面keyboardと大量root metadataの応答性を確認。
2. 新しいtext/cover holdoutを凍結して混合順位を評価する。
3. Laya日本語gate再評価、既定無効維持。reader/Komgaは別slice。


今回のフォルダ検索・ページ選択・全文パスの実装/テスト/仕様commitは **2c1b167310574c6b6d9530d01502d19d6f703ccd**。このSHA追記は同commitからの文書だけの後続commit。通常push後の最終HEAD・CIの読み取り観測はGit/PR head・PR説明で確認する。Draft未マージ・comparison baseを維持。

---

## 最新：5万件metadata・258フォルダのCPUと実GUI（2026-10-13）

開始HEAD **33e65d8acdea153af0b6d48d26c3f406f50adafe**。同じfeature / [Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5) / comparison baseを維持。今回の提出SHAは後続の提出記録/Git/PR headで確認。

- 50,000生成metadata＋実PNG75件・258登録rootの再実行可能なfixture/CPU計測/GUIモードを追加。残り49,925件に実メディアはなく、私物/1TBのfilesystem走査や実GPU索引ではない。
- 複数rootのkeyset SQLの反復sortを修正。この分布の256root件数取得5回中央値は14,221→1,410ms。ID順、除外、種類、先頭1万対象枠、256行reads、scope/モデル/キャッシュ契約を維持。
- root選択欄を最大160 DIPの標準ScrollViewerへ収め、258番目の保存rootへ到達できるよう修正。先頭256＋保存ID・最大512 controlsの境界は維持し未仮想化。未選択の256以後を新規に探すUIは未実装。
- 最終Python **150 PASS / 92.363秒**、新規3 PASS / 2.328秒、Core **19 PASS**、Release **PASS / 35.82秒 / errors0・既存IL2104 2warnings**。手動WinUIレビュー済み、専用analyzer未実行。
- CPU01/02各14 checks PASS。native01 FAIL（last root到達不可）/4 PNG目視/所有PID終了fallback、bounded viewport修正後native02 **45 checks PASS / 12 PNG全目視 / scoped visual PASS / 2正常close**。Light/Dark・wide/narrow・DPI96/Contrast off、5万件/834ページ・文字検索・grid・saved258 restart・全root件数/最大1万・保存、GPU worker未ロード、生成素材不変。
- 狭幅長パスは一部がscroll境界で切れるため全文同時可視性は未確認。native測定はCLI/UIA/waits/scrollを含みフレーム描画/純粋な操作応答とは異なる。DPI/keyboard/読み上げと疎なroot分布の評価は次へ。詳細・再実行・失敗履歴は[library-scale.md](library-scale.md)。
- docs/status・scope文書とPR説明を更新。CI manual-only・Draft未マージを維持。push後runs/checksをread-only確認し提出記録/PRへ反映する。

### 次の3手

1. 疎な複数root分布を計測し、多数rootの新規選択/全文表示・keyboard/高DPIを確認する。
2. 新しいholdoutを凍結してtext/cover根拠別に混合順位を評価する。既存品質v1はdevelopmentとして扱う。
3. Laya日本語gate再評価。既定無効を維持し、reader/Komga/フォルダ本集約は別sliceで設計する。


今回の実装・検証・仕様更新commitは **f440e5916579ce1f1b4e0daca331a00466f236eb**。この提出記録は同commitからの文書のみの後続commit。通常push後の最終HEADとCI runs/checks観測はGit/PR head・PR説明で確認する。Draft/base/main境界は維持。

---

## 最新：架空日本語の検索品質ベースライン（2026-10-12）

開始HEAD **15bb0c10ce71a2a6a8eb48135e4f03edfe4fef19**。同じfeature / [Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5) / comparison baseを維持。提出commitは後続記録/Git/PR headで確認。既存製品検索・モデル・順位・GUI・scopeを変更せず、再実行可能な診断評価だけを追加。

- 固定[manifest](../tests/fixtures/search-quality-v1.json) v1、SHA256 `94260e45459d539285d7cde257214cddc9c39263b454a15b8e3c3b1e2e15afa8`。生成26件（PNG8/CBZ6/SVG8/無音WAV4）、20文（semantic12/visual4/filename-control2/no-answer2）、種類あり/なし、literal/text/cover/allで130結果行。正解2/関連1のgraded qrels、Hit1/Best-grade1/Recall5/MRR/nDCG5、no-answerとfilenameを別集計。関連候補はkind/cover eligibilityへ射影する。実行前に凍結し観測後のtuningなし。
- `python tools/evaluate_search_quality.py --output data/ai-ui/search-quality-01`: **runtime PASS / 164入力・境界検査 / 実CUDA document26/image14/query90 / index19.802秒**。元byte/mtime/hash・検索前後vector bytes・manifest不変、所有process-instance handles3件全終了。既存venv/重みだけ、downloads/私物/OS変更なし。native GUIは今回起動しない。rank品質gateは未定義で、runtime passと品質合格を混同しない。
- semantic12文は種類指定text/combinedでprimary Top1 **12/12**。種類未指定textは関連12/12・primary11/12、combinedは10/12・Recall5=0.972・MRR=0.917・nDCG5=0.921。literalは0/12。combinedのs08（謎解き本）とs09（朝食本）は2位。全modeで同じquery文のvariantsは独立した130問ではない。
- visual4文は画像指定cover Top1 **4/4**、combined2/4・text2/4・literal0/4。種類なしcoverは関連4/4だが同一PNGのCBZ表紙がitem ID同点順で先に出るためprimary0/4（人工的なgrade差）。正解PNG4枚目視、定義した色/形/白背景を確認。filename exactはliteral2/2・AI1/2。no-answer2問でもAIは候補を返すため、confidence/共通閾値/存在保証は未実装のまま。
- SVGは同一灰矩形＋用途を示す架空タグ、WAVは無音＋架空タグで内容理解の証拠ではない。CBZ表紙も単純図形で物語はmetadataだけ。今回のmixed-kind順位の弱点を実本全体へ一般化しない。PyTorch peak allocated931.8MiBは総VRAMでない。今後この20文はdevelopmentとして扱い、改善判定は新しいholdoutで行う。
- metrics/fixture契約 **5 tests PASS / 0.161秒**。全Python **147 tests PASS / 86.923秒**。Python構文/CLI/diff確認PASS。前回C#19・Release35.75秒/IL2104 2warnings・native133/31PNG等は過去の証拠で再実行なし。詳細は [search-quality-baseline.md](search-quality-baseline.md)。
- CI manual-only・Draft未マージを維持。push後実HEADのruns/checksをread-only確認しPR説明へ記録。旧失敗履歴は以下に残す。

### 次の3手

1. 多数の生成metadata・長いrootパス・scope上限とGUI応答性を評価。大量root選択、DPI/keyboard/accessibilityの未検証部分を段階的に確認する。
2. 新しいholdoutを先に凍結し、text/coverそれぞれの根拠がある素材で混合順位を評価。v1の結果へ過適合する重み/閾値変更や自動routingはしない。
3. Layaの日本語品質gateを再評価し合格前は既定無効を維持。reader/Komga/フォルダ本集約は別sliceとして設計する。


今回の実装・評価・文書commitは **83b6ca2be8551543e25f0ccb4d68f46187cead1a**。この追記は同commitを開始HEADとする後続commitで、manifestのGit LF属性と固定SHA256検査も含む（Windows改行変換でも入力の同一性を保持）。同じDraftへ通常push。最終HEADとpush後CI観測はGit/PR head・説明で確認。

---

## 最新：AI対象選択GUI・設定保存・再起動確認（2026-10-12）

開始HEAD **ba9e1ee7474e8ea91e1f48ac7d4fe3dc6e9fdb02**。同じ `feat/winui3-production-mvp-20261011` / [Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5) / base `feat/gui-framework-comparison-20261010` を維持。提出commitは後続の提出記録または実Git/PR headで確認。下の旧結果・失敗履歴は当時の記録として保持する。

### 実装と操作

- WinUIの「AI索引」→「AI検索と索引の対象」で登録フォルダ・種類・棚を選択し、「件数を確認」→「保存してAI検索に適用」。候補/最大10,000件の対象枠/文字索引/残りを分けて表示。保存された同じscopeをAI検索と次の索引に明示送信する。文字検索と一覧kind/viewは独立。現在進行中または過去のjob進捗は「索引処理（開始時の対象）」と表示。
- 新GET/POST `/api/library/ai/scope` とローカルuser preferenceを実装。旧profile-only設定は互換の全登録root。profile/resource/scopeは同じ所有lockとatomic replaceで更新し、互いの保存値を保持。設定上限16KiB、明示root配列最大256。job scope保存とは別のユーザー設定。範囲の変更はモデル/索引の削除・hot swapを行わない。
- 件数確認後のdraft変更は再確認が必要。未保存で閉じるとdraft破棄、保存中は編集と閉じる操作を抑止、scan/AI索引中の保存は409。非同期の古い件数応答・閉じた画面への反映を防止。通信エラー時は保存設定を読み直し、要求値/前の値と一致する場合だけ採用し、不明ならAIを止めて確認・再保存を促す。製品の自動書込みretryは行わない。
- `[]`はゼロ件。削除済みrootは警告・明示修復を求め、全rootへ復帰しない。scope単体の破損もAIを止めて選び直せる。JSON全体/基礎設定が破損した場合、scope保存だけでは修復できずモデル選択の保存または設定ファイル修復が必要。モデル選択による全体修復はscopeを空にする。文字検索は独立。
- reflection無効でも動くJSON DOM/deep cloneを維持。native ListView/ItemsWrapGrid、60件paging、metadata editorのdirty/stale規約、既存assets/比較アプリは維持。個別root表示は先頭256と保存済みID（最大512 controls）で、root一覧は未virtualize。大量rootと長いパスは今後評価。

### 今回の検証と失敗履歴

- `python -m unittest discover -s tests -q`: **142 tests PASS / 96.724秒**。settings13 / scope12を含む。atomic保存失敗で旧bytes保持、同時resource/scope保存、restart、token/Origin、busy/空/削除root/不正型をCPUと実HTTPで検証。後の変更はC#/native harnessのみ。最終Python構文とCLI helpもPASS。
- `dotnet run --project tests/Aredoko.Core.Tests -c Release --no-restore`: **19 checks PASS**。初期はgeneric JsonArray.Add(int)がreflection無効で実行時失敗。primitive JsonValueを明示JsonNode castして非generic overloadへ修正し、抑制なしで新規IL2026も解消。
- x64 SelfContained Release最終build05 **PASS / 35.75秒 / 0 errors / 既存SDK/WinRT IL2104 2 warnings**。初回はStackPanel.IsEnabledの誤用でFAIL、各Controlの無効化へ修正。build04はPASSだが最終製品差分の結果は05を使う。manual WinUI review実施（async/ownership/theme/IDs/JSON/authentication/bounded controls）。専用analyzer未導入・未実行、日本語固定文言/MVVM全面移行/AOTは別工程。
- `scope-native-01`: functional **101 checks PASS / 22 PNG / 3正常close / source hash不変**。目視はLight-A-selection/countsの2枚だけで全体visual合格とは扱わない。その後狭幅・restart実検索・削除rootを追加。
- `scope-native-02`: **FAIL / 49 checks / 12 PNG / source hash不変**。Light-Bの保存通信が失敗し旧A設定が残った。保存成功待ち5000ms timeout、原因未確定でbackend tracebackなし。目視はLight-narrow-A-selection/counts、Light-A-saved、failureの4枚のみ。cleanupには所有test PID停止fallback warning。保存応答を読み直す製品処理と15秒待機・失敗観測後だけの明示GUI retryを追加。失敗を成功扱いしない。
- `python tools/test_ai_profile_ui.py --editor-only --scope-checks --output data/ai-ui/scope-native-03`: **133 checks PASS / 全31 PNG目視 / 対象範囲のvisual PASS / 4正常close / cleanup warningなし / retry観測なし**。isolated DB/settings、生成17+2 files/2 roots、既存EG2実CUDA・GUI text-only profileでA/B各audio2件のindex/query、保存・profile/resource保持・Dark restart後B実検索、Light/Dark幅1200x800と700x620、解放後A cached rebuildで未ロード、A/B4文字vector bytes不変。空scope・消えたrootでAIを広げずGPU未ロード、文字検索は動作、消えたIDを明示解除して空へ修復。消失はisolated catalog内だけのfault injection。元source bytes/mtime/hash不変、生成profile/所有processをcleanup。既存重みのみ、ダウンロードなし。
- PNGの設定欄はスクロール領域で別captureにより選択欄/件数/保存feedbackを確認。status/start/cancel/closeは固定で読み取れる。一部検索captureのCtrl+F tooltipと追加HWND縁はharness artifact。今回DPI/Contrast状態は計測していない。ネット応答喪失のreadback分岐は専用fault injection未実施で、native03では自然失敗なし。visual-review.jsonは各ignored実行フォルダに残す。
- 前回native182/29PNG、scope CUDA15（表紙あり）、GPU10k126/HTTP28/解放CUDA30は**過去の結果**で再実行なし。1TB私物、別checkpoint、検索順位品質、総VRAM/ゲームFPS、高DPI/HighContrast/screen-reader、AOT/installer/reader/Komga/OCRは未検証または未実装。Layaは日本語品質gate未達で既定無効の実験API。
- Hosted CIは未実行。既存3workflowはworkflow_dispatchのみを維持し、手動dispatch/課金/runner設定変更なし。push後に実HEADのruns/checksをread-only確認し、結果はPR説明に記録。Draftのまま未マージ。

### 次の3手

1. 架空日本語の検索品質セットを整備。名前一致だけに頼らない期待意図・正解候補を固定し、文字/表紙/combinedの順位を比較する。私物1TBの評価とは分ける。
2. 多数の生成metadata・長いrootパス・scope上限、GUI応答性とDPI/keyboard/accessibilityを評価。必要に応じroot選択の仮想化と表示設定永続化を検討。
3. Layaの日本語品質gateを再評価し、合格条件が揃うまで自動routingを既定有効化しない。reader/Komga/フォルダ本集約は別sliceで設計する。


今回の実装・テスト・文書commitは **2a42b3acaddd943e9fbf51c62de13043022207cc**。この追記は同commitを開始HEADとする文書のみの後続commit。同じDraft PRへ通常push。正確な最終HEADとpush後のread-only CI観測はGit/PR head・PR説明で確認する。

---

## 最新：グリッド実機確認・AI対象選択API/GPU・自動CI抑制（2026-10-12）

開始HEAD **d635c980199e3c6fafb093576127f88ff31a0385**。同じ `feat/winui3-production-mvp-20261011` / [Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5) / base `feat/gui-framework-comparison-20261010` を維持。未マージ。提出commitは後続の提出記録と実Git/PR headで確認する。以下が今回の実装・検証で、下の旧失敗履歴を上書きしない。

### 実装

- ユーザーのグリッド表示希望を反映。既存のタイル表示は安全なnative `ListView` + `ItemsWrapGrid` で既に実装されていたため、切替ボタンを「グリッド表示」/「リスト表示」と明確化。60件paging・画像/CBZ/ZIPの限定プレビュー・キャッシュ・選択復元を維持し、managed ItemsSourceを再導入しない。表示設定のrestart永続化は未実装（今はセッション内）。
- 登録済みroot ID・種類・完全一致の棚でAI対象を指定する **CPU/API sliceを実装**。新 `POST /api/library/ai/coverage` はモデルを起動せず候補/対象枠/fresh/残りを数える。index/searchに任意scopeを追加。`[]`はゼロ件、未登録/削除済みID・不正型・未知キー・明示scope:nullは400、勝手な全root復帰なし。token/Origin・読み取り専用sourceを保持。
- scopeで絞り、present・除外適用後、ID順の最大10,000件が共通対象枠。追加の検索kind/viewはその枠の後に適用。省略scopeは従来の互換経路。256行keyset読み取り、count側も全候補をメモリに保持しない。候補件数は上限前、freshは同一profile/revisionのtext vectorレコード数で、表紙成功/品質/破損vector検査とは区別する。
- job開始時にscopeをコピーし進捗/ai_stateへ保存、処理・publish前にも範囲/presence/除外/revisionを確認。job scopeはrestart後も残る。同じmodel/vector identityを維持し、対象を切り替えても他範囲のvectorを削除しない。**GUI選択欄・ユーザーscope設定の永続化はまだない**。過去job state保存とユーザーの次回対象設定保存を混同しない。
- `.github/workflows` の3本は一時的に **workflow_dispatchのみ**へ変更し、自動push/PR起動の重複通知を抑制。jobs/stepsを保持、課金・上限・runner・通知設定は変更しない。ユーザーが課金しなくてもローカル開発は続けられる。default branchへ未マージなので手動Run workflowボタンの表示は未確認。CI PASSとは扱わず、手動dispatchもしていない。

### 今回の検証

- `resource-native-07`: **FAIL / 57 checks / 9 PNGすべて目視**。旧20px最低高さでは実際の完全な19px Text peerも拒否。最初の1px断片は正しく拒否され、スクロール後の全19pxが実測された。19pxを許可する観測回帰を追加（UI geometry 9件）。3正常終了＋所有test PID停止1回のwarning。全体visual PASSではない。
- `python tools/test_ai_profile_ui.py --output data/ai-ui/resource-grid-native-08 --editor-only --layout-checks --appearance-checks --coverage-checks --resource-checks`: **182 assertions PASS / 29 PNGすべて目視 / scoped visual PASS / 9正常終了 / cleanup warningなし / source hash不変**。生成17件、専用DB/settings、DPI96・Contrast OFF。既存EG2の生成GUI用text-only profile。グリッドはDarkで1200px広幅4列、700×620px狭幅2列、表紙・選択・詳細・リストへの復帰を実確認。Light/Darkのリソース保存/解放メッセージ全文、restart値、文字検索復帰・未保存編集・お気に入り・folder dialogを確認。scroll contentの全項目が常に同時表示される保証ではない。一部PNGのCtrl+F tooltip/別HWNDの端はharnessのcapture artifactとして記録。
- 07→08は今回1修正再試験。06の1px誤判定/visual未合格を08で解消したが、過去runの結果はそのまま残す。ignored各runの `visual-review.json` に目視範囲/結果を記録。19px guardは96-DPI単行用で、他DPI・折返し全文を保証しない。
- 新しいscope CPU **11 tests PASS / 8.818秒**。2 roots、空/不正/削除ID、棚のSQLパラメータ、missing/exclusion、同一cap、scope切替reuse、job中のscope変更/publish再検査、263件の256+7行freshness集計と60件paging、restart/auth/Originを確認。HTTP null本文を修正後 **11 tests PASS / 8.731秒**。偽encoderのみで意味品質試験ではない。
- `python tools/test_ai_scope_gpu.py --output data/ai-ui/scope-gpu-01`: **実CUDA 15 checks PASS**。生成6ファイル/2 roots、選択したPNG4件のみdocument4/image4/query3、text/cover queryが指定rootを越えない、scope切替cache再利用・vector digest/model key/path不変、job scope restart復元、restart count/cached rebuildでworker未ロード、所有process-instance handle **3件全終了**、source byte/mtime/hash不変。検索順位の品質保証ではない。既存重み/環境だけでダウンロードなし。
- 全Python **137 tests PASS / 88.077秒**。C# `dotnet run --project tests/Aredoko.Core.Tests -c Release --no-restore`: **15 checks PASS**。WinUI x64 SelfContained Release **PASS / 33.58秒 / 0 errors / 既存IL2104 2 warnings（抑制なし）**。最終nullテスト修正後はscope11件だけ再確認、全suiteの結果と区別する。
- WinUI manual review: 今回のproduct UI差分は文言のみ。native Items/ItemsWrapGrid/60 paging、async stale/dirty/selection、theme/accessibility IDs、JSON DOM、認証/所有worker境界を再確認。専用analyzerは未導入・未実行。日本語固定文言・MVVMの全面移行は別工程。Release JIT成功はAOTの検証ではない。
- GPU10k126/HTTP28・専用解放GPU30は**以前の検証**で今回再実行なし。1TB/私物、ANN、別checkpoint、総VRAM/ゲームFPS、高DPI/HighContrast/screen-reader/AOT/installer/Komga/reader/OCRは未検証または未実装。Layaは品質gate未達で既定無効の実験API。

### 次の3手

1. [AI対象選択の契約](ai-coverage-selection.md)をWinUIのAI画面へ接続。登録root/種類/棚を明示選択し、CPU件数を表示、dirty/stale/busyを守って同じscopeをindex/searchへ渡す。文字検索は独立のままにする。
2. ユーザーのscope preferenceをprofile/resourceと同じatomic設定更新規約で保存。削除済みrootは通知・再選択、全rootへfallbackしない。job state保存と区別してrestart・同時保存をテストし、Light/Dark/狭幅を実操作・全PNG目視する。
3. 架空日本語検索の品質セットを整備し、表紙/文字/種類の評価を進める。Layaの品質gateを再検討するが、自動routingを既定有効化しない。CIは自動起動を抑えたままローカル検証を続け、必要時だけ無料枠/制限を確認して復帰する。

今回の実装・検証・文書の提出commitは **893bb08014ba31936b78e055059a813c20116f8f**。この追記は同commitを開始HEADとする文書のみの後続commit。同じDraft PRへまとめて通常pushし、正確な最終HEADはPR head / `git rev-parse HEAD` で確認する。


---

## 最新：リソース操作155項目確認・1px誤判定を特定・CI停止原因判明（2026-10-12）

開始HEAD **e3caae44c38f4d3c602e1b1075add2bee9cd5c53**。同じ `feat/winui3-production-mvp-20261011` / [Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5) / baseを維持。今回の変更はnative試験helper、回帰テスト、文書のみ。製品C#/XAML/API、model/vector identity、10,000件上限は変更していない。

### 今回の結果と残っている表示問題

- `resource-native-04`: **FAIL / 36 checks / 6 PNGすべて目視**。WindowsがStartAIIndexへのforeground focusを拒否した。所有HWNDの標準UIA Invokeで実ボタンのClick handlerを呼ぶ形へ修正し、設定操作の不要なfocusを除いた。3正常終了＋所有test PID停止1回のcleanup warning。
- `resource-native-05`: **FAIL / 55 checks / 9 PNGすべて目視**。設定操作に時間がかかり、保存した60秒idle policyがworkerを解放し、手動解放ボタンが無効だった。生成fixtureの明示queryでworkerを準備してから手動操作を試験する順序へ修正。3正常終了＋所有test PID停止1回のcleanup warning。
- `python tools/test_ai_profile_ui.py --output data/ai-ui/resource-native-06 --editor-only --appearance-checks --coverage-checks --resource-checks`: **155機能assertions PASS / 23 PNGすべて目視 / 8正常終了 / cleanup warningなし / source hash不変**。Light/Dark、700×620px、DPI96・Contrast OFF、生成17件・専用DB/settings。旧profile-only設定から開始し、60秒/50ms保存、manual release後のresident/device/telemetry消去、GUI意味検索による実CUDA再ロード、restart後の保存値とlazy unloaded状態、文字検索復帰・未保存編集・お気に入りを確認。既存EG2重みのGUI用text-only profileで、別checkpointの試験ではない。
- **全体のvisual PASSではない**。06の `23-Light-resource-released.png` / `23-Dark-resource-released.png` には解放メッセージが写らない。UIAは両方で `IsOffscreen=false` だがText peerのheightが**1px**だった（Light y340 / fixed heading y353、Dark y392 / fixed heading y405）。正の高さだけを許可したhelperが、スクロール下端の断片を可視扱いしたと特定。restartの1分/50msの選択値は両テーマで実際に映るが、スクロール途中でheaderが外れる画像もある。
- `tools/ui_geometry.py` を追加してTextに最低20px、Button/ComboBoxに最低32pxを要求する96-DPI試験guardへ修正。実測のLight/Dark 1px例、上下clip、offscreen、無効buttonの可視性など **CPU回帰8 tests PASS**。**この最終guardを使用したnative再実行はまだ行っていない**。多行Textや他DPIを含む完全可視保証ではなく、画像の目視は引き続き必要。
- winui-ui-testing SKILLの **Maximum two fix-and-rerun cycles** に従い、今回04→05→06の2修正再試験で停止。ignoredの各runに `visual-review.json`（visual_pass=false）を保存し、機能PASSを表示合格へ読み替えない。所有GUI/APIの正常終了は06の結果で確認、04/05のfallback履歴を残す。
- 前回の実GPU専用30 checks、Python117 tests / C#15 checks / SelfContained Release（IL2104警告2件）は過去の検証結果。今回製品コードは変えていない。WinUI manual code reviewでasync dialog配線、JSON-DOM、テーマ資源、Name/ID、busy/releasing guardを再確認。専用analyzerは未導入・未実行。GPU10k126 checks / HTTP28、総VRAM/ゲームFPS、1TB/私物、HighContrast/高DPI/AOT/installerを今回確認したとは扱わない。

### GitHub CIの原因

開始HEAD e3caae4のcheck-run annotationsを認証済みGitHub APIで読んだ。**最近の支払い失敗、または利用上限の引上げが必要なためjobが開始されなかった**というGitHub側の注釈を、PRとpush両方の全4ジョブで確認した。コードのテストが走って落ちた証拠ではなく、CIは合格していない。

- [owned-worker CPU](https://github.com/jakymiku/Aredoko/actions/runs/38241656866/job/114785481774)
- [Prototype tests](https://github.com/jakymiku/Aredoko/actions/runs/38241656890/job/114785481991) / [browser smoke](https://github.com/jakymiku/Aredoko/actions/runs/38241656890/job/114785482614)
- [AI profile/build](https://github.com/jakymiku/Aredoko/actions/runs/38241656885/job/114785481732)

ユーザー側でGitHubのBilling & plansを確認する必要がある。支払い/利用上限の変更、有料runner、CIの不要な再実行は行っていない。既存認証情報は読み取り要求のためだけにメモリ内で扱い、出力・ファイル・commitへ保存していない。古いHEADの取得不能logの原因を同じと断定せず、その履歴は下に保持する。

### 次の3手

1. 修正済み最低高さguardを使う新しい生成native runで、解放メッセージが完全に映るLight/Dark PNGを取得する。まず23の1px誤判定を解消し、固定status/start/cancelと各設定値の表示を目視する。現時点で製品layout故障とは断定しない。
2. [AI対象選択の仕様案](ai-coverage-selection.md)に沿って、登録root/種類/棚と候補件数のCPU/API sliceを実装する。**仕様案のみで未実装**。scopeをmodel identityに入れず、10,000上限・cache再利用・token/Origin・登録同意を維持。scopeありではindex/searchの同じ対象枠へ検索filterを適用し、検索だけ別の先頭10,000件を選び直さない。
3. 対象選択を生成少数件の実CUDA/WinUIへ接続し、架空日本語検索の品質セットを進める。Layaは精度gate未達の既定無効実験API。実素材走査/移動、Komga、OCR、folder-to-bookを勝手に追加しない。CIの再確認はユーザーのGitHub account制限解消後。

`python -m unittest discover -s tests -q`: **125 tests PASS / 79.968秒**。新しいUIA回帰8件を含む既存CPU/API/scanner/settings/owned-worker全体。CLI rate範囲外テストの想定argparseエラー出力を含むがsuiteはexit0/OK。native helper/geometry/testのPython構文も確認。C#契約とReleaseビルドは製品コード未変更のため今回再実行せず、前回結果を区別して保持。実装・検証・仕様の提出commit **05f4ba3c4a1defb615cd56f7ecf1af743778e9b9**。この追記の作成時HEADも同値。後続の文書追記commitを含む正確な最終HEADは `git rev-parse HEAD` / PR headで確認する。

---

## 最新：Chat分を取り込み、AI解放GPU合格・GUI機能確認、表示検査は未完（2026-10-12）

再開前ローカルHEAD `753ae518b58a2fb97d5e8cc0e353909396e76697`、Chat提出HEAD `e63a5f955459f29e1b6082d44ecc3b21b1a69189`。同じ `feat/winui3-production-mvp-20261011` / [Draft PR #5](https://github.com/jakymiku/Aredoko/pull/5)、base `feat/gui-framework-comparison-20261010` を保持し、Chatの29コミットをfast-forwardで取り込んだ。以下は今回の新しい確認。旧GPU10k 126 checks / HTTP28は今回再実行していない。

### 修正したこと

- resource設定を保存してから動作中のpolicyへ反映する。壊れたJSONや書き込み失敗は409、動作中の設定を維持。profile/resourceのread-modify-writeを同じsettingsインスタンスのlockで直列化し、同時保存で片方が失われることを防ぐ（別プロセス間の排他を保証する設計ではない）。
- idle timerの事前確認後に検索が完了したり設定が無効化された場合、inference/guard内でidle条件を再検査して誤解放を防ぐ。
- WinUIの新ComboBoxに読み上げName/選択肢ID、設定パネルと固定行にUIA ID。保存中は選択を固定し、解放中のtimer更新でボタンを再有効化しない。モデル・catalog・vector identityを変更しない。

### 実行した確認

- `python -m unittest discover -s tests -v`: **117 tests PASS / 73.187秒**。保存失敗時のpolicy不変、profile/resource同時保存、idle条件再検査の回帰を追加。C#契約 **15 checks PASS**。
- x64 SelfContained Releaseビルド **PASS**。既存のSDK/WinRT IL2104 **2 warnings**を保持、無効化していない。WinUI manual code review実施（async/dialog配線、JSON-DOM、token/Origin、native行、テーマ、操作ID）。WinUI専用analyzerは未導入のため未実行。日本語固定文言、多言語化/AOT/installerは今後。
- `python tools/test_ai_release_gpu.py --output data/ai-ui/resource-gpu-02`: **30 checks PASS**。既存EG2既定text+cover/auto-bf16/768、生成17件、document17 / valid cover12 / damaged image skip1 / query4。手動解放→所有launcher/実worker終了→query再ロード、query guardを試験gateで保持した重複releaseの即時409、1秒idle自動解放→再ロード、source/vector hash不変、再索引なしを確認。所有process-instance handle **9件すべて終了**。
- query再ロード **10.55秒 / 12.41秒**（手動後/idle後）、PyTorch peak allocated **931.8MiB**。これは総VRAM量でもゲームへの影響測定でもない。プロセス終了は実測したが、他アプリを含む総VRAM/物理メモリの減少量は測定していない。
- `python tools/test_ai_profile_ui.py --output data/ai-ui/resource-native-02 --editor-only --appearance-checks --coverage-checks --resource-checks`: **機能の153 assertionsは通過**。Light/Dark、700×620px、DPI96/Contrast OFF。60秒/50ms保存、手動解放後のresident/device/telemetry消去・ボタン無効化、実CUDA再検索、restart後保存値復元とlazy unloaded状態、既存17件検索/dirty/favoritesを確認。**8回正常終了 / cleanup warningなし**。旧profile-only設定から開始。GUIは生成テスト用text-only profile、別checkpointではない。**23枚すべて目視した結果、解放メッセージとrestart選択値の撮影時のスクロール位置が不十分で、GUI全体のvisual PASSとは認めない。**
- 厳格化した `resource-native-03` は **FAIL / 44 assertions後 / 8枚すべて目視**。`AIIdleRelease cannot be brought into settings viewport`。WinUI ScrollViewerのUIA boundsはcontent extentを含み、Grid/StackPanelはIDだけではUIA peerを生成しないため、固定パネルIDを探すテスト側が失敗した。観測済みTextBlock peer（dialog title / 現在のAI索引）でviewportを挟むようhelperを静的に修正・構文確認したが、**この最終helperは実画面再実行していない**。新GUIの完全可視検査は次回優先。03のcleanupは3回正常終了＋失敗時の所有test PID停止1回（warning）で、02の8回正常終了と混同しない。
- 試験履歴: `resource-gpu-01`は計測器が破損PNGの正常skipを例外にしたためFAIL→計測器のみ修正。`resource-native-01`はスクロールしない可視検査でFAIL、02は構造化検査通過後に目視で不足発見、03は上記FAIL。winui-ui-testing SKILLの「Maximum two fix-and-rerun cycles」に従い今回は再試行を止めた。失敗をPASSに読み替えない。
- 生成データ/DB/settings/モデル/log/画像はgitignore下、個人AppData/素材は未使用。既存runtime/weightsのみ、DL/依存変更なし。

### GitHubと次の3手

実装・検証提出コミット **84535632f4b261e57389ee78c9d0f6e3cae74329** を通常push済み、Draft PR #5更新済み。後続の文書コミットを含む正確なHEADは `git rev-parse HEAD` とGitHubのPR headで確認する。

提出8453563のCI最終状態も取得: [owned-worker CPU](https://github.com/jakymiku/Aredoko/actions/runs/38241308142)、[Prototype checks](https://github.com/jakymiku/Aredoko/actions/runs/38241308023)、[AI profile/build](https://github.com/jakymiku/Aredoko/actions/runs/38241308108) は **すべて completed/failure**。4ジョブのstep/log URLがnull、CPU job log取得はBlobNotFound404。**原因不明、CI合格ではない**。課金・runner・コードのどれが原因かはこの証拠だけでは断定できない。文書のみの後続HEADのCIは未確認。

Chat HEAD e63a5f9のActions: AI profile/build checks成功、prototype testsジョブ成功。owned-worker CPUジョブとbrowser-smokeはfailure、step/logは取得不能（Azure Blob404）で原因未確定。ローカルの上記PASSと区別する。今回の提出HEADのCIは最終ジョブを別途確認し、未確認の成功を推測しない。

1. 修正したviewport helperで新しい生成テストrunを行い、AI解放メッセージ/各選択値が実際に映るLight/Dark画像と設定復元を確認する。03の失敗はテストpeer探索の問題であり、製品レイアウト故障とはまだ断定しない。
2. 現在HEADのGitHub CI最終状態を確認し、実行前failure/log欠落なら原因を特定する。ローカルPASSをCI成功と混同しない。
3. 上記の確認後に、10,000件超へ向け明示root/種類/棚とcoverage選択の仕様、架空日本語品質評価を進める。既存上限は維持。個人サンプル/1TB、Komga、OCR、folder-to-book、ゲームFPS、高DPI/Contrast/AOTは未検証。Layaは精度gate未達の既定無効実験APIを維持。

---

## Chat担当時点：所有AI workerの解放と選択式リソース設定（履歴）

開始HEAD **753ae518b58a2fb97d5e8cc0e353909396e76697**。**同じ`feat/winui3-production-mvp-20261011` / Draft PR #5（base `feat/gui-framework-comparison-20261010`）に追記。** 最新の機能実装コミットは **284fc5883db6edd0c0d3cf1dfd9b13c9f3baed80**（cache待機修正・WinUI変数初期化順を含む）。この引継ぎドキュメント以降の正確なHEADはGitHubで取得する。

### 変更したこと

1. `app/ai_process.py` は`EncoderProcess.release()`を追加。**自身が所有するアイドル中のsubprocessのみ**を停止し、device/telemetryを消去。次のencodeで同じprofile/重みを再ロードできる。対して`close()`は永続終了フラグとlockで再起動を禁止する。`_stop()`は元ファイル/VectorStoreには触らない。
2. `app/ai_search.py`: 既存の`inference` guard共有、検索/索引worker生存中の解放を即時`AIBusy`、closeとstart/searchの競合防止。statusに`resident/worker_state/resource_policy`を追加。自動解放は**既定0秒（無効）**で、`time.monotonic()`から処理後のアイドル時間を測り、`Event`で終了する。索引待機は**既定0ms（無効）**で**新規推論後のみ**`cancel.wait`を用い、保存済みベクトルだけを再利用するcache rebuildや検索には適用しない。
3. `app/production_server.py`: 既存localhost/token/Originを使った`POST /api/library/ai/release`（本文`{}`、Busyは409）、`GET/POST /api/library/ai/resource`（`{"idle_release_seconds":0..3600,"index_pause_ms":0..2000}`）。失敗時AIだけエラー、文字検索を保持。
4. `app/ai_settings.py`: `settings.json`の`resource`設定を原子的に保存。**従来のversion1/profileのみのJSONにも後方互換**。`profile`選択/adapter/model identity/旧vectorキャッシュと独立。GUIの変更は即時に有効で、再索引不要。
5. `src/Aredoko.WinUI/MainPage.xaml.cs` の既存「AI索引」ダイアログで、**「AIをメモリから解放」**、自動解放0/1/5/15分、索引待機0/50/200/500/1000msの選択・保存、現在の待機/常駐表示。元の索引status/start/cancelは固定領域に維持。利用可能な既定設定でも元ファイル/索引は削除しない。Layaは今回未変更の既定無効実験API。

### テスト・検証を混同しない

- CPU専用`tests/test_ai_release.py`: 偽encoder/所有subprocess、解放→再検索、VectorStore行不変、検索・索引のbusy、close後再起動禁止、timer/索引待機キャンセル、API token/Origin/不正値、文字検索。**[Actionsの専用CI](https://github.com/jakymiku/Aredoko/actions/runs/38233333368) PASS。**
- `tests/test_ai_settings.py`: 古いprofile-only JSON、保存後のprofile切替でresource維持、型や範囲外拒否。その他既存AI/GUI比較コードを変更せず。**WindowsフルCI/WinUI Release結果は各Actionsの最終ジョブで確認すること。**
- 並列CI環境で以前の`test_ai_scaling.py`の2,105件CPU索引が60秒以内に終わらず失敗したため、**テスト用join上限だけ180秒**へ調整。製品のworker推論タイムアウト/対象上限や既存テストの正当性判定は変更しない。
- ビルド履歴: 追加WinUI GUIの初回CIでlocal変数 `polling` の未初期化参照 CS0165 を検出。`polling` と `indexLimit` をイベントハンドラ登録前に移動。**修正後WinUI Releaseの最終結果は最新Actionsで確認する（未実機検証）**。
- **今回やっていない**: 以前PASSした実GPU 10,000件126項目・HTTP 28項目の再実行、実VRAMの解放量測定、Windows実画面の新AI dialog操作、一般検索精度/別checkpoint/1TBや個人メディア走査。GPU/FPS上限は保証しない。新たなモデルや依存DL・OS変更なし。元ファイル不変、mainマージ/force pushなし。

次の3手: (1) 生成素材の実GPUでquery→解放→所有worker消滅→再queryとベクトルhash確認、(2) Windows実画面でAI dialogのLight/Dark・狭幅・busy表示と設定保存・旧profile JSONを確認、(3) 未検証の1万件超の対象root/種類/棚/coverage設計と架空日本語品質セットを検討（上限は撤廃しない）。

---

更新: 2026-10-12。旧Web試作段階の引継ぎを置き換える。**製品GUIはWinUI 3に決定済みで、EmbeddingGemma 2検索まで実装・実GPU検証済み。最初から作り直さない。**


## 大きめ生成素材で実GPU1万件・HTTP検索確認（2026-10-12）

開始HEAD **44ecd51**。実装/結果コミット **82134643ce11018919048094f779e569f77ec148**。後続は提出文書のみ、最新HEADは実Gitで確認。同じfeature/Draft PR #5/baseを保持。`gpu-large-10k-01`は**126 checks PASS**、既存default EG2/text+cover/auto-bf16/768次元で実CUDA索引。生成10,000件（架空WAVメタデータ9,062、PNG625、1ページCBZ313）。cover938枚は768×768px、tag30個×60文字、実encoderの文字入力1865..1881文字とPNG寸法を記録・検証。

| 段階 | 保存済み件数 | 新規文字推論 | 新規表紙推論 | 秒 |
| --- | ---: | ---: | ---: | ---: |
| index-64 | 64 | 64 | 6 | 21.67 |
| index-256 | 256 | 192 | 18 | 24.71 |
| index-1024 | 1,024 | 768 | 72 | 94.12 |
| index-2304 | 2,304 | 1,280 | 120 | 156.50 |
| index-5000 | 5,000 | 2,696 | 254 | 300.62 |
| cancel-10000 | 5,096 | 96 | 9 | 14.51 |
| resume-10000 | 10,000 | 4,904 | 459 | 567.52 |
| fresh-restart-cache | 10,000 | 0 | 0 | 10.47 |

5,000既存+96新規で中断し、新encoder/AISearchから残り4,904件だけ推論。最終text10,000/cover938、累計document10,000/image938/query21で重複文字/表紙推論なし。fresh cache buildでは推論0・worker未起動、その後のqueryのみCUDAロード。元source bytes/size/mtime digest不変、所有9 process-instance handles全終了。

10,000件の単発検索: text 1.98秒（10,000候補） / cover 0.99秒（938候補） / all 1.89秒（10,000候補）。warm/cold等の条件はresult phasesで区別する。最初のbuildと再開buildはlazy model load込み、cached後最初のqueryは再ロード込み。一般的な検索精度の合格率ではない。

build RAMの0.2秒sample peak: controller **101.2MiB working set**、所有worker tree **2049.9MiB working set**、同tree private commit **5330.1MiB**。private commitを全て物理RAMとして足さない。torch CUDA lifetime max allocated **994.0MiB**（reserved/context/他アプリ/ボード総VRAMを含まない）。baseline `NVIDIA GeForce RTX 4070 Ti, 616.64, 12282 MiB, 3069 MiB, 15 %`。単発・他GPU利用ありで独占benchmarkではない。

`test_index_gpu_api.py`で完了済みの生成1万件のみを受け付け、製品loopback/token/Origin APIを専用processで確認。**28 checks PASS**: 60/60/40/0件のページ0/1/166/167、重複しないページID、画像625件、cover938件、ID1と10000のお気に入りをHTTP更新→検索で2件。変更はfinallyで元に戻し、vector/source/benchmark result digest不変。query7回のみ、文書/画像推論0、所有3 process-instance handles全終了。HTTP controllerのprocess lifetime peak working set **116.0MiB**（API/検証処理込み、GUI除外）。各request単発: first 15.31秒 / second 1.78秒 / last 1.79秒 / beyond 1.81秒 / images 0.28秒 / covers 1.91秒 / favorites 0.12秒。HTTP初回はmodel再ロード込み。HTTP試験終了後の所有worker停止を確認し、native GUI1万件負荷は未実行。

preflightは768×768/30tag/128件で49 checks PASS。CLI guardはbenchmark9/API5 checks PASS: 範囲外/既存/未完了/1万件でない入力、寸法/tag上限等を拒否し既存証拠を保護。新しいtoolのsyntax/help/diff checks PASS。Python103 tests/C#15 checks/WinUI x64 SelfContained Releaseも再確認（実行logはdata/index-scaling/gpu-large-*）。WinUI code reviewは変更差分とnative Items/60 paging、async/dirty、DOM JSON、theme/profile/auth境界を確認。WinUI analyzer未導入。今回GUIは変更・再実行なし、前回appearance-09の105 checks/17 PNG目視PASSと区別する。

画像は単純図柄でPNG約6KB、生成source全体は**5.9MiB**。768px画像decodeと現行processorによるresize/280 soft-token上限を通る測定であり、大きな実ZIP/JPEGのI/Oや最大byte/pixel限界を網羅しない。tag内容は共通の架空負荷文で、品質コーパスではない。実1TB/多数root/実作品・GUI込み総資源/一般検索品質/別checkpoint/Laya精度改善/reader/Komga/HC/高DPI/AOT/配布は未確認。私物・個人設定・OS・依存・モデルは変更/取得なし。

再現（生成素材のみ、新規output）:

    python tools/test_index_gpu_scaling.py --output data/index-scaling/<fresh-folder> --stages 64 256 1024 2304 5000 10000 --cover-width 768 --cover-height 768 --metadata-tags 30
    python tools/test_index_gpu_api.py --fixture data/index-scaling/<same-completed-folder>

既定の小素材/stagesを保持。cover各32..768、metadata-tags0..30、tag長60。build1phaseは測定toolだけ最大3600秒、製品timeoutは変更なし。APItoolは生成/合格/実GPU10000/生成rootを確認し、api-result.jsonがない時だけ実行する。全result/DB/生成素材/logはignored。途中pass=falseを失敗と混同せず最終exit/resultを確認。

次の3手: (1) [ai-resource-policy.md](ai-resource-policy.md)の明示worker解放を実装し生成実GPUで停止/再ロード/競合を検証、(2) 選択式idle解放/索引待機と上限超の対象選択をGUIへ、(3) 明示指定の小実サンプルで意味/表紙の検索品質を評価。Layaは精度gate未達の既定無効実験APIを保持。


## 前段階の再開地点（2026-10-12・GUI完走／実GPU2,304件確認）

開始HEAD **a4690a1**。GUI検証コミット **b7de729**、実GPU測定/記録コミット **7d28a6e**。後続は提出文書のみ、最新HEADは実Gitで確認。同じfeature/Draft PR #5/baseを保持。通常GUIテスト許可は継続、専用DB/settings/生成17素材と既存EG2のみ。

**appearance-09は操作 105 recorded checks PASS / 全17 PNG目視PASS。** Light/Dark双方の実CUDA日本語検索と上限表示、cover非対応の実エラー/文字検索復帰、dirty keep、roots、missing model案内、favorite/native再起動を完走。6正常終了/cleanup warningなし、source hashes全一致。full profile chooserバッチの再実行ではなくeditor/appearance/coverage sliceであり、別checkpoint・HC・高DPI・実ライブラリの証明ではない。

07はDark clickのforeground安全拒否でFAIL（13 PNG全目視、4正常終了+1fallback warning）。所有HWNDへのscoped focusを追加。08は直接API queryをGUI初回lazy queryと競合させてFAIL（14 PNG全目視、5正常終了/warningなし）。GUIの成功Message/項目/件数を待ってから直接API queryするよう修正。07→08→09の2回fix/rerunで終了、過去FAILを変更しない。新規XAML/C#/依存/モデル/個人設定/OS変更なし。

Darkのindex_states/coverage_gpu_statesは別時点で、短時間のcached rebuild開始とcompleteが非同期に入れ替わる（09は後者processed=0）。このsnapshotをcached jobの厳密な開始/終了時刻や推論ゼロの証明に使わない。GUI結果の表示と実CUDA queryは完了確認済み。厳密なcache再利用と処理数は後続専用GPU測定で確認する。

Python103 tests PASS（81.92秒）、C#15 checks PASS、WinUI x64 SelfContained Release PASS（37.04秒/既存IL2104 2警告）。WinUI code reviewはnative Items/60 paging、async/stale/dirty、テーマ/AutomationId、DOM JSON、認証/所有worker/profile identity保持を確認。analyzer未導入。

**gpu-02:実EG2文字+表紙2,304件、86 checks PASS**。64→256→1,024→2,304、中断1,120から残り1,184だけ推論、fresh再起動cache build全推論0→queryだけCUDA。text2,304/cover216、source bytes/size/mtime不変、所有worker tree handle全終了。RAM sample peak controller40.1MiB/worker tree2062.2MiB、torch CUDA確保peak931.8MiB（総VRAMではない）。96×128の生成小表紙/短いmetadata、GPU baseline48%で独占なし。gpu-01のworker RAMはlauncherのみで使用禁止。詳細・秒・再現はindex-scaling.md最新節。実GPU1万件/1TBを合格にしない。新規取得なし。次の3手: (1) 生成768px表紙/長文metadataで1万件へ段階測定、(2) 負荷/idle解放・上限超対象選択を実装、(3) 明示小実サンプル品質評価。私物/1TB/HC/高DPI/reader/Komga/AOT/配布は未検証・未実装の範囲を維持。Layaは実験APIのみ。

## 前段階の再開地点（2026-10-12・通常GUI再開）

開始HEAD **8a62492**。同じfeature/Draft PR #5/baseを保持。実装/検証記録HEAD **5ac973b**。後続は提出文書のみで、最新HEADは実Gitを確認。

**ユーザーが通常のGUIテストを許可し、ゲーム前面維持の制約を解除した。** Sandboxはdisabledなのでlocal target、専用DB/settings/生成17素材。OS/私物/個人設定/依存/重みの変更・取得なし。

AI dialogはmodel設定だけscrollし、索引status/start/cancelを固定行へ。roots scrollも開いた時のwindow高に応じて制限。明暗AI dialogと最大10,000/ボタンbounds、Light dirty/rootsと17件実CUDA日本語検索の上限文を実確認。

**最新appearance-06全体はFAIL。75 successful checks/13 PNG全目視で撮影状態のvisualはPASSだが、Dark fresh cacheの再索引でもcuda deviceを要求したテスト条件で停止。** diskの17 current vector revision/complete17とDarkのmodel loadなしをread-only確認。これはnative全体成功ではない。fresh reuse時のみcudaをbuild条件から外し後の実queryでassertする修正、index state記録を追加。最後はsyntax/helpまででnative未再実行。Dark semantic/追加dirty/roots/missing段階が未到達。04→05→06の2回fix/rerun上限を守り、新依頼の最初に修正後を再確認する。

    python tools/test_ai_profile_ui.py --editor-only --appearance-checks --coverage-checks --output data/ai-ui/appearance-07

新規outputを使う。--coverage-checksはeditor-onlyの例外で既存EG2 text-only/float32/768を実GPUで17件使い、全profile切替を意味しない。06は4正常終了＋1owned PID fallback warning、04にもwarning。所有GUI/API/worker残留なし、sourcehash一致、生成profile cleanup。旧appearance-03 visual FAILと04/05/06全体FAILを消さない。

最終Python **103 tests PASS**、C# **15 checks PASS**、最終WinUI x64 SelfContained Release PASS（既存IL2104 2警告）、syntax/help/diff PASS。analyzer未導入。GUI通しFAILとこれらの成功を区別する。

次の3手: (1) 上記でcache条件と未到達nativeを全PNG込みで確認、(2) 生成素材で実EG2の段階的な負荷/メモリ測定、(3) 10,000超の対象/資源設定と明示小実サンプル品質評価。実GPU1万件/HC/高DPI/reader/AOT/配布/1TBは未確認。Layaは実験APIのみ。詳細はui-polish.md/codex-handoff.md最新節。

## 前段階の再開地点（ゲーム中のバックグラウンド検証）

開始HEAD **1f77172**。同じfeature/Draft PR #5/baseを維持。実装/検証記録HEAD **5be9b88**。後続は提出文書のみで、最新HEADは実Gitで確認。

**ユーザーは別窓でゲーム中で、アクティブwindowを変えないテストを希望。** 今回はnative GUI起動/Activate/入力/OS設定変更を行わず、Hidden/BelowNormalのCPU検証とbuildだけを実行。GPU/新規download/私物走査はなし。この希望が続く間は前景が必要なharnessを実行しない。

AI対象をeligible **10,000件**まで拡張。256件keyset metadata、build IDリスト固定、現行除外/revision再確認、16件進捗checkpoint、候補IDだけのvector取得、全batchをまとめたglobal mean-rrfを実装。GUIはAPI上限を表示し既定値を使い、明示2,000件指定/旧モデルidentity/cache/手動filter/60件pagingを保持。検索metadata/scoreは最大10,000件保持し、全数万件/1TB/constant-memory対応ではない。

生成10,010ファイルのうち10,000件、768次元synthetic text vector、**14 checks PASS**。2,300件cancel後の再起動で残り7,700件だけ生成、末尾top1/paging/filter、次の再起動でdocument encode 0、全source bytes/size/mtime不変。actual_model=false/gpu_used=false/native_gui_run=false。[index-scaling.md](index-scaling.md)に単発時間/peak working setと限界を記録。

**前回appearance-03はUIA68 PASS / visual FAILを保持。** 全3dialogのRequestedTheme修正、新しい1万件のGUI文はbuild/reviewまででnative未再実行。ゲーム終了等で前面操作が可能なとき、新規outputへ `--editor-only --appearance-checks` を実行し全PNGを見て確認する。実GPUの大規模評価、HC/高DPI/reader/AOT/配布/1TBも未確認。Layaは精度未達の実験APIのみ。

最終Python **103 tests PASS**、C# **15 checks PASS**、WinUI x64 SelfContained Release PASS（既存IL2104 2警告）。WinUI review済み、analyzer未導入。

次の3手: (1) 前面操作可能ならLight/Dark dialogと新上限表示のnative確認、(2) GPUを使ってよい時に生成素材で実EG2の段階的なメモリ/負荷測定、(3) 10,000件超の対象選択/資源設定を設計し、明示指定の小実サンプルで品質評価。未指定の私物は走査しない。

## 前段階の再開地点（テーマとAIエラー復帰）

開始HEAD 988d55e。同じfeature/Draft PR #5/base、チャット側f4273ffとモデル/旧索引互換を保持。実装/検証記録HEADは8418d68。後続は提出文書で、最新HEADは実際のGitを確認すること。

開発起動の `-UITheme System|Light|Dark` を追加した。Windows全体の設定を変えず、アプリのrootだけへ適用する。既定Systemで通常のテーマ追従を維持し、保存設定は追加しない。WinUIのOnLaunched.Argumentsは非対応なので、実プロセスのcommand-line argumentsから限定した値だけを読む。

**native appearance-03はUIA 68 checks PASS、視覚レビューはFAIL。** 生成17素材/専用DB/settingsで、文字専用profileの実cover非対応エラーをLight/Dark両方、missing profileの実意味検索エラーをLightで再現。中央の具体的案内、古い件数/ページの消去、前後ボタン無効、名前・タグへの復帰/1件の実作品表示/InfoBar成功文まで確認した。favorite保存/dirty keep/native再起動も再確認。9 PNGを全目視し6回正常終了/cleanup warningなし/元ファイルhash不変。

目視でLight画面のAI dialogだけDarkになる不一致を発見し、全3 ContentDialog（未保存確認/フォルダ管理/AI設定）に `RequestedTheme=ActualTheme` を追加した。**最後の表示修正はRelease build/code reviewまでで、native未再実行。** winui-ui-testing skillの最大2回fix/rerunへ達したため、残件として記録。68項目のUIA成功をテーマ完了と扱わない。ignored visual-review.jsonはvisual_pass=false。

appearance-01は候補のUIA二重公開でFAIL、02はInfoBar本体に存在しない値を待ってFAIL（実復帰は画面/子Title・Messageに表示）。候補を所有PopupHost HWNDへ限定し、成功判定を実子テキストへ修正して03のUIAはPASS。01の環境変数、02のOnLaunched.Argumentsはテーマ指定が届かず、03でプロセス引数のLight/Dark本体表示を実確認した。過去failureを消さない。

Python96/C#13/WinUI x64 SelfContained Release PASS（既存IL2104 2件）。actual_model=false/profile_verification=not_run、AI推論/重み取得なし。モデルcapabilityチェックは推論前に失敗する実APIで、CUDA索引/品質の再検証ではない。実DPIは96/HighContrast=false、OS設定変更なし。高DPI/HC/reader/配布/1TBは未確認。私物/個人AppData設定は変更せず、既存のアプリ診断ログは使用した。所有test GUI/API/workerなし、生成profileのみcleanup。

**次の3手:** ① `--editor-only --appearance-checks` を新規outputへ実行しLight/Dark dialogの修正後実画面を最優先確認、②2,000件超をcheckpoint/増分/resource上限込みで段階拡張し生成大規模集合で測定、③明示実サンプル評価と用意された高DPI/Contrast環境での確認。私物サンプル未指定時は生成素材。Layaは実験APIのみ。詳細はdocs/ui-polish.md、docs/codex-handoff.md末尾。同じDraft PR #5/baseを維持。

## そのままチャットへ貼る依頼文

```text
Aredokoの開発を現在の実装から引き継いでください。
リポジトリ: https://github.com/jakymiku/Aredoko （非公開）
作業ブランチ: feat/winui3-production-mvp-20261011
最新引継ぎ: https://github.com/jakymiku/Aredoko/blob/feat/winui3-production-mvp-20261011/docs/chat-handoff.md
Draft PR: https://github.com/jakymiku/Aredoko/pull/5

まず、このブランチのAGENTS.md、docs/chat-handoff.md、docs/codex-handoff.mdの最新節、Issue #4、PR #5を確認してください。mainや古いWeb試作の状態を現状と混同しないでください。
WinUI 3製品MVP、EmbeddingGemma 2の曖昧検索、交換可能なモデルprofile、混合順位改善は実装済みです。Layaは精度不足のため明示実験APIだけで、GUIの自動切替や種類絞込みには使っていません。
最新は生成1万件の実EG2文字+768px表紙/長い日本語tagのGPU検証と、HTTPのpaging/種類/お気に入り検索までPASSです。増分・中断5096から残4904だけ再開・fresh cache全推論0・所有worker終了を確認。前回native appearance-09も105 checks/17 PNG目視PASSであり、appearance-06等の過去FAILは履歴として残しています。まずdocs/ai-resource-policy.mdに従って明示worker解放を実装し、実GPUで停止/再ロード/競合を検証してください。次に選択式idle解放/索引待機/上限超の対象選択、明示小実サンプルの品質評価へ。私物を未指定で走査せず、全1TBやGUI1万件負荷を検証済みとは扱わないでください。
既存資産・手動検索・タグ保存を維持し、実装できる環境なら必要なテスト、コミット、同じDraft PRの更新まで進め、進捗を引継ぎへ記録してください。直接編集やWindows実行ができない場合は、実コードに対応した変更ファイルか適用可能な差分と、PCで実行する検証手順を返してください。未実行のテストを成功と報告しないでください。
非公開リポジトリを読めない場合はアクセスできないと明記し、ユーザーが共有するこのブランチのソースを使ってください。仕様だけから実装済みコードを想像して書き直さないでください。
```

## 現在のGit状態

- 今回の開始HEADは `8a62492`、実装/検証記録HEADは `5ac973b`。後続は提出文書のみで最新HEADは実Gitを確認すること。前段階の索引拡張は `5be9b88`、テーマ修正は `8418d68`。
- HEADブランチ: `feat/winui3-production-mvp-20261011`。
- Draft PR [#5](https://github.com/jakymiku/Aredoko/pull/5)、base `feat/gui-framework-comparison-20261010`。未マージ。PR #1/#2/#3も保持し、mainへmerge・force-push・squashしない。
- 引継ぎ開始時点はclean、機能作業の未コミット残りなし。テスト用API/GUI/GPU workerは停止済み。
- 元PCのプロジェクトはユーザー指定の `C:\AI\Aredoko`。別チャットの実行環境へこのフォルダ、localhost、GPU、venv、モデルが自動で移る前提にしない。
- 非公開GitHubの閲覧可否と、コード編集・push可否は実際の利用環境で確認する。読めない場合はブランチのコードZIP等をユーザーから受け取る。venv/models/DB/私物をZIPへ含めない。

## ユーザーの目的・決定

指定した複数フォルダの画像・動画・音楽・素材・購入同人誌を、曖昧な文章で探し、タグ/仮想棚で整理するWindows GUIアプリ「あれどこ / Aredoko」。数万ファイル・1TB以上が将来の対象。PCはCore i7-13700K、RAM32GB、RTX4070Ti 12GB。

画像フォルダ・ZIP・CBZが混在、PDFは少数。Komgaは読む時に起動する。将来の読書/Komga検索補完は希望だが未実装。ツール/OSS検索は別企画。ダウンロードフォルダ限定ではなく、ユーザーが明示選択したフォルダを使う。元ファイルの移動・変換を強制せず、タグ等をアプリDBへ保存する。移動後の追跡は未実装。

ユーザーは後発の互換モデル（非検閲モデル等）へ交換しやすい構造を希望。任意のモデルが無条件に互換という意味ではない。アプリに検索内容の拒否処理は追加していない。「下着のデザインテンプレート」は架空PSDの名前/タグ入力から1位で検索できたが、実PSD内部や私物精度の検証ではない。

## 実装済み

| 範囲 | 現状 |
| --- | --- |
| 製品GUI | 独立したWinUI 3/C#アプリ。登録同意→read-only走査→一覧/検索→タグ・棚・お気に入り・確認済み保存。60件paging、詳細pane、未保存確認、async stale検索対策 |
| プレビュー | 画像、CBZ/ZIPの先頭画像。サイズ/画素/並行処理を制限、archiveを展開しない |
| 通常検索 | Python stdlib + SQLite APIによる名前・タグ検索。AI不足/失敗でも独立して利用可能 |
| AI検索 | ローカルEmbeddingGemma 2/CUDA。名前/タグtextと画像/表紙coverを別vector保存。AI索引dialog、意味検索、画像・表紙検索 |
| 索引 | eligible上限10,000件。256件metadata/vector取得、16件進捗保存、増分/cancel/restart、除外/manual filter/旧cache互換。CPU生成1万件PASS、実GPU大規模/全数万件は未完 |
| モデル交換 | 検証済みJSON profile +登録adapter、起動時-AIProfile。vector-space identityごとに索引分離、旧default互換。text-only adapterは契約実装済み、別重み未検証 |
| 混合順位 | AI意味検索の既定mean-rrf。k60、cosine同点平均順位、利用可能modality平均。maxへrollback可、明示text/coverはcosine。再索引不要 |
| Laya | 固定0.4.2/多言語重み、owned offline worker、独立suggestion API。起動既定無効、-LayaIntentで明示有効。hybrid質問＋順序棄権。GUI採用保留 |
| 過去資産 | Webデモ、read-only索引試作、GUI比較アプリを保持。製品とは区別 |

## 検証済みの範囲と限界（順位改善時点の履歴・最新結果は上記）

- 最新実装でPython **90 tests PASS**、C# **13 checks PASS**、WinUI Release build PASS。旧SDK IL2104警告2件は未解消・抑制していない。
- 実EmbeddingGemma CUDA、生成23素材/28条件: 期待top1 **25→27**、期待順位悪化0。赤表紙2→1、青表紙1維持。新validation16条件は15→15で、改善2件は既知development条件。個人ライブラリの性能保証ではない。
- 最新WinUI実機local生成17素材: 登録/走査/CUDA索引/意味検索/タグ保存/dirty keep/文字復帰/赤表紙融合/max復帰/青coverタイルPASS。4枚目視確認、sourcehash不変。
- 過去段階でGUI restart保存・vector再利用、旧索引互換、profile切替もPASS。最新順位更新でrestartは再実行していない。
- Laya development32で選定後、新held-out24を評価: hybrid effective intent17/24、kind15/24（v1 kind12/24）、各head6件棄権。warm中央値81.53ms、cold12.94秒。精度不足なのでGUI提案/自動mode/filterを追加しない。
- 新Laya HTTP契約・cold中literal・busy fallback・timeout・親終了でrealworker停止PASS。Windows venv redirectorと実Pythonを区別し、ownerと即時親の両方を監視する。
- 旧held-out12と新24はいずれも評価済み。今後調整するなら別の未見集合を先に作る。確率や類似度をconfidence/正解率とみなさない。
- Sandbox/WinUI analyzerなし。高DPI/Light/HighContrast/reader/ピッカー全体/AOT/配布未検証。CPU/量子化/idle unload、1TB throughput、実私物精度も未検証。
- 本文/OCR、PDF内部、音声/動画内容、PSD/SVG等の内部は未解析。関連表示、読書ビューア、Komga、画像フォルダを一冊にまとめる処理、移動追跡、複数棚は未完。

## GUIモデルprofile選択の実装計画（実装済み・当時の履歴）

1. [model-profiles.md](model-profiles.md) と既存launcher/API/dialogコードを読み、設定をGUIから選ぶ最小経路を設計する。既定profileへ戻す操作、現モデル/対応入力の表示、無効JSON/重み不足の案内を含める。
2. 選んだ設定はまず次回起動に適用。進行中の検索/索引・未保存タグの調停を維持する。既存-AIProfile引数との優先順位と設定保存先を明記し、選択だけでDL/依存導入しない。JSONをアプリ設定として扱い、任意Pythonコードやremote codeを許可しない。
3. 設定と既存vector identityを共通実装で扱い、GUI側に別の互換性判定を作らない。別profile索引・旧default復帰・text-only画像検索案内・invalid/missingでもliteralを維持する回帰を確認する。
4. 対応環境でPython/C#/Releaseと生成素材GUIフローを検証、コミット、同じDraft PR更新、引継ぎを記録。実GPU重みがない環境ではmock契約と実モデル検証を区別する。

その次は、ユーザー選択の実サンプルで順位を評価し、2,000件超をcheckpoint/増分・resource上限で拡張する。実サンプル指定がない間は生成素材で進める。

## 守るべき実装上の境界

- AGENTS.mdを優先し、既存資産を削除/再scaffoldしない。特に `experiments/gui-compare/winui3/generated` を触って作り直さない。
- ソースの移動/削除/rename/reencode/archive展開なし。私物走査は明示フォルダ選択後のみ。モデル/DB/cache/venv/個人paths/credentialsをGitへ含めない。
- APIはloopback/token/Originを維持。torch等はowned workerへ隔離、stdlib catalogを重くしない。通常検索fallback、同時数/出力/timeout制限を維持する。
- .NET Releaseでreflection JSONが無効なためJsonDocument/JsonNode/Utf8JsonWriter経路を保つ。過去のWinRT/ComWrappers crashを起こしたmanaged ListView.ItemsSourceへ安易に戻さず、現在のnative Items/60pagingを維持する。
- AI index identityをmodel ID/revision/dimension/modalities/prompts/precision/preprocessingから分離しない。未保存編集・async選択競合・stale search対策を崩さない。
- 新しいcheckpoint、package、OS変更は今回の文書引継ぎの範囲外。過去にEG2と固定Layaの取得は承認済み、今後の新規取得は必要性/対象を確認。全DL合計 **6,000,000bytes/s以下** を維持する。

## コード・資料の入口

- 詳細履歴: [codex-handoff.md](codex-handoff.md) の末尾。仕様: [winui-mvp.md](winui-mvp.md)、[model-profiles.md](model-profiles.md)、[ai-ranking.md](ai-ranking.md)、[laya-evaluation.md](laya-evaluation.md)。旧README/spec/statusの時点が古い場合は最新コードと本資料を優先。
- WinUI: `src/Aredoko.WinUI/MainPage.xaml`, `MainPage.xaml.cs`, `MainWindow.xaml.cs`。共通C#: `src/Aredoko.Core/LibraryApi.cs`, `Protocol.cs`。
- API/catalog: `app/production_server.py`, `production.py`, `library_index.py`。launcher: `tools/start-winui.ps1`。
- embedding: `app/ai_profiles.py`, `ai_adapters.py`, `ai_process.py`, `ai_worker.py`, `ai_search.py`, `ai_ranking.py`、`config/ai-profiles/embeddinggemma-2.json`。
- Laya: `app/search_intent.py`, `intent_questions.py`, `laya_config.py`, `laya_process.py`, `laya_worker.py`。検証定義: `tests/fixtures/laya-ja-v2.json`。

## 起動・検証コマンド（repo root）

```powershell
python -m unittest discover -s tests -q
dotnet run --project tests/Aredoko.Core.Tests -c Release
dotnet build src/Aredoko.WinUI/Aredoko.WinUI.csproj -c Release -p:Platform=x64
pwsh -File tools/start-winui.ps1 -Database data/chat-test/catalog.sqlite
# 既存local JSON profileで起動（不足時もダウンロードしない）
pwsh -File tools/start-winui.ps1 -Database data/chat-test/catalog.sqlite -AIProfile data/ai-profiles/custom.json
# 旧順位へ戻す
pwsh -File tools/start-winui.ps1 -Database data/chat-test/catalog.sqlite -AIRanking max
```

元PCのGPU用 `.venv-ai` と `models` はGit対象外。別環境にあるとは限らない。実GPUテストの新outputは既存証拠と重ならないignoredディレクトリを指定する。`tools/evaluate_ranking.py`, `evaluate_intent_v2.py`, `test_laya_api.py`, `test-ai-ui-local.ps1` の引数/生成素材条件を読んでから使う。元PCの `data/ai-smoke/ranking-01`, `data/ai-ui/ranking-01`, `data/laya-evaluation/v2-heldout-01` 等はローカル証拠でGitHubに実体はない。

## スキルの扱い

元PCにはHallmark、Web Design Guidelines、WinUI setup/design/dev-workflow/code-review/ui-testing/packaging等を導入済み。スキル本体が別GPTチャットへ自動で渡る前提にしない。利用可能なら対応するSKILL.mdを読んで適用する。ない場合も上記の検証・安全境界・Fluent/アクセシビリティ・async/dirty制御を守り、正式スキル監査を実施したと報告しない。XAML変更時はWinUI design、ビルド後commit前はcode-review、実機検証はui-testingが対応する。

この引継ぎだけでソース読取は代替できない。アクセスできるコードと実行環境を確認してから、次の実装を始めること。

## 開発追記：WinUI GUIモデルprofile選択（2026-10-12）

**今回実装した変更**（最終の実機検証は別途必要）:
- `app/ai_settings.py`: 既定profileと `data/ai-profiles/*.json` のローカル候補一覧、JSONとモデルidentityの既存検証、`.venv-ai` /重みフォルダ/ revision markerの欠落・不一致診断、設定ファイルの原子的保存。`%LOCALAPPDATA%/Aredoko/settings.json` はGit管理対象外。モデル/索引実体は変えず、選択を**次回起動から**適用。既定へ復帰できる。候補のprofileは任意Python import/remote code不可、自動DLなし。
- `app/production_server.py`: トークン保護 `GET /api/library/ai/profiles` と Origin+トークン保護 `POST /api/library/ai/profile`（IDだけ受理）を追加。起動時は **明示 `-AIProfile` > GUI保存 > 既定**。保存設定が破損しても引数優先。選んだprofileが消失・無効ならoptional AIを停止して通常文字検索を維持。ローカル確認用`--ai-settings`を追加。
- `src/Aredoko.WinUI/MainPage.xaml.cs`: 既存「AI索引」ダイアログにprofile候補、対応入力（文字/表紙）、不足・無効警告、次回起動用の保存ボタン、起動引数優先・再起動必要のメッセージを追加。作業中のworkerはhot swapしない。text-only時のcover非対応は従来のbackend契約を維持。
- `tests/test_ai_settings.py`: 一時フォルダ・一時SQLite・疑似HTTPでプロファイル復帰、保存設定と起動引数の優先、不正パス/壊れたJSON、重み・リビジョン不足、APIのOrigin/token保護、文字検索維持を検査。`.github/workflows/ai-profile-checks.yml`でWindows Python/C#とWinUI Releaseを検証。

**現在の境界**:
- GUIの実機クリック操作、再起動後の実GPU worker起動、別重みの精度/互換性はこの環境から実行できず**未検証**。CI上のWinUI Release成功もGUI実機動作保証ではない。
- Layaは今回一切変更せず、明示実験APIのみ。既存のmean-rrf/再索引分離/旧default互換を維持。
- 実行は `pwsh -File tools/start-winui.ps1` →「AI索引」→候補選択→「次回起動に設定」→アプリ終了→同じコマンドで再起動。すでに `-AIProfile` を渡す場合はそれが優先する。
- Codexへの次の指示: (1) Windows実機でdefault/custom/text-only/不足時の画面と再起動切替、(2) GUIに表示される警告の読みやすさ/高DPIを確認、(3) 完了後は実サンプル精度と2,000件超索引へ進む。

