# R04-A — 全scopeの未準備索引を明示的に継続するAPI

2026-10-19。R04の最初の区切りとして、CPU計画→固定範囲の開始→取消→再起動/復元→明示再開をバックエンドへ追加する。既存の1回最大10,000件の索引上限を維持し、同じ先頭範囲だけを繰り返さず未準備へ進む。**このAPIは既存WinUIに未接続**で、R04全体のDONEではない。次はR04-BのCore/既存AI設定画面への接続。新規管理画面・一般queue・自動全件索引は追加しない。

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

## 開始と取消

`POST /api/library/ai/index/start`:

```json
{"plan_id":"サーバー発行ID","scope":{},"profile":"同じprofile key"}
```

期限/最新preview・scope/profile・直前の保存job・root定義・全selected revision/signatureを再確認してから開始する。空の計画や変更済み計画では新jobを保存しない。追加された同root内の新itemは固定upper-IDより後として今回含めず、次の計画で扱う。root追加/解除・除外/登録設定変更、selected metadata/candidate変更は再確認を要求する。

既存`AISearch._build`とinference lock・1item単位のvector公開を再利用し、legacy `start/coverage`・本の16page atomic/128page chunk/8冊batchを維持する。新modeはpublish前にcatalog guard内でselected条件を照合し、全範囲終了前にも確認する。保存済み通常/未承認vectorは再利用する。通常jobで拾える本は従来どおり表紙までで、内部pageを勝手に追加しない。

取消は既存の`POST /api/library/ai/cancel`を使う。この旧APIは最新索引job共通であり、search用request ID/本page用job-ID取消とは違う。**R04専用のjob所有取消APIはこの区切りでは未追加**。R04-Bのクライアント接続で古い操作が別jobを止めない導線を検討する。encode/OS I/Oを強制killせず、処理の戻りで取消を検出する。

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

## 検証と残り

開始HEAD `b659367`。生成素材・模擬encoderによるCPU契約であり、実GPU品質/1TB/RSS/p95/新GUI受入の結果ではない。新規19件は、複数range・cancel/restart/cache reuse・追加ID・変更拒否・期限/二重/古いjob・保存record破損・pending signature/未準備・HTTP認証/再開・backup/restore・実10,001metadata境界を確認。先頭10,000件を保存済みにしたfixtureで10,001件目だけを選び、1回のencodeで全体remaining=0へ到達する。

初回14件中3FAILは実装編集でcancel_buildからworker内ローカル`saved()`を参照した誤り。同APIを元のstate保存へ戻し14PASS、その後補強19PASS。失敗logを上書きしない。最終全体/専用環境の結果は最新handoffを参照。

次：**R04-B**でCoreのstrict parser/取消所有・既存AI設定の簡潔なplan→start/resume導線へ接続し、旧prefixボタン/本page再開を保持する。実機受入は変更箇所をR14へ積む。R04がつながってからR05動画起点類似、R06音声方式設計へ進む。P0累積2/2・OCR保留・全機能/簡潔GUI、私物/原本保護、Actionsなし、既存Draft PR5/main未mergeを維持する。

最終CPU回帰：全Python589件（586 PASS/3 platform SKIP）・専用Python3.11対象106 PASS・Core528 PASS。全体時に旧shutdownテストの期待例外がthread外へ出たため、fixtureだけを型照合へ補強し、対象11件を別途PASS。全体結果はfixture補強前の1回で、補強後の全体再実行ではない。raw log/JSONは`data/large-library/r04a-checks-20261019-01/`、詳細時間と未実機は最新引き継ぎ参照。
