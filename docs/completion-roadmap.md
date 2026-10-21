# Aredoko 完成までの実行計画

> **Windows準備済み2026-10-21**：[実結果と起動ファイル](portable-windows-validation.md)。Work68db65bを統合しCore759/起動CPU103/Portable publish・bootstrap実Win32非GUI通信・同梱runtime検査PASS。viewer78 PASS/3 SKIP。準備済みdist/portable-wincheck-20261021-02/Aredoko/Check-Startup.cmdでユーザー手動確認へ。GUI/GPU/clean Windows/ZIPは未実行、旧Alpha未更新・旧GUI3/3維持。再準備を無用に繰り返さず、次は実起動の結果を確認。

> **最新2026-10-21・実使用改善**：[U01–U16台帳と部分検証](usability-feedback-20261021.md)を先に読む。GIF native化/APNG poster除外/小画像拡大/テーマ/favorite即時保存/scope解除/タイル再配置を実装、Python31/Core732/Release0 errors・既知5 warnings。overnight GUIは3/3で停止、Light全工程・Dark一部を確認、raw FAILを成功へ読み替えない。全21 PNG目視。installed Alpha/封印済み02は未更新。HoneyView parity/U09 folder favorite/U11棚別/U13 GUI backup/U14全体履歴は未完。次はCPU viewer段階診断→PZ2/PZ3/PZ4/PZ5、ALPHA後実音声。今回のshutdownを将来へ再適用しない。

> **最新方針2026-10-21（ユーザー指定）**：今後の標準は[ZIP解凍→Aredoko.exe](portable-distribution.md)。PZ1自己完結frontend publishはCPU合格、製品ZIPは未完成。現在はPZ2所有bootstrap→PZ3全runtime梱包→PZ4 ZIP/再配置CPU→PZ5明示許可後のnative/clean Windows。下のMSIX-firstの「次」は履歴で、この順序を優先。DB/原本/機能/旧登録/試行上限を保持、ALPHA後に実音声/音楽→WinUI。

> **最新2026-10-21**：[MSIX正式起動・実機結果と再開条件](alpha-packaged-activation.md)。許可済み証明書trustとAlpha1.0.0.1通常installは完了し、元Development登録を保持して併存。363 installed payload全件照合PASS。実shortcut→新規所有GUI/backend→生成画像検索・タグ保存まで確認したが、native flowは待機/スキャン/保存captionのテスト不備で**3/3上限**。誤った起動失敗通知とテスト期待値をsourceで修正し、追加GUIなしでCPU55 PASS、停止後DB保存/整合・source不変・封印済み02全24,325ファイル一致を確認。02は修正前artifactのまま。**R13 DOING / ALPHA-0未完 / R14 PARTIAL**。次はCPUのみ起動待ち/配布整備、追加GUIは新たな明示許可後に残るargv/閲覧/正常終了・再起動/clean Windows更新削除受入。過去のcaps/全機能/guardを維持し、ALPHA後の実音声/音楽→WinUI改善へ戻る。

## 2026-10-20 現行状態の訂正

[最新UI受入](ui-current-build-acceptance.md)：表示サイズ/元解像度/通常footer整理を受入済み。ユーザー指示で通常幅1200〜1600pxを優先、小窓は主要操作だけに留める。R11の同一flowを反復せず次はR13。R14はPARTIALのまま。

[ブラッシュアップ監査](polish-audit-20261020.md)を優先する。下段の各タスク実装報告は履歴であり、音声の実抽出・現行GUI・clean-machine配布を受入済みにしない。現在はR11/R13の不足を修正中、R06/R07/R08実入力は未完、R14 PARTIAL。ユーザーのUI巻き戻し懸念は今回の古いAppX誤起動から生じたため、現行UIをresetせず正しい配備の検証を先に行う。

2026-10-18。コード確認基準：`cec19cb`。これはユーザー依頼による計画・担当難度・完了条件の整理であり、以下の未完タスクを今回実装した報告ではない。長期目的は[product-vision.md](product-vision.md)、最新の実行結果は両handoffを正とする。

## 完成に近づける判断

主要な検索/整理/閲覧は存在する。次の重心は、数万ファイルでの検索範囲の完全性、データ保全、未完の媒体機能、導入から復旧までの製品化へ移す。CPU最適化は受入予算を超えた箇所だけに限定する。1,024冊ベンチの秒数更新やテスト件数増加そのものを完成としない。

古いP0→P1→P2の順番や「次はOCR」「chunk GUI未接続」は再開指示ではない。P0は累積2/2で閉じたまま。実際に新しい検索失敗が見つかるまでRRF再調整/専用OCRへ戻らない。既存機能を減らして完成扱いにせず、未実装と未検証を分ける。

## 初期棚卸し（2026-10-18の履歴。現行状態は下の台帳）

| 領域 | 現状・根拠 | 残るもの |
| --- | --- | --- |
| ライブラリ/整理 | 登録root・複数root検索・棚/タグ/履歴・解除/再登録/purge。`app/production.py`、既存回帰 | 旧DBを含む製品としてのバックアップ/復旧・更新失敗の一連の保証 |
| 文字/画像/本検索 | EG2/WD・未承認タグ意味検索・ページ根拠・長冊chunk GUI実装済み | AI/類似/pending候補の1万件上限と数万件運用の整合、索引の継続導線 |
| 大規模候補 | `app/ai_search.py`: `MAX_ITEMS=10_000`。検索/類似は制限付き`_iter_rows`、coverageには全件列挙経路。`app/tag_semantics.py`も上限を使用 | metadata総数・索引済み数・検索候補数の違い。登録が5万件でも全件AI検索可能とは言えない |
| 動画 | 最大4代表フレーム索引・時間根拠・シーク再生、動画起点・候補の類似検索（R05 CPU_DONE） | R14実機GPU/GUIネイティブ自動操縦検証（シーク・メニュー探索） |
| 音声/音楽 | ファイル登録・名前/タグ検索、発話区間の時間付き索引と日本語検索（R06 DONE / R07 CPU_DONE） | R08音響・音楽特徴索引/類似検索、R09日常UI再生/シーク統合、R14実機検証 |
| 閲覧/UI | 画像/アニメ/本/動画・ホイール/見開き/シーク・簡潔な管理導線あり | 日常操作の一貫性、DPI/Contrast/Narratorなど製品受入、旧取消PNGの未完整理 |
| モデル/資源 | profile分離・再起動選択、手動/idle解放、処理間waitは実装済み | 初回導入/モデル不足/破損/容量不足/更新時の利用者向け復帰確認。作り直さない |
| 配布 | `tools/start-winui.ps1`はpython/dotnet/winappを要求する開発launcher | 開発tool不要の起動、配布物/ライセンス/更新・データ保持・新規環境検証。既存の個別migrationは維持し、全体保証とは区別 |

既存証拠：代表14枚/17問のcombined・cover Top1=16/17、Rec@3=100%。現行の生成1,024冊×64pageは8.573716秒（祖先検査省略版7.10秒は現行値でない）。Python514件中511 PASS/3 SKIP。これらは実私物全体/1TB・全機能の製品受入完了を意味しない。[代表評価](representative-asset-evaluation.md)・[原本確認](source-path-validation.md)。

## 完成の区切り

- **M1：日常利用β**。画像/本/動画について登録→明示索引→範囲検索→根拠へ移動→整理→再起動→バックアップ/復旧が通り、1万件以後を黙って検索対象から落とさない。開発環境に依存せず起動できる。R01〜R05とR10〜R14のM1欄を完了する。音声/音楽の内容検索が未完なら、その制限を明示したβであり全媒体完成版ではない。
- **M2：全媒体の製品版候補**。M1にR06〜R09を加え、発話だけでなく音響/音楽の内容・アイテム起点類似検索も実データで検証する。R14を変更箇所に絞って再確認し、全媒体の受入記録を揃える。ユーザー確認前にmainへのmerge/公開配布はしない。
- **長期目標**。複数ページでの物語/関係性タグ、任意Komga連携、重複/移動追跡の高度化等は後述の別台帳に残す。M1/M2を長期ビジョン全達成と呼ばず、機能削減や未実装の隠蔽で区切らない。

## タスク台帳（優先順）

状態：READY=次に着手可能、TODO=未着手、DOING=作業中、CPU_DONE=実装/CPU検証済み・必要な実機確認が残る、WAIT=具体的依存/承認待ち、DONE=必要な受入証拠が揃う。2026-10-20監査で全完了判定を訂正。R06/R07/R08/R11/R13は下表の不足が残り、R14はPARTIAL。以下の「依存」は実装契約/CPU部分の依存で、実機確認待ちだけを理由に独立した次の作業まで止めない。

| ID | 作業・出力 | 依存 | 担当難度 | 状態 |
| --- | --- | --- | --- | --- |
| R01 | 1万件上限の影響監査と大規模検索契約を凍結 | なし | **Astra推奨：設計**、調査/fixtureはSol可 | DONE：[再現/契約](large-library-contract.md)、2規模各17対照PASS |
| R02 | 全登録範囲を扱う上限付きメモリの検索/候補列挙 | R01 | Sol実装、**Astra推奨：同値性/競合レビュー** | CPU_DONE：[A/B](full-library-search.md)・[C所有取消](search-cancellation.md)実装/CPU合格、実機R14 |
| R03 | バックアップ/復旧・DB/profile更新失敗からの復帰 | なし | Sol実装、**Astra推奨：整合性設計/レビュー** | CPU_DONE：[停止時backup/新規復元](backup-recovery.md)・launcher引数CPU確認、UI導線R10/native R14 |
| R04 | 大量索引の明示継続・差分・中断再開を一連で完成 | R01、R03契約 | Sol、複数保存先の競合のみAstraレビュー | CPU_DONE：[A/B/C](index-continuation.md)実装/CPU合格、実機GUI/GPU受入はR14 |
| R05 | 動画起点の類似検索と時刻根拠/既存UI接続 | R01、既存動画索引 | Sol。集約契約が曖昧ならAstra | CPU_DONE：[保存済みframe最大集約/時刻根拠](video-similarity.md)、4通り根拠・視覚/音響空間分離・表紙/内部頁契約、UIシーク接続、実機R14 |
| R06 | 音声/音楽の入力能力・モデル/契約/評価設計を決定 | なし | **Astra強く推奨：方式選定** | DOING：[現状監査](polish-audit-20261020.md)・[音声契約](audio-content-design.md)。保存空間は実装、既存EG2の直接入力と別方式の実入力比較/実測は未完 |
| R07 | 発話内容の時間付き索引/検索adapter | R06、R03/R04契約 | Sol。新モデル取得は別途許可 | DOING：発話区間の保存/検索/時刻根拠は実装・検証済み。元音声→発話抽出→通常索引へのproducer未実装 |
| R08 | 音響/音楽特徴の索引・日本語検索・類似検索 | R06、R03/R04契約 | **Astra推奨：特徴/比較設計**、実装Sol可 | DOING：512D保存/類似・記述子照合は実装済み。実音声/曲からの特徴抽出・実モデル空間/品質未受入 |
| R09 | 音声/音楽の検索→再生→類似検索のGUI統合 | R07、R08 | Sol＋WinUI skills | CPU_DONE：再生/シーク/類似UI接続は保持。自動内容索引はR07/R08待ち。実音声の検索→再生受入が残る |
| R10 | 初回設定・未索引/上限/失敗状態・資源管理の仕上げ | R01、既存設定 | Sol | CPU_DONE：[状態明瞭化・所有取消・診断情報](ui-consistency-checklist.md)、未索引/対象外/モデル未導入の案内、実機R14 |
| R11 | 日常導線の整理と統一したWinUI表示 | R05/R10の操作契約 | Sol＋WinUI/design skills | DOING：詳細操作の折返し修正。今回の旧AppX画面は現行証拠に使わない。現行の指定flowは受入済み。通常幅を優先し、小窓は最低限。HC/DPI/Narratorが残る |
| R12 | 数万件の性能・資源予算を測り必要箇所だけ改善 | R02、R04 | Sol計測、設計変更時Astraレビュー | CPU_DONE：[受入記録](scale-resource-acceptance.md)、5万件通常検索p95=0.34s・6.5万件ベクトル順位計算p95=9.57s・取消0.1ms・WAL0B・復元2.2s合格、実機R14 |
| R13 | 配布・起動・更新/アンインストール・利用手順 | R03/R10の契約 | Sol＋WinUI packaging skill | DOING：標準配布はユーザー指定ZIPへ変更。PZ1 frontend自己完結publish合格、PZ2起動入口/PZ3全runtime/PZ4 ZIP/PZ5実機は未完。旧Alpha証拠/GUI上限を保持 |
| R14 | 実GPU/GUIのまとめ受入→修正→RC判定 | M1/M2対象の前項 | Solで通常検証、重大横断不具合はAstra | PARTIAL：既存限定GPU/GUI/規模PASSは保存。音声実入力、現行UI、配布受入が未完でM1/M2/RC全完了とはしない |

## 各タスクの完了条件

### R01 — DONE：候補境界のCPU再現・契約

完了証拠：[大規模検索契約と2規模の実行記録](large-library-contract.md)。以下は固定した受入手順。R02-A/B/Cは実装/CPU検証済み、R03も[CPU完了](backup-recovery.md)、次の実装はR04。

読む：`app/ai_search.py`の`_iter_rows/start/coverage/search/similar`、`app/tag_semantics.py`、`app/page_semantics.py`、既存`tests/test_ai_scope.py`/`test_library_scale_fixture.py`/`test_similarity_search.py`。

1. 名前/AI text/cover/combined/画像類似/pending意味/本ページで、対象選択→候補上限→kind/view/scope→順位→ページ切出しの順序と1万件上限を一覧化する。索引jobの上限と検索全集合の上限を混同しない。
2. 生成metadataを10,001/50,001件、低次元の模擬vectorで用意し、上限の前後・最終IDに正解を置く。全root/単root/複数root/棚/除外/解除/再登録で再現。巨大な実画像や私物走査は不要。未索引と「索引済みだが候補に入らない」を別に判定する。
3. `docs/large-library-contract.md`へ対象範囲・総件数表示・索引継続・top-k/ページング・同順位・RRF重み計算・取消/メモリ上限・鮮度/モデル切替を記述し、凍結fixtureと結果を残す。全件RAM展開やMAX_ITEMSの数値変更だけで解決しない。近似索引/新DB導入は初期解にしない。

**完了**：上限後の取りこぼしを再現するCPU証拠と、R02/R04が実装できる契約/受入テスト仕様がある。これは既知品質セットへの第3回RRF調整ではない。未解決設計を残したままR02へ渡さない。

### R02 — 検索範囲の完全性

R01に沿い、keyset/streaming・bounded top-k等を比較して採用。combinedの候補全体のspan/同点平均順位を、局所バッチで勝手に計算しない。既存サイズのraw score/順位/根拠は一致、50,001件の最終候補も検索でき、root/shelf/除外変更は即反映。取消・ページング・モデル別索引・不正vectorを確認する。返した件数を全集合件数と誤表示しない。CPU性能を測り、GUI変更があれば実機確認項目へ積む。

### R03 — 整理したデータを失わない

まず実際の保存先を棚卸し（catalog/元索引、タグ/棚/履歴/読書位置、候補/承認履歴、page snapshot、profile別vector、設定/再開記録）。既存migrationを維持し、SQLite backup APIまたは停止時snapshotを用いる一貫したmanifest/版契約を決める。稼働中DBの単純copyや一部DBだけの復元で整合済みとしない。

生成DBを別の新規復元先で開き、整理/読書位置が一致、再生成可能なAI cache欠損は明示再索引で復帰、破損backup/容量不足/途中失敗/旧版は元DBを壊さず失敗する。Pythonホスト変更の物理token不一致も扱い、鮮度検査を無効化せず再確認・再索引へ誘導する。実利用DBの上書き復元はこの開発タスクの自動実行対象にしない。

SQLite WALモード（`-wal`, `-shm`）の整合性を保つため、停止時バックアップ、新規ディレクトリ復元、配布作成前には必ず `PRAGMA wal_checkpoint(TRUNCATE)` を完了して単一ファイル整合性を保証する。また将来のスキーマ不整合を防ぐため `PRAGMA user_version` による前方互換性・スキーマバージョンガードを導入し、未対応の上位版DBに対してフェイルクローズ（破壊的書き込みの防止）を徹底する。

### R04 — 最後まで索引を進められる

2026-10-19：[R04](index-continuation.md)はCPU_DONE（A backend継続API、B Core厳格プロトコル/job所有取消、C WinUI AI設定統合、Python 590 [587 PASS/3 SKIP]、Core 585 PASS、Release 0警告/0エラー）。実機GUI/GPU受入はユーザー方針に従いR14で一括検証（`tools/test_continuation_acceptance.py`）。次はR05（動画起点類似）。

既存128page/16page atomic・8冊batch・最新job再開を再利用。登録5万件でも先頭1万件だけを繰り返さず、明示したscope/profileの未処理分へ進める。計画→開始→取消→再起動→明示再開/次の範囲、追加/変更/除外/解除を生成fixtureで検証。総数/準備済み/未処理/対象外/失敗を混同しない。一般queueや自動全冊走査は目的にせず、必要なbounded継続だけを追加する。

### R05 — 動画の内容類似（CPU_DONE）

2026-10-19：[R05](video-similarity.md)はCPU_DONE（保存済み時間付き動画代表frame vectorの最大類似度集約・timepoint grounding・厳格な4通り時刻根拠契約・cover単体候補0ms安全フォールバック・自己除外・UIシーク接続完了、Python 23 PASS [7 VideoSimilarityTests]、Core 596 PASS、Release 0警告/0エラー、CPU受入ハーネス合格）。実機GUI/GPU受入はユーザー方針に従いR14で一括検証（`tools/test_video_similarity_acceptance.py`）。

- **4通りの時刻根拠契約（4-way Grounding Contract）**:
  1. 動画起点 → 動画候補：候補側 `video_match_ms`（最類似フレーム時刻）および起点側 `origin_match_ms`（起点動画の照合フレーム時刻）の双方を明示。
  2. 画像起点 → 動画候補：候補側 `video_match_ms` を付与、起点側 `origin_match_ms` は null（画像は単一時刻なし）。
  3. 動画起点 → 画像候補：起点側 `origin_match_ms` を付与、候補側 `video_match_ms` は null（画像候補にシーク時刻なし）。
  4. 画像起点 → 画像候補：両時刻とも null。
- **視覚/音響空間の分離**: 視覚空間（EmbeddingGemma 768D 表紙/動画フレーム/ページ画像）と音声空間（発話意味768D / 音響特徴空間）を完全に分離し、異モダリティ間の内積計算や不正集約を契約レベルで排除。
- **本表紙と内部ページ類似の契約**: 本の類似検索では表紙ベクトルを媒体全体の代表として扱い、内部ページベクトル（`ai_page_vectors`）はページ検索時のみ明示走査され、本全体の類似度へ無断混入・希釈させない。
- **UI連携**: 動画候補結果のクリックで `VideoPlayerView` が該当 `video_match_ms` へ自動シークし、文脈メニュー「似た動画・素材を探す」から直ちに類似探索が可能。

### R06 — DOING：実音声入力の能力と方式選定

保存/検索の2系統契約は[音声設計](audio-content-design.md)に維持する。前回の「方式B凍結」は実入力の品質/VRAM比較がなく、直接EG2に環境音/音楽能力がないとの断定は撤回した。まず既存モデル/環境で入力API・出力空間・実資源を調査する。発話・環境音・音楽・音同士の類似を生成または許可済み音声で比較し、方式を確定する。新取得は別途明示許可。Astraでの設計/空間レビューを推奨、通常実装はSol可。

### R07 — DOING：保存/検索adapter CPU_DONE、実抽出producer未実装

2026-10-19：[R07](audio-content-design.md)はCPU_DONE（SQLite `ai_audio_segments`テーブル新設、無アロケーション有限性検証/高速内積計算、検索集約への発話区間ヒット統合、CoreリフレクションフリーJSONパーサー・時刻/スニペット根拠表示、Python/Core単体テストおよび受入ハーネス合格）。実機GPU/GUI受入はR14で一括検証（`tools/test_audio_acceptance.py`）。次はR08（音響/音楽特徴の索引・日本語検索・類似検索）。

- **実装コンポーネント**:
  - `app/audio_semantics.py`: 契約 `audio-speech-segment:v1`、スキーマ `ai_audio_segments(item_id, source_revision, segment_id, start_ms, end_ms, snippet, vector, contract, PRIMARY KEY(item_id, segment_id))`。リスト不生成の高速検証 `_is_valid_packed` / `unpack`、内積 `_score_packed`。
  - `app/ai_search.py`: `VectorStore.__init__` でテーブル作成、`scores_with_content` に `audio_scores` を配線、`AISearch.search(...)` で発話ヒットの時刻 `audio_match_ms` とスニペット `audio_match_snippet` を結合。
  - `app/storage_schema_v1.json` / `app/ai_store_cleanup.py` / `app/production.py`: 正式なvectorテーブルとして登録、バックアップ復元時のテーブル検証および安全クリーンアップを保証。
  - `src/Aredoko.Core/Protocol.cs`: `AIEvidence` に `audio_match_ms` / `audio_match_snippet` の安全なリフレクションフリー構文解析とフォーマット表示（`音声発話一致（mm:ss · 「snippet」）`）を実装。
- **検証記録**:
  - `tests/test_audio_semantics.py`: 6件PASS（スキーマ、正常登録/取得、無音処理、時間境界0..86400000ms検査、破損ベクトル・NaN/Infの不生成拒絶、削除/鮮度整合）。
  - `tests/Aredoko.Core.Tests/AudioSpeechTests.cs`: 20件PASS（Coreテスト合計616件PASS）。
  - `tools/test_audio_acceptance.py --stage cpu`: 15/15件PASS。
  - WinUI x64 Releaseビルド：0警告・0エラー。

### R08 / R09 — R08 producer DOING、R09再生/保存済み特徴接続CPU_DONE

2026-10-19：[R08/R09](audio-content-design.md)はCPU_DONE（独立512D音響特徴空間、日本語記述子による効果音・BGM検索、音声・音楽ファイル同士のアイテム起点類似検索、時間根拠照合、WinUIプレイヤー再生・自動シーク・「似た音声・曲を探す」コンテキストメニュー配線完了）。実機GPU/GUI受入はR14で一括検証（`tools/test_audio_acceptance.py --stage cpu` 36件合格）。次はR10（AI状態明瞭化・資源管理）。

- **R08（音響/音楽特徴の索引・日本語検索・類似検索）**:
  - 凍結された候補案B（[audio-content-design.md](audio-content-design.md)）に基づき、768D発話言語空間（テキスト共有）および視覚空間と完全に直交する独立した512D音響特徴空間を導入（`CONTRACT = 'audio-acoustic-feature:v1'`、SQLite `ai_audio_acoustics` テーブル）。異モダリティベクトルとの内積計算をAPIおよびスキーマレベルで厳格に拒絶。
  - 日本語音響記述子（例: 雨音、ピアノ、ジャズ、環境音、爆発音）のマッチングによる自然な日本語音響検索を実現。無音WAVには記述子がつかず幻覚ヒットをゼロに抑制。
  - 音声・音楽ファイル同士のアイテム起点類似検索（`origin_kind == 'audio'`）を実装。マルチフレーム最大集約、候補時刻 `audio_match_ms`、起点時刻 `origin_match_ms` の時間根拠、自己除外、未索引フォールバックを完備。
- **R09（音声/音楽の検索→再生→類似検索のGUI統合）**:
  - `AudioPlayerPolicy` による安全な拡張子検証（.mp3, .flac, .wav, .ogg, .opus, .m4a, .aac, .wma）とサイズ制限。
  - バックエンドHTTPストリーミング範囲再生 `/api/library/audio/{item}/...` と `ArchiveReaderClient.OpenAudioRangeAsync` の接続。
  - `VideoPlayerView` コンストラクタの音声モード拡張（サムネイルプレビュー抑止、簡潔なトランスポートコントロール、`audio_match_ms` への自動シーク）。
  - WinUI右クリックコンテキストメニュー「似た音声・曲を探す」を音声アイテムで有効化。
  - 詳細ペイン・検索オプション・ヒント表示の音声対応。
- **検証記録**:
  - `tests/test_audio_acoustics.py`: 11件PASS（スキーマ、512D検証、無アロケーションunpack/scoring、空間分離拒絶、特徴登録/取得、無音WAV幻覚防止、日本語記述子検索、音響類似検索、時間根拠、自己除外、応答的キャンセル）。
  - `tests/test_audio_semantics.py`: 12件PASS。
  - `tests/Aredoko.Core.Tests`: 652件PASS（AudioSpeechTests 28件、SimilarityTests 音響類似検証）。
  - `tools/test_audio_acceptance.py --stage cpu`: 36/36件PASS。
  - WinUI x64 Releaseビルド：0警告・0エラー。
  - `tests/test_storage_backup.py`: 24件PASS（新テーブル含むバックアップ・復元整合）。

### R10 / R11 — CPU_DONE：使える状態が分かる簡潔なGUIとUI整合性・アクセシビリティ監査

2026-10-19：[R10/R11](ui-consistency-checklist.md)はCPU_DONE（AI未導入/未索引/処理上限/対象外/処理失敗の明瞭な区別と案内、GUI全体の所有検索取消配線、設定画面でのオフラインバックアップ復旧案内・個人情報/Bearerトークン完全伏字化診断情報表示とワンクリックコピー、UI一貫性・DPI・ハイコントラスト・Narratorアクセシビリティ監査チェックリスト策定）。実機GPU/GUI受入はR14で一括検証（`tools/test_ui_status_acceptance.py --stage cpu` 16件合格）。次はR12（数万件の性能・資源予算の計測と局所改善）。

- **R10（状態明瞭化・所有取消・診断情報）**:
  - `AISearch.status` に `status_code`（`ready`, `model_missing`, `corrupt_profile`, `worker_failed`, `idle`, `running`, `cancelling`, `interrupted`, `failed`）、`coverage` に `coverage_status`（`unindexed`, `partially_indexed`, `ready`）、`search` に `search_status`（`ready`, `unindexed`, `partially_indexed`, `out_of_scope`）を追加。
  - `DisabledAI`（モデル未導入/環境欠落）で `status_code: 'model_missing'`、HTTP 503 `error_code: 'ai_unavailable'` を返却。
  - `src/Aredoko.Core/AISearchStatus.cs`: 11状態の定数、ユーザー向け明瞭な日本語案内 `Guidance(...)`、状態ラベル `StatusLabel(...)` を実装。
  - `src/Aredoko.Core/DiagnosticsReport.cs`: システム・ライブラリ・AI状態の要約診断情報生成。ユーザー名（`C:\Users\[USER]\...`）およびトークン（`[REDACTED]`）を正規表現で完全伏字化し、無断通信ゼロを明記。
  - `src/Aredoko.Core/Protocol.cs`: `Protocol.ParseSearch` で `search_status` をリフレクションフリーで解析。
  - WinUI 3 検索中断配線: `MainPage.xaml` に `CancelSearchButton`（`BtnCancelSearch`）および `Escape` キーアクセラレータを追加。検索モード変更・種類変更時にも進行中検索を即座に所有取消し、`api.SearchMultiAsync` にキャンセルトークンを伝達。
  - WinUI 3 設定ダイアログ拡張: 「バックアップと復旧ガイド」（`BtnBackupGuide`）によるオフライン安全運用の解説、および「診断情報を表示・コピー」（`BtnDiagnostics` / `BtnCopyDiagnostics`）によるサポート用安全テキスト表示。
- **R11（日常導線の整理と統一したWinUI表示・アクセシビリティ監査）**:
  - `docs/ui-consistency-checklist.md` を策定し、以下の項目を監査・固定：
    - 状態明瞭化マトリクス（8パターンの状態・表示文言・案内内容）
    - UI用語整合（「AI検索の準備」「未作成」「索引済み」「中断」など揺らぎの排除）
    - Light / Dark / High-Contrast 各テーマの可読性と余白確保
    - 幅800px未満の狭幅ウィンドウ・リサイズ時の詳細ペイン自動折りたたみ
    - 100%〜200% DPI拡大時のボタン・テキスト欠損防止
    - キーボード操作（Escapeによる検索中断/詳細閉じ、Tab順序、Ctrl+Fフォーカス）
    - Narrator読み上げ（アクセシビリティ名・ライブ領域更新）
    - 個人情報・トークン非送信の診断情報安全性
- **検証記録**:
  - `tests/test_ai_status_clarity.py`: 4件PASS（status_code, coverage_status, search_status, DisabledAI）。
  - `tests/Aredoko.Core.Tests`: 691件PASS（StatusClarityTests 27件）。
  - `tools/test_ui_status_acceptance.py --stage cpu`: 16/16件PASS。
  - WinUI x64 Releaseビルド：0エラー。

### R12 — CPU_DONE：大規模受入と性能の終了条件

2026-10-19：[R12](scale-resource-acceptance.md) は CPU_DONE（登録50,001件メタデータおよび65,536件保存ベクトルでの網羅的計測、全項目で工学的予算を達成、過剰な投機的変更を排して bit-exact 整合を保全）。実機GPU/GUI受入はR14で一括検証（`tools/test_scale_acceptance.py --stage cpu` 26件合格）。次はR13（配布・起動・更新手順）。

- **工学的目標と実測値対照**:
  - 通常文字検索: warm p95 = 0.3368秒 ≤ 1.0秒（Cold 241ms、12回計測）。
  - CPU保存ベクトル順位計算（65,536件 768D）: warm p95 = 9.573秒 ≤ 10.0秒（Cold 8.353s、10回計測）。
  - 所有検索取消受付レイテンシ: 0.109ms ≤ 1.0秒。
  - クリーン終了時間: 0.0045秒 ≤ 2.0秒。
  - 候補列挙（`_iter_rows`）: 50,001件全件を1.198秒で昇順走査、最終ID 50,001に到達。
  - 差分・鮮度走査: 10,000件未処理判定を0.054秒で完了。
  - カバレッジ計算: 50,001件全件で `candidate_total=50001`、`target_total=10000`（`MAX_ITEMS=10,000` 頭打ち契約遵守）。
  - 停止時バックアップ（4.26秒）および新規ディレクトリ復元（2.21秒）: `PRAGMA integrity_check` OK、50,001件完全一致保全。
  - 別fixture境界検査: 512MiB音声/書庫容量上限、24時間（86,400,000ms）時間上限の安全拒絶を確認。実1TB走査とは称さない。
  - SQLite WAL 単一ファイル整合性: 終了時に catalog / vector store 双方の `-wal` ファイルサイズが 0 バイト（完全truncate）。
- **検証記録**:
  - `tools/test_scale_acceptance.py --stage cpu`: 26/26件PASS。
  - `docs/scale-resource-acceptance.md`: p95公式、測定条件、メモリ/ディスク容量記録凍結。

### R13 — DOING：staging準備済み、配布/起動/更新の受入は未完

2026-10-19：[R13](user-guide.md) は CPU_DONE（前方スキーマバージョンガード導入、WALモード単一ファイル整合保証、配布スクリプト・単体ランチャー整備、ライセンス/NOTICE一覧、クリーン利用ガイド作成）。実機GPU/GUI受入はR14で一括検証。次はR14（実GPU/GUI一括受入）。

- **実装コンポーネント**:
  - `PRAGMA user_version = 0` 前方スキーマバージョンガード: `Catalog.__init__`, `ProductionCatalog.__init__`, `VectorStore.__init__`, `storage_backup._database` で未対応の上位スキーマ（`user_version > 0`）を検出した場合、即座にフェイルクローズ（起動/書き込み拒絶）。
  - `PRAGMA wal_checkpoint(TRUNCATE)`: `Catalog.close()`, `ProductionCatalog.close()`, `VectorStore.checkpoint()`, `AISearch.close()`, `storage_backup.backup()`, `storage_backup.restore()` の各所でクリーン終了時および配布・バックアップ前に確実に実行。
  - 配布作成スクリプト `tools/package_release.py`: .NET SDK / winapp / git checkout 不要のスタンドアロン配布物（`dist/aredoko-release-windows-x64`）を生成。SHA256ハッシュリスト（`sha256sums.txt`）およびマニフェスト（`manifest.json`）を自動生成。
  - スタンドアロンランチャー `tools/start-aredoko.ps1` および `Aredoko.cmd`: ユーザーデータを `%LOCALAPPDATA%\Aredoko` に永続保持し、アプリ更新・再配置時も安全に保全。
  - オフライン動作保証: AI環境未導入時でも通常機能（画像/本/動画/音声閲覧、タグ/棚整理、文字検索、読書進捗）は完全動作。AIモデルの無断自動ダウンロードなし。
  - `THIRD_PARTY_NOTICES.md`: Python, .NET, WinUI, AIモデル（EmbeddingGemma, WD Tagger）の著作権・ライセンス通知を一覧化。
  - `docs/user-guide.md`: 通常起動・フォルダ登録・AI導入・バックアップ復元・既知制限の網羅的ガイド。
- **検証記録**:
  - `tests/test_storage_version_guard.py`: 4件PASS（Catalog/ProductionCatalog/VectorStoreのuser_versionガード、WAL作成とclose時WAL 0バイトtruncate）。
  - `tests/test_storage_backup.py`: 24件PASS。
  - `tests/test_similarity_search.py`: 24件PASS（R08音声類似検索導入整合・material等非対象kindのValueError検証）。
  - `tools/package_release.py`: dry-run `--check` および実パッケージング検証完了（538ファイル、320.37 MiB、SHA256ハッシュリスト・manifest.json生成）。
  - `tools/test_scale_acceptance.py --stage cpu`: 26/26件PASS。
  - `tools/test_video_similarity_acceptance.py --stage cpu`: PASS。
  - `tools/test_ui_status_acceptance.py --stage cpu`: 16/16件PASS。
  - `tools/test_audio_acceptance.py --stage cpu`: 36/36件PASS。
  - `tools/test_continuation_acceptance.py --stage cpu`: PASS。
  - `tests/Aredoko.Core.Tests`: 691件PASS。
  - WinUI x64 Releaseビルド：0エラー。

### R14 — まとめて受入、完成と呼ぶ条件

M1/M2ごとに対象commit/artifact・対象機能・fixture・必要GPU/GUI時間を事前固定してユーザーへ実行確認。実行可否は最新のユーザー指示に従う。2026-10-18に実行許可を得てR02/R03限定受入を行い、[GPU PASS/native PARTIAL](release-readiness.md)を記録。以前の延期を現在の禁止とせず、試行上限/未完gateもresetしない。開発中はCPU作業を先へ進め、承認待ちは対象実機項目だけに付ける。

#### R14一括受入実行コマンド台帳（Batch Acceptance Command Ledger）

実機GPU/GUI検証許可時に実行する統合ハーネス一覧：
1. **R04 大量索引継続**:
   `.\.venv-ai\Scripts\python.exe tools/test_continuation_acceptance.py --stage all`
2. **R05 動画類似検索・時刻シーク**:
   `.\.venv-ai\Scripts\python.exe tools/test_video_similarity_acceptance.py --stage all`
3. **R07 音声発話区間検索・時刻根拠**:
   `.\.venv-ai\Scripts\python.exe tools/test_audio_acceptance.py --stage all`
4. **R10/R11 状態明瞭化・UI監査**:
   `.\.venv-ai\Scripts\python.exe tools/test_ui_status_acceptance.py --stage all`
5. **R02 全件検索・所有取消**:
   `.\.venv-ai\Scripts\python.exe tools/test_search_acceptance.py`
6. **R03 停止時バックアップ/復元・整合性**:
   `.\.venv-ai\Scripts\python.exe -m unittest tests/test_storage_backup.py`
7. **Core プロトコル総合検証**:
   `dotnet run --project tests/Aredoko.Core.Tests -c Release`
7. **WinUI 3 GUIネイティブフロー & 外観検証**:
   - `dotnet build src/Aredoko.WinUI/Aredoko.WinUI.csproj -c Release -p:Platform=x64 --no-restore`
   - WinAppDriverによる実機GUI自動操縦テスト（Light / Darkテーマ、動画シーク、音声再生、継続設定、検索画面）

成果：`docs/release-readiness.md`にM1/M2別PASS/FAIL/未確認、再現手順/証拠/残課題、既知制限、対象版を記録。必須失敗/データ損失/主要操作の未確認が残ればRC合格としない。軽微な後続事項は影響を明記し、利用者に判断可能な状態にする。merge/公開は別の明示指示で行う。

## Astraクラスを使う場所

必須と実証された専用モデル制約はない。ここでの指定は難度と失敗コストからの**プロジェクト上の推奨**であり、モデルを自動変更/別agent起動する指示ではない。通常の実装・回帰・文書・WinUI接続はSolで進められる。

特にR01/R02（全件候補とRRF・同値性・取消・鮮度を同時に扱う）、R03（複数DB/保存状態/失敗途中の整合）、R06/R08（発話と音響・音楽、異なるembedding space、VRAM/品質/ライセンスの選択）はAstraで設計または最終レビューする価値が高い。合意した契約を小さな実装へ落とす段階はSolへ渡す。Solで同じ設計矛盾/退行が2回続く場合も、第三の場当たり的修正より再現fixture・代替案・未決点を揃えてAstra相談候補にする。

公式の一般的な選定指針は[Astra/Sol等のモデル選択](https://developers.openai.com/api/docs/guides/model-selection)を参照（2026-10-18確認）。このAredokoタスクへの割当は本計画の判断であり、公式が個別タスクの必須モデルを指定したものではない。利用枠/アクセスを推測せず、自動切替や追加課金を約束しない。

## 継続手順と後続台帳

1. fetch/status/log→最新handoff→本表の最上位READY/TODOを確認。他AIの未コミット変更を上書きしない。依存が揃う最上位1件をDOINGにし、その中のAPI/CPU→Core→WinUI→必要な受入の小区切りで進める。
2. 証拠が揃う既存実装を再作成しない。不足は「未実装」「未検証」「新しい退行」に分類。CPU_DONE/WAITには未実行テストと解除条件を具体的に付け、独立した次のタスクへ進む。
3. 台帳の状態、最新handoffの対象ID/commit/完了条件の達否/次のIDを毎回更新。次の作業順の正本はこの表一つ。歴史文書に別の順番を追加しない。新しい要望/重大退行は優先順位を更新して理由を記録。
4. 当面の次の3手は **R11 最新ビルドのUI受入→R13 配布の実条件→R06 実音声入力能力の比較とR07/R08 producer接続**。UIの巻き戻し判断は誤起動した旧AppXに基づけない。詳細は[現状監査](polish-audit-20261020.md)。同一flowの試行上限/新DL許可/Actions禁止を保持。

長期台帳（削除しない）：B01 複数ページの関係/展開タグ（Astra推奨、根拠ページ/不明状態/固定評価を先に設計、専用OCRを既定にしない）、B02 Komga任意連携、B03 重複・移動追跡、B04 保存検索/ピン留め、B05 GPU/索引の高度な自動スケジューリング。新しい要望や実運用根拠が出たら順序を更新する。これらをM1前の無限な機能追加へ混ぜない。

## 2026-10-20 追加マイルストーン：ALPHA-0（次の実作業）

ユーザーの最新指示により、**R13（staging-only → ダブルクリック起動可能な最初のアルファ版）を直近の最優先実行項目**とする。実装範囲、AI/Python/SQLiteの同梱・起動、クリーン環境テスト、未完成の音楽/音声内容解析の扱いとデータ保護は **[ALPHA-0 指示書](alpha-packaging-milestone.md)** に定義する。既存R01–R14台帳・M1/M2/RCの状態/完了条件を削除・改変せず、R13の進捗として区別する。現行のR11/R14 PARTIALは維持し、配布スクリプトだけでALPHA-0/M1/RC完了とはしない。**ALPHA-0後はR06→R07→R08→R09の実音声・音楽検索対応、その後にWinUIの使い勝手・最終デザイン改善、残存R11/R14/M1/M2受入へ進む。** この後続作業は中止ではなく一時的な後回しである。旧「次の3手」は記録として保持するが、作業再開時にはこのユーザー指定のALPHA-0を優先する。


## 2026-10-20 Linux追記：R13 runtime stagingの進捗

**R13はDOING、ALPHA-0未完、R14 PARTIALのまま。** [実装と検証](alpha-runtime-staging.md)：準備済みPython/FFmpegの明示梱包、manifest検査、モデル/worker保存先指定、Python launcher/所有終了、current-user shortcutスクリプトを追加。対象の重複除外139 PASS / Windows2 SKIP。上表の「Python/AI runtime未同梱」は実配布物について引き続き成立し、今回追加した同梱**機構**の検証と区別する。次IDはALPHA-0/R13のWindows runtime import・WinUI activation/identity・clean-machine受入。完成後R06–R09実入力対応、次にUI改善。旧台帳/過去成績は削除せず保持。


## 2026-10-20 Windows追記：同梱runtimeとfrontend MSIXの実物確認

[Windows実測・生ログ・次の3手](alpha-windows-runtime-validation.md)。既存資産だけでPython/AI/動画runtimeを準備し、同梱環境のimport、EG2 CUDA固定3処理、backend2起動の保存/所有終了と対象CPU38件がPASS。5.52GB stagingの全checkは169.781秒、frontendのみの未署名自己完結MSIXは約65MB。**R13 DOING / ALPHA-0未完 / R14 PARTIAL**。Native activationと所有launcher統合・起動待ち・通常shortcut/署名/install/clean Windowsは未受入。過去のLinux/GUI記録は履歴として保持し、次はALPHAの起動経路を完成させる。成立後の実音声/音楽→WinUI改善は中止しない。


## 2026-10-21 R13起動前検査の追記

[同条件の全検査計測と安全性](alpha-startup-performance.md)：固定4 workerでwarm73.567→41.558秒、24,196 hash/80,864 guard保持、対象CPU39 PASS。既存配布を書き換えず現行checkerを比較した結果で、前日の170秒・cold/p95やnative起動完了と混同しない。前日helper由来の未知cache3件は無視せず退避/保存済み。次はALPHA-0のnative activationと所有backend連携。R13 DOING/ALPHA未完/R14 PARTIALと後続音声/音楽→WinUIの順序を保持する。


## 2026-10-21 R13 MSIX実機結果と誤通知修正

[MSIX正式起動・実機結果と再開条件](alpha-packaged-activation.md)。許可済み証明書trustとAlpha1.0.0.1通常installは完了し、元Development登録を保持して併存。363 installed payload全件照合PASS。実shortcut→新規所有GUI/backend→生成画像検索・タグ保存まで確認したが、native flowは待機/スキャン/保存captionのテスト不備で**3/3上限**。誤った起動失敗通知とテスト期待値をsourceで修正し、追加GUIなしでCPU55 PASS、停止後DB保存/整合・source不変・封印済み02全24,325ファイル一致を確認。02は修正前artifactのまま。**R13 DOING / ALPHA-0未完 / R14 PARTIAL**。次はCPUのみ起動待ち/配布整備、追加GUIは新たな明示許可後に残るargv/閲覧/正常終了・再起動/clean Windows更新削除受入。過去のcaps/全機能/guardを維持し、ALPHA後の実音声/音楽→WinUI改善へ戻る。

## 追加：viewer速度改善のsource checkpoint（0c2a34b後）

[viewer性能記録](viewer-performance.md)に実装と残る受入条件を集約。先読み/cache/旧画像保持/保存分離/close flush/段階計測とAPNG thumbnailを追加し、Python関連81 PASS。新Coreテスト・WinUI build/native/HoneyView比較は未実行。次のviewer作業はWindowsで既存依存のビルドと許可後の実描画・保存・source guard確認。その後PZ2→PZ3→PZ4→PZ5を継続し、R13/ALPHA/R14の完了条件や残件は緩めない。

## 2026-10-21 PZ2処理基盤の進捗

[実装と境界](startup-progress-control.md)：全SHA/guardを維持した実進捗/協調取消と所有runtime probe cleanupを実装、関連66 PASS/Windows5 SKIP。PZ2は処理基盤のみPARTIALでnative bootstrap/起動UI/IPC/ready/portable launchは未実装。前回viewerの新Core/WinUI/実機速度比較も保留。次はPZ2残り→PZ3→PZ4→PZ5、R13/ALPHA/R14の未完状態は維持する。
