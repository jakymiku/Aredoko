# R04 — 全scopeの未準備索引を明示的に継続するAPI・Coreプロトコル・UI接続

2026-10-19。R04として、CPU計画→固定範囲の開始→取消→再起動/復元→明示再開の一連をバックエンド、Coreクライアント、既存WinUI AI設定へ実装完了（CPU_DONE）。既存の1回最大10,000件の索引上限を維持し、同じ先頭範囲だけを繰り返さず未準備へ進む。新規管理画面・一般queue・自動全件索引は追加しない。実機GUI受入はユーザー方針に従いR14で一括検証（`tools/test_continuation_acceptance.py`）。次はR05動画起点類似。

## 計画と件数

`POST /api/library/ai/index/plan`:

```json
{"scope":{},"profile":"現在のprofile key","limit":1000,"after_id":0}
```

既存loopbackのHost/Origin/X-Aredoko-Token認証が必要。scope/profile/limit/after_idを全て明示し、未知field・null scope・bool数値・異なるprofileを拒否する。limitは1〜10,000、after_idは0〜int64最大。Python内部呼出しではlimit=1000/after_id=0がdefault。

- CPUだけでmetadataを256件ずつ読み、保存text/必要な画像・動画input contractと、未承認タグsnapshotに対応するvectorの既存鮮度を確認する。モデル・media decode・ファイル走査・page refresh・索引jobの更新は行わない。root定義も256行ずつhashする。
- `candidate_total`はscope内のpresent/enabled/除外適用後の全候補。`fresh_total`と`remaining_total`はこの全集合で数える。非対応や解除済み等も含むcatalog全件数、物理sourceの再検証完了数、失敗件数と解釈しない。鮮度は既存coverageと同じ保存metadata/input contract/未承認タグの基準であり、未走査の物理変更まで新たに検出するAPIではない。
- `remaining_after_id`は指定cursorより後の未準備数。`selected_total`は今回選んだ最大limit件。既存prefix coverageの`target_total`と混同しない。
- `upper_id`を計画時の最大item IDに固定。selected ID・metadata revision・未承認候補signature、root構成・scope/profileを記録する。レスポンスは件数・`plan_id`・cursor等の要約だけで、大量IDや元pathを返さない。
- previewはprocess内に最新1件、300秒だけ保持。次のpreviewで置換し、再起動で消える。既存ai_state/再開記録は変更しない。計画中のcatalog/vector data_version変更を監視し、不整合な件数を公開しない。無変更の分散atomic snapshot/敵対的ABA/TOCTOU完全解消を保証するものではない。

通常は毎回after_id=0で未準備を選び直せば、準備済みは飛ばして次へ進む。失敗/未準備の対象を一旦残して後ろへ進むときに限り、利用者が結果を確認して`next_after_id`を次のafter_idへ渡せる。cursorより前の未準備が消えた/完了したとは表示しない。

## 開始と所有取消 (R04-B)

`POST /api/library/ai/index/start`:

```json
{"plan_id":"サーバー発行ID","scope":{},"profile":"同じprofile key"}
```

期限/最新preview・scope/profile・直前の保存job・root定義・全selected revision/signatureを再確認してから開始する。空の計画や変更済み計画では新jobを保存しない。追加された同root内の新itemは固定upper-IDより後として今回含めず、次の計画で扱う。root追加/解除・除外/登録設定変更、selected metadata/candidate変更は再確認を要求する。

既存`AISearch._build`とinference lock・1item単位のvector公開を再利用し、legacy `start/coverage`・本の16page atomic/128page chunk/8冊batchを維持する。新modeはpublish前にcatalog guard内でselected条件を照合し、全範囲終了前にも確認する。保存済み通常/未承認vectorは再利用する。通常jobで拾える本は従来どおり表紙までで、内部pageを勝手に追加しない。

### Job所有取消API (R04-B)

`POST /api/library/ai/index/cancel`:

```json
{"job_id":"32-hex job ID"}
```

- R04-Bで追加。32桁hexのjob_idを検証し、現在アクティブな継続job IDと照合。
- 実行中(running/cancelling)でjob IDが一致する場合のみ `cancel_requested: true` を返し中断フラグを立てる。
- 既に完了/失敗/中断済み、ID不一致、あるいは別jobの場合は `cancel_requested: false` を返し、別jobを誤って止めない。
- 既存の `/api/library/ai/cancel`（引数なし、最新job一括取消）も後方互換として維持。
- Coreの `IndexContinuationClient.CancelAsync(jobId)` から呼び出され、WinUIのCancelボタンも所有job IDを優先して呼び出す。

公開statusには`job:library-continuation-v1`、job_id・scope/profile・今回total/processed/indexed/skipped/reused・cursorを返し、内部selectionは除く。`selected_total=total`、`unready_total=skipped`。`indexed`は通常/必要なpendingが準備済みになった数、`reused`はそのうち今回encode不要だった数。`unready_total`は未準備/利用不可をまとめた既存skipped相当で、例外種類別の失敗件数ではない。`state:failed`はjob全体の例外停止で別に扱う。中断途中のprocessedは最終成功数ではない。

## 再起動と復旧

`POST /api/library/ai/index/resume`:

```json
{"job_id":"直前jobのID","scope":{},"profile":"保存時と同じprofile key"}
```

- 最新jobだけが対象。cancelled/interrupted/failedの同mode/ID/scope/profileと、版付き固定selection（最大10,000件、順序/重複/型/上限/64hex revision/signature）を検証する。別jobや破損/将来版は拒否し、推測して再選択しない。
- 再開前にcompleted分も含めてselected metadataとroot構成を再確認する。再開は同じ選択を先頭からcache確認し直し、保存済み分は再encodeしない。単純な途中cursorからの再生ではない。processed/indexedは今回の再開attemptで数え直す。
- 新job IDと`resumed_from`を保存する。旧IDで新jobを再開できない。新しい別索引jobを始めると、従来どおり最新1件の再開記録が置き換わる。履歴queueではない。
- 固定selectionは既存ai_state JSONに保存し、新table/columnは増やさない。R03 backup v1でそのまま保持。running/cancellingは既存VectorStore起動時にinterruptedとなり、**自動scan/モデルload/索引再開なし**。復旧しても元scope/profile/sourceの検査を迂回しない。将来recordの意味を変えるときは版/復旧互換も同時に扱う。

## Core厳格プロトコル (R04-B)

`src/Aredoko.Core/IndexContinuation.cs`:
- `System.Text.Json` のreflection完全無効（Aredoko.Core方針）に準拠し、`JsonDocument` / `JsonObject` 手動パース。
- `IndexContinuationRequests`: `PlanRequest`, `StartRequest`, `ResumeRequest`, `CancelRequest` の厳格な引数検証（null/空/範囲外を拒否）。
- `IndexContinuationPlan`: plan_id, candidate_total, fresh_total, remaining_total, remaining_after_id, selected_total, upper_id, next_after_id。
- `IndexContinuationStatus`: job_id, state, mode, selected_total, unready_total, processed_total, indexed_total, reused_total, percent, error_message, cancel_requested, resumed_from。
- `IndexContinuationClient`: `LibraryApi.Continuation` として公開。
- `tests/Aredoko.Core.Tests/IndexContinuationTests.cs`: 61チェック（境界値、型不正、破損JSON、キャンセル応答照合・破損ペイロード検査等）。Core全体 589 PASS。

## WinUI AI設定画面統合 (R04-C)

`src/Aredoko.WinUI/MainPage.xaml.cs`:
- AI設定画面の `indexInfo` パネル内に簡潔な継続操作コントロールを配置（自動生成/レイアウト崩れ防止）：
  - `PlanAIContinuation` (`planContinuation`): 選択中scope/profileで未準備候補を計算し、`AIContinuationSummary` (`continuationText`) に「未索引: X件 / 今回選択: Y件 (全候補: Z件)」のように表示。ナレーター用 `AutomationProperties.SetName` を配備。
  - `StartAIContinuation` (`startContinuation`): 計画済みの有効な `plan_id` かつ `activeProfile` が一致する場合のみ有効化。明示開始し、返却されたjob IDを即座に `ownedContinuationJob` として追跡（失敗時は計画を自動破棄）。
  - `ResumeAIContinuation` (`resumeContinuation`): 保存状態に中断/取消済みの継続jobが存在する場合に有効化。
  - `CancelAIIndex`: 連打防止（クリック直後に無効化）。所有job ID（本ページjobまたは継続job `ownedContinuationJob`）が存在する場合は所有取消API（`CancelAsync`）を呼び出し、なければフォールバック取消を実行。
- scopeやprofileの変更時に計画を即時無効化（誤開始を防止）。profile値のnull安全性を確保。
- 既存の先頭1万件prefixビルドボタン（`StartAIIndex`）および本のページ追加ダイアログ・複数冊ジョブは完全保持。
- WinUI x64 Releaseビルド: 警告0 / エラー0。

## 検証と状態

- **全Python回帰**: 590 tests (587 PASS, 3 platform SKIP, 0 FAIL, 0 ERROR)。
- **Python targeted (7 files, 105 tests)**: 105 PASS (106.0s)。
- **Core Tests**: 589 checks PASS。
- **WinUI x64 Release**: 警告0 / エラー0。
- **検証ハーネス**: `tools/test_continuation_acceptance.py` (--stage cpu PASS)。実GUI/GPUテストはユーザー指示により延期し、`--stage gui` / `--stage gpu` をR14一括受入用に完全実装。
- **状態**: **R04 CPU_DONE**。次は **R05 動画起点類似**。

