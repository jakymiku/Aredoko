# Restore review follow-up

## 2026-10-24 owned restore handoff continuation

Added per-launch restore request/closure receipts in `app/restore_handoff.py`. Authenticated `/api/library/restore/restart` requires explicit consent/current completed owned job, freezes discard/replacement, and publishes only an owned staging reference. Enabled only when Portable launcher supplied session directory (default launch-settings path). Backend emits closure proof only after its resource ExitStack succeeds; job close timeout prevents proof. Launcher requires both owned child exit codes0 plus proof and old catalog kernel lease before switching, then rereads settings and relaunches under the same launcher lease. Only the first launch emits the original bootstrap ready signal. No GUI hookup yet; backup.restore_supported remains false. Existing startup rollback remains.

Evidence: restore HTTP3 PASS/2.510s; switch22 PASS/8.461s; lifecycle10 PASS/16.016s. Handoff first6 had5PASS/1 wrong exception expectation (StoragePathError, not FileNotFoundError); corrected6 PASS then added real generated backend test: final7 PASS/2.238s. This covers authenticated staging/restart request, actual stdin-owned backend normal exit, closure proof, released catalog lock and cutover, plus simulated frontend exit and owner-loop reuse. Does NOT prove native frontend closure/relaunch/ready, GUI dirty handling or packaged acceptance. No GUI/GPU test performed, no installed Alpha or normal user DB changed.

Next: Core RestoreClient restart capability/request + WinUI settings selection/progress/cancel/discard/explicit restart using existing dirty-transition guard. GUI/GPU tests require notifying/asking user first per current goal. P5 partial, do not skip to P6 or mark goal complete. No shutdown. Active goal continues; commit boundary is a resumable checkpoint, not quota exhaustion.


## 2026-10-24 継続作業の終了チェックポイント

実装HEAD `1ca11d4`。開始 `2e416eb` から5単位を継続実装。利用枠used88%で大きな作業を止め、保存・確認・引き継ぎへ移行。シャットダウンなし。

- `1630047`: 取消と完了の競合、ワーカー動作中の削除、既存展開先の削除を修正。ZIP上限を復号前に検査し、CRCは取消可能な展開で確認。
- `13afabc`: 起動中backupのフォルダ形式とZIPを共通復元へ接続。認証付き GET `/api/library/restore`、POST `/start`・`/cancel` とCore `LibraryApi.Restores`。公開APIからステージング先やDB切替は指定不可。
- `b4363c8`: 切替直前の復元receipt/全payload hash/schema/config検証、プロセス間排他、壊れた既存設定の保全、旧ai_profileによる復元設定の上書きを修正。
- `7072578`: 明示同意付き `/discard` とCore操作。終了済みの所有ステージングだけを破棄し、選び直せる。動作中・別job・所有同一性不一致は拒否。
- `1ca11d4`: 実frontend ready handshakeなしの復元確定を拒否してrollback。commit時にも現在DBとpending対象の一致を検証。

確認: jobs25 PASS/3.610s（初回の新規directoryテストは親未作成で失敗→修正）、HTTP3 PASS/2.432s（discard追加後）、switch22 PASS/8.387s（途中のmock poll回数不足1件は修正）、storage_backup28 PASS/23.428s、最終lifecycle10 PASS/15.935s。Core全runner exit0（新規4assert）、最終Core build0errors/0warnings。Portable build0errors/既知WUI1001×3、23.12s（discard追加前、追加後Coreのみ再build）。生成データのみ。GUI/GPU/全体性能/新配布版は未検証。旧Alpha/通常DB/元メディア未変更。

**次の1件**: 所有ランチャーの復元再起動プロトコルを接続する。ユーザーの未保存編集→所有ジョブの正常停止→backendのDB閉鎖確認→検証済みステージングの切替→同じlauncher所有下で再起動→readyで確定/失敗rollback。通常DBを開いたままapplyしない。実装済みAPIは準備だけで `switch_supported=False`、backup側`restore_supported=False`のまま。WinUIの選択/準備進捗/中止/破棄と明示再起動ボタンはこの所有境界が確定後に接続する。P5未完、P6へ飛ばさない。

残点: 起動を跨ぐ準備済みjobの再接続/不要stage掃除、tagger/profile選択の完全な復元意味、切替の電源断耐性・全異常系、native受入。既存GUI試行上限は別名でリセットしない。準備API/Coreがあることを「GUIから復元可能」と報告しない。今回の変更でロードマップ全体を完了扱いにしない。


## 2026-10-24 restore review correction

Reviewed a821c07 against current source. P5 is PARTIAL, not ready to skip to P6: production_server still reports restore_supported=False; RestoreJobManager/apply_restore_switch have no production GUI/API caller. Owned job shutdown, unsaved edits, restart and packaged launch integration still need implementation/acceptance.

Fixed rollback handling for non-object JSON sentinels (previously AttributeError), invalid rollback copies (previously overwrote current settings with invalid JSON), and missing recovery information (previously erased evidence and falsely reported success). Preserve current settings and sentinel when safe recovery cannot be established. Tests: test_restore_switch.py 15 PASS /3.875s, generated temporary data only; no GUI/GPU or full regression replay. No installed Alpha update or shutdown.

Next: review packaged import path (launcher imports restore_switch from ROOT/app whereas packaged backend lives under backend/app), restored config/vector/profile paths, source/destination ownership and switch serialization before exposing restore. These are review targets, not verified fixes. Then wire authenticated restore staging and explicit restart into native settings. Existing GUI caps remain. This focused correction does not constitute a full audit of a821c07.


## Launcher follow-up (2026-10-24)

Rollback-reloaded settings now receive the same writable-location validation as initial settings, including ai_profiles_dir. A restored pointer cannot bypass the release-directory write prohibition. Launcher explicitly selects backend/app in packaged layout; release_runtime already inserted that directory, so this was implicit dependency cleanup, not proof of an existing import failure.

Focused restore16 PASS (3.722s); lifecycle10 PASS (15.933s). No native GUI/build rerun for Python-only change. Next remains restore ownership/serialization and config/vector mapping review, then authenticated restore API/native restart integration. P5 remains partial; no Alpha replacement/shutdown.

## Restore worker ownership correction

Cancellation now only requests the worker to stop; it does not remove an in-use staging directory or claim terminal completion while the worker still runs. Completion and accepted cancellation share the job lock. Cleanup validates ordinary paths and creation identity; a pre-existing extraction directory is refused and preserved. ZIP limits are checked before payload decoding; CRC is checked during bounded extraction rather than an uncancellable testzip pass. Duplicate/case-aliased/backslash/colon entries are rejected and files are created exclusively. Related23 tests PASS/3.437s, including live-worker cancel, pre-existing canary preservation and limit-before-decode. P5 still partial; next support the directory bundles produced by the existing live backup and connect authenticated staging.

## Authenticated restore preparation and Core connection

Native directory bundles and ZIPs share existing restore validation; original backup is retained. Initial new directory test failed (missing parent); fixed and final jobs25 PASS/3.610s. Added GET /api/library/restore and POST /start, /cancel under existing session/Origin/strict JSON rules. Caller cannot select staging or switch current DB; one active/ready job, status hides internal paths/raw errors. Shutdown closes worker. HTTP3 PASS/2.349s (real generated bundle, auth, search during cancellation, duplicate ready rejection). Core RestoreClient connected through LibraryApi; Core runner exit0 with four new assertions; Portable0 errors/known3 WUI1001 warnings23.12s. Native UI and restart switch not connected; restore_supported remains false intentionally. Next validate restored bytes/receipt immediately before switching, then owned launcher restart protocol and UI.

## Switch preflight and serialization

Cutover now validates the recovery receipt using shared manifest rules and checks listed hashes, schema/profile identities and config before moving staging. Tests now use real backup→restore bundles, replacing invalid hand-written fixtures. Existing invalid launch settings are rejected before moving data; an old ai_profile override is removed only when restored AI settings are present (rollback restores it). Apply/commit/rollback/pending checks share an interprocess lease with nested-call support; orphan rollback files block new cutovers. Final switch20 PASS/7.575s; shared backup28 PASS/23.428s after manifest validator extraction. These do not replace owned launcher shutdown/restart integration or native acceptance.
