# 長い本の分割追加：明示plan/start/resume API

2026-10-17。既存の `next_gaps` / `start_chunked` を、安全なローカルAPI・固定選択の永続化・再起動後の明示再開へ接続した。**今回完成したのはバックエンドAPIであり、WinUIのボタン/クライアント接続は次の段階**。既存GUIの単一範囲16ページ・複数本8冊/計128ページはそのまま利用できる。専用OCRは保留し、通常AI buildで本文全体を自動解析しない。

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
- GUI接続/native操作は今回は未実装・未検証。前回の複数本取消画面1 PNGは引き続き静止画レビュー未完。既存の自動再試行上限を迂回しない。全体queue履歴・複数冊の長い範囲同時追加・私物/1TB一括実測は未完成。
- 新依存/モデルdownload・専用OCR・新たな私物scan・GitHub Actions起動なし。代表14枚の実モデル評価は再実行していない。[既存実測](representative-asset-evaluation.md)と[多数本CPU測定](page-search-performance.md)を保持。combined/RRFの順位調整も今回行わない。

再現：`python -m unittest discover -s tests -p test_page_chunks.py`（app/toolsをfixtureがpathへ登録）。全体は `python -m unittest discover -s tests`。

次は新画面を増やさず、[既存ページ追加/複数本UI](page-batch-indexing.md)に今回のplan/start/resumeを接続する。範囲確認と開始を分離し、進捗・取消を狭幅でも常時見せ、24DIP scroll gutter/16DIP pane間隔と未保存編集を維持する。
