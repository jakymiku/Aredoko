# 長い本の分割追加：明示plan/start/resume API

> **最新（2026-10-18、再利用vector非確保透過保存）**：`_publish_range`で既存vectorの再利用判定を`_is_valid_packed`による非確保検証へ統一し、768要素リスト生成と再正規化/再エンコードを排して保存済みblobを直接SQLiteへ透過保存（bit/byte完全一致）。Python506（503 PASS / 3 platform SKIP）、Core493、Release0警告0エラー。P0 2/2/OCR保留を維持。

> **最新（2026-10-18、CPUのみ）**：coverage/planのvector復号をcatalog guard外へ移動。最後にscope/同snapshot/原本/scan/AI終了を再確認し、生成1万pageの全応答一致。guard保持340→34ms、総所要は微増で検索高速化とは別。[設計/測定/回帰](page-coverage-concurrency.md)。今回の検証はCPUのみ。P0 2/2/OCR保留/既存機能を維持。

2026-10-17のplan/start/resume APIを、2026-10-18に既存WinUIのページ追加dialogとAI設定へ接続した。既存の単一範囲16ページ・複数本8冊/計128ページは保持。専用OCRは保留し、通常AI buildや範囲確認だけで本文全体を自動解析しない。

## WinUIから使う（2026-10-18）

1. 本を右クリック→「本のページをAI検索に追加…」。既存の「ページを指定（最大16）」は従来どおり。
2. 「追加する範囲」を**「未準備ページをまとめて（最大128）」**へ切り替える。今回の上限は1〜128（初期64）。「追加範囲を確認」でCPU planだけを取得する。source/profile/scopeと固定page IDsを検査し、1始まりのページ範囲と保存回数を表示。まだ推論しない。
3. **「確認した範囲を追加」**でのみ開始。上限や方式を変えたらplanを破棄し再確認が必要。進捗・保存済みページ数・中断・閉じるはスクロールする入力欄の外に置き、右24DIP gutterを保持。長い範囲一覧はスクロール内、情報や機能を削除しない。
4. 中断/失敗で完成chunkを保持。同じdialogは「同じ範囲を再開」を表示。新しい範囲確認をすれば保存jobの再開選択を明示的に解除する。dialogを閉じる要求は自分のjob IDだけを中断し、処理開始待ち中の要求も開始応答後に追跡する。
5. app/AIサービス再起動後は「設定」→「AI検索の準備」→**「前回のページ追加を再開」**。保存済みの同scope/profile/版/page IDsへだけ再開。scope編集が未保存/未確認、別scopeや他jobでは再開を有効にしない。自動再開/自動scope復元なし。新AI jobは最新1件の再開記録を置換する。
6. 旧jobで保存planが欠ける場合は再開を表示せず「本の追加範囲を開き直してください」。通常AI索引の作成や新しい範囲確認は利用でき、保存vectorを消して代用しない。

Coreの`PageChunks.cs`と`PageEvidenceClient`がJSON件数/範囲/固定IDs・scope正規化（空rootsと全rootsを区別）・profile/版/所有job・実chunk数を検証。UIはdialogの調整に留め、モデル推論/索引公開は既存backendのみ。`chunks`（連続した欠けの範囲数）と`chunks_total`（16個ずつ平坦化して保存する回数）は混同しない。既存未保存タグはdialogで書換え/破棄しない。i18nは既存の日本語UI方式を踏襲し、全面resw化は今回行わない。

### このGUI接続の検証

- Core **493 PASS**（新規44 checks）。1〜128の上限、35固定IDs、飛び飛び35範囲/実3chunk、scopeの型・空roots・明示null kind、profile/版/job/選択置換、旧checkpoint、HTTP routeとJSON所有、変更plan拒否を含む。初回Core runは`JsonValue<int>`を`GetValue<long>`で直接読むと失敗。int/longを型確認し、初回ログを保持して修正後合格。
- Python分割API対象 **16 PASS /36.414秒**。製品Python sourceは変更せず、全Python495件の再実行は今回は行っていない（前回492 PASS/3 platform SKIPは履歴）。最終Windows x64 SelfContained Release **0警告/0エラー**、時間とログは最新handoffへ。新APIやモデル/依存追加なし。
- native **`page-chunks-20261018-02`: runtime40 checks PASS / graceful closes2 / 6 PNG全目視**。生成145ページ本、CPU模擬encoderのみ。plan推論0、上限変更で再確認、33page確認→16page保存後中断→app/AI service再作成→16再利用/残17だけ処理、scope未保存中の再開無効、残112追加→145/145、旧plan欠落でも通常操作可能、未保存タグ/原本bytes/mtime/AI設定の保持を確認。`visual-review.json`をraw resultとは別に保存。スクロール入力の端は通常どおりclipされるが、固定の状態/開始/取消/閉じるに重なりや見切れはない。
- 初回`01`は新fixtureで77件になる待機が76件のままのため停止（failure PNG1枚目視、正常終了1）。テスト件数を修正→`02`で合格。新しい長冊featureの修正再実行1回だけ。**旧book-batchの上限消費済みtestや取消静止PNG1枚の未完gateは変更/再実行/成功扱いしていない**。
- Sandboxは`Win32_OptionalFeature.InstallState=2`（無効）のため許可済みlocalで所有PID/HWNDだけ操作。全test appは正常終了、専用AI/catalog/serverをclose。今回実EmbeddingGemma/WD/OCR/GPU・新download・私物走査・CIなし。WinUIAnalyzer未導入/未実行、High Contrast/Narrator/AOT/DPI・キーボード網羅・実私物/1TB/実GPU大量処理は未検証。
- ユーザーは`C:\AI\Aredoko-test`の既存2 ZIP（`Aredoko_text_recognition_test_images_6.zip` / `Aredoko_search_test_images_8.zip`）を、使う場面があればこのPCの実モデル確認へ利用してよいと再確認。原本は変更/移動/削除せず、[既存14枚の実評価](representative-asset-evaluation.md)を保持。今回の長冊ライフサイクルは生成145ページで測り、2 ZIPの再推論/新精度測定はしていない。

## バックエンドAPI（2026-10-17の実装を保持）

## 操作と上限

1. 既存のページ索引を明示更新し、item/revisionを取得する。本の元ファイルを変更しない。
2. `chunked/plan` にモデルprofile・scope・今回の最大ページ数を明示。CPUのみで未準備ページを選ぶ。snapshot更新・画像decode・モデルload/推論・job/state更新は行わない。
3. 返されたページ/範囲/上限を利用者が確認してから `chunked` を呼ぶ。**planだけでは開始しない**。1冊最大128ページ、HTTPのatomic保存単位は固定16ページ以下。一般queue/全冊/全ページの自動処理ではない。
4. 既存のjob ID一致cancelを使う。完了したchunkは保持し、処理中chunkは全て保存するか全て未公開。失敗時はその本を停止し、自動retryしない。
5. 中断・失敗・app再起動後は、保存されたjob IDに対して `chunked/resume` を**明示的に**呼ぶ。scope/profile/元のrevision/page IDs/chunk_sizeを検査し、同じ選択を再実行して既存vectorを再利用する。新たな範囲を勝手に足さない。

## HTTP契約

通常の `X-Aredoko-Token` とloopback Originの検査をそのまま使う。path/file/model path/任意SQLは受け付けない。以下はすべて `POST /api/library/ai/pages/` 以下。

| route | 必須フィールド（余分なフィールドは拒否） | 用途 |
| --- | --- | --- |
| `chunked/plan` | `item_id`, `revision`, `scope`, `profile`, `max_pages` | 1..128ページの未準備plan。モデル未loadでもCPUで確認可能 |
| `chunked` | `item_id`, `revision`, `page_ids`, `scope`, `profile` | 固定16ページ以下のchunkに分割して開始。重複なし1..128 IDs |
| `chunked/resume` | `job_id`, `scope`, `profile` | 最新の保存済みchunk jobを同じ選択で再開 |
| `cancel`（既存） | `job_id` | 現在のjob IDに一致するときだけ取消 |

scopeは既存の登録root/kind/shelf条件。`None`による暗黙scopeは拒否し、空root配列は0対象。profileは完全な現在のprofile keyを必須とし、`null`や別モデルの値は拒否。planの `max_pages` はbool/小数/0/129以上を拒否。HTTPでchunk_size/expected_job/別のpage_limitを指定して契約を緩めることはできない。Python内部の互換関数は従来の1..16 chunk_sizeを維持。

plan応答はcoverage由来の `item_id`, `source_revision`, `source_state`, `profile`, `model`, `supported`, `available`, `page_count`, `indexed_pages`, `remaining_pages`, `chunk_size`, `max_pages`, `chunks`, `total_gap_pages` と、`page_ids`, 正規化した `scope`, `chunks_total`。**`chunks`は連続した欠けの範囲、`chunks_total`は実際のatomic保存回数**。飛び飛びの欠けはpage順のID列へ平坦化して16個ずつ保存するため、この二つの数は異なる場合がある。currentでない/画像非対応ならpage IDsは空。planはその時点のsnapshotで、開始時に必ず再検査する。初回indexがない場合は404、revisionがheadと異なれば409。

開始応答は作成したjob自身のdeep copy。workerが即完了/別jobに置換されても他jobのstatusを返さない。実際の進行は既存 `GET /api/library/ai/status` で確認する。busy/scan中・元の版不一致は409、利用できない本/保存jobは404、不正/別scope・profile・選択不一致/完了済みの再開は400、モデルが未設定・画像入力非対応・閉鎖中は503。400/404にはCoreの日本語エラー表示を追加。

## 保存と再開の安全性

- profile別の既存 `ai_state` に `job='book-pages-chunked'`, job ID, item/revision, 正規化scope, profile key, 固定page IDs, chunk_size, total/chunks_total/chunks_completed, processed/indexed/reusedを保存。新しいDB schemaは不要。**保存される再開jobは最新1件だけ**。別のAI jobを開始すると古い再開記録は置換されるが、完成vectorは保持される。
- 再起動時にrunning/cancellingは既存VectorStoreの処理でinterruptedとなる。自動でworkerを作らず、明示resumeを待つ。保存されたpage IDs/profile/chunk_sizeのない旧jobは再開拒否し、新しいplanを確認する。vectorを削除して代用しない。
- resumeが保存jobを読んだ後に別jobへ置換されても、開始guard内でexpected job/終端状態とscope/profile/選択を再検査し、新しいjobを上書きしない。失敗した再開も保存状態を変更しない。
- AI worker/inference lockは既存単一・複数本・通常AI索引と共有。planではcoverageの非再入AI guardをネストしない。coverage後にAI→catalogの順でlockを取り、scope/source/page構成を再確認。モデル推論中はcatalog guardを保持しない。
- 各chunkの前とatomic公開前に現在のscope/root/head/物理版を検査。途中で登録解除・除外・元ファイル変更が起きた場合は次のchunkを推論せず停止する。公開済み旧revisionは保存されても、検索の現行版確認で非currentを返さない。手動タグ・棚・お気に入り・原本bytes/mtimeは変更しない。
- `processed` は試行済み処理、`indexed`/`chunks_completed`はjobが記録した公開済み範囲（再利用を含む）。process終了がvector commitとstate保存の間ならカウンターが遅れる可能性がある。再開時は固定全選択を検査してvectorを再利用し、カウンターだけで処理を飛ばさない。全128ページを一つのtransactionにしない。

## 検証・現在の制限

- 新規 `tests/test_page_chunks.py` は生成145ページCBZだけを使用。128ページ/8chunk上限、16ページ完了→次chunk取消→再起動→残17ページだけ推論、interruptedの非自動再開、失敗chunk未公開、除外後の推論停止、別scope/profile/物理版/新job拒否、plan後の競合、HTTP認証/Origin/厳格fields/所有cancel、飛び飛びの欠けと実chunk数、呼出元/初期応答の変更耐性を確認する。実モデル精度/実GPU速度の測定ではない。
- 既存page semantics/batch/coverage 33件PASS（30.828秒）。新規14件+エラー表示3件の対象17件PASS（32.236秒）、追加2競合/gap検査PASS（2.505秒）。最終全体/Core/Releaseは[最新handoff](codex-handoff.md)を参照。
- 初回の対象runは新planがcoverageをAI guard内から呼んだため停止。所有テストPIDだけ停止してログを保持（`data/page-chunks-target-initial-stalled-20261017.log`）。ロック取得順を修正し、2秒の取得上限を使う回帰テストを追加した。成功runだけで初回停止を隠さない。
- 2026-10-17 API実装当時はGUI接続/native未実装。2026-10-18の接続と検証は上の最新節を参照。前回の複数本取消画面1 PNGは引き続き静止画レビュー未完。既存の自動再試行上限を迂回しない。全体queue履歴・複数冊の長い範囲同時追加・私物/1TB一括実測は未完成。
- 新依存/モデルdownload・専用OCR・新たな私物scan・GitHub Actions起動なし。代表14枚の実モデル評価は再実行していない。[既存実測](representative-asset-evaluation.md)と[多数本CPU測定](page-search-performance.md)を保持。combined/RRFの順位調整も今回行わない。

再現：`python -m unittest discover -s tests -p test_page_chunks.py`（app/toolsをfixtureがpathへ登録）。全体は `python -m unittest discover -s tests`。

上記WinUI接続まで完成。[既存複数本UI](page-batch-indexing.md)と[CPU検索の計測](page-search-performance.md)を保持し、次作業は[最新handoff](codex-handoff.md)を参照。一般queue履歴/全冊自動処理は未実装、P0品質枠2/2/OCR保留を継続。
