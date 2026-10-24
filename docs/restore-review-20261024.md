# Restore review follow-up

## 2026-10-24 final cancellation check

Implementation stays30480f8. New focused generated-only test rejects publication after derived profile settings were staged: no completed bundle, no new source settings.json, profile SHA/mtime unchanged, writer pause released and owned capture directory removed. **1 PASS/0.305s**, separate from prior live11 and switch/jobs/HTTP10; full suite not repeated. This is the capture publication boundary, not a new native cancel/API race claim. Evidence: ignored portable-refresh-20261024/active-profile-cancel.log. Source-only follow-up; ZIP still875f94a. Next dual active/pending metadata remains unchanged; no GUI/GPU/shutdown.

## 2026-10-24 explicit profile without saved settings

P5 first bounded case: production backup passes the explicit startup profile filename to live capture. If settings are selected and NO saved ai_settings exists, the backup COPY creates version1 local:<filename> settings pointing to the included validated profile. Source preferences remain absent, original profile unchanged, no new bundle format/guess by file order. The derived settings survives ordinary restored-path rebasing and rollback. Missing included profile prevents publication; metadata-only/settings-off backup remains available.

If saved/pending settings exist, their exact bytes are retained. Do not overwrite a pending choice with the startup override: preserving BOTH requires an explicit active-selection metadata contract, still TODO together with multiple tagger profiles. The initial broader overlay prototype was not adopted; its10-pass log is not final-policy evidence. Final live11 PASS/2.806s; final switch/rollback case plus backup jobs/HTTP10 PASS/4.081s separately, not21 independent tests. No C#/GUI/GPU/model/normal DB change and no full build repetition. Logs: ignored portable-refresh-20261024/active-profile-backup{,02}.log and active-profile-boundaries.log.

New source follows9ec50b1. Existing ZIP stays source875f94a and does not contain this follow-up. Next explicit metadata contract for saved pending choice + actual startup override, then multiple tagger active selection, with old bundle compatibility/cancel/rollback checks. Goal remains active; near quota handoff, no shutdown.

## 2026-10-24 committed cleanup recovery

Successful restore confirmation now writes/fsyncs an atomic committed sentinel after history publication, then removes rollback copy before sentinel cleanup. Cleanup failure returns cleanup_pending without undoing the ready library; next startup completes cleanup rather than interpreting it as a failed attempt. Explicit rollback refuses committed state. Pre-commit history failure leaves rollback available. This is process-interruption/atomic-publication handling, not proof of hardware power-loss durability on every filesystem.

Checks: switch26 PASS/10.300s plus newly added final-sentinel-deletion case1 PASS/0.407s separately (do not call it a rerun of27). New case first failed to be added due to tests-relative path mistake; no app mutation from that failed command, corrected then focused case passed. No additional GUI/GPU, no native cap reset. Next continue current P5 remaining settings/active-profile contract and packaged restart acceptance planning; require fresh approval before any new GUI scope. Active goal continues; last usage29% used, no shutdown.


## 2026-10-24 final native attempt and WD profile correction

User-authorized native restore run03 used the last of3 attempts. It failed before picker open: winapp invoke reported no invoke pattern for RestoreChooseZip, while captured tree reports enabled/invokable and both PNGs show enabled ZIP/folder buttons. Do not assert an app defect or picker/Start acceptance from this. Both PNGs viewed; restore cap3/3 EXHAUSTED, no renamed retries. Native cancel and picker→Start remain unaccepted. Cleanup initially posted main close before dialog teardown and raw report recorded frontend still running. Later verified PID37616 executable path/HWND ownership and no open dialog, sent ordinary WM_CLOSE, WaitForExit succeeded, old catalog lease reacquired. Reopened process exit code unavailable; raw report retained with post_cleanup addendum. No forced process exit/PC shutdown. Runner now waits dialog-gone before main close, source-only/not replayed.

Single restored tagger_profile now rebases launch setting to verified restored file. Previously backup copied that profile but launcher retained the old path. Omitted tagger settings preserve existing runtime selection; rollback restores previous path. Multiple tagger profiles/explicit AI command-line selection need a future explicit active-selection backup contract, not inferred selection. Latest switch24 PASS; no model loading required.

Next CPU work: strengthen interrupted cutover/recovery failure handling and document true P5 completion limits before moving P6. No new GUI/GPU runs without fresh scope/approval. Existing source and installed candidate are distinct; frontend03 belongs to GUI trial, not a released ZIP. Goal active, usage stopping threshold not reached.


## 2026-10-24 durable prepared-job continuation

Prepared stages now publish one bounded `restore-staging/prepared.json` under the same cancel/completion lock. Backend restart reattaches the exact job/source/vector choice using ordinary-path, directory identity and recovery-receipt SHA checks; no directory scan, payload DB open or automatic cutover at startup. Explicit discard removes the owned stage and its receipt; successful cutover retires the old receipt. Invalid receipt blocks only restore and preserves evidence. Native client presents the recovery guidance from status. Prior prepared metadata does not authorize a new launch's restart request.

Evidence: new prepared5 PASS/0.918s; handoff initial integration failed409 because the real backend correctly reattached the setup's existing prepared job; fixture changed to assert that ID/state rather than start a duplicate. Final handoff7 PASS/2.199s includes real process restart/reattach and closure/cutover. HTTP3 PASS/2.376s after persistence connection. Core935 assertions PASS. No additional GUI run for this unit; prior restore native2/3 remains (1 attempt left). Next prepare final native picker→Start check and independent settings/profile restoration review. Goal active; quota20% used at last check, not a stopping checkpoint. No shutdown.


## 2026-10-24 native restore UI continuation

Core `RestoreClient.RestartAsync` and typed capability/acknowledgment/source/cache-policy fields connected. Native backup settings now lead to a restore dialog with folder/ZIP selection, preparation, progress, cancel, discard, refresh and consent-gated restart. Existing dirty guard runs before opening, polling is lifetime/revision guarded and in-flight operations block dismissal. Explicit restart flushes reading progress and closes only the owned main window after acknowledgment. Restore source/cache choices reattach from backend status; operation errors survive final render. Capability `backup.restore_supported` now follows actual owned handoff availability, not a blanket false.

User explicitly authorized up to3 native restore attempts with generated assets/DB only; no GPU. Dedicated `frontend01`/`frontend02` candidates and `tools/test_native_restore.py`. run01 PASS6checks, exposed blank reattached source; source/cache roundtrip fixed. run02 PASS9checks including reattach, native discard/reprepare, consent-gated restart, two real ready handshakes, retained old catalog. Both runs each2 frontend exits0, owner finished, no residual process; source media hashes/mtimes unchanged. run02 source files unchanged during run. All8 PNGs viewed and readable. Test starts preparation via authenticated API: native Windows picker→Start, GUI cancel, dirty-dialog scenarios, Light/HC/DPI, complete packaged launcher/bootstrap remain UNVERIFIED. Uses real `run_session` and handoff but test driver loop, not a shipped ZIP. Native restore cap2/3 used; preserve older backup/shelf/P3 caps.

Checks: Core934 assertions PASS; HTTP3 PASS/2.357s after source/cache status addition; Portable build0errors/knownWUI1001×3 (25.97s), independent frontend02 publish succeeds with existing SDK IL2104×2. Candidate does not update installed Alpha. Last capability-only server edit after native run is CPU checked, not included in native source fingerprint.

Next independent P5 work: persist prepared-job ownership across backend restarts (safe explicit reattach/discard, no automatic cutover), confirm remaining tagger/profile restoration choices, then remaining focused native picker/cancel acceptance within1 remaining attempt only when prepared. P5 remains partial; no P6/full-roadmap completion claim. Notify/ask before new GUI/GPU scope. No shutdown.


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


## 2026-10-25 失敗後の再選択バグ
基本ZIP06の通常Aredoko.exe＋生成1PNG/専用DBで、破損した生成ZIPをnative picker→準備→failedへ到達。別の生成ZIPを選び直すと、Renderが前のjob.Sourceを無条件で書き戻し、表示/次回入力が元ZIPに戻る不具合を確認。`data/ai-ui/restore-rejection-20261025/run01` のrejected-0/failure PNGを目視、所有app/bootstrap exit0。元DBの切替や再起動同意はしていない。

修正は入力同期をactive/completed/restart状態へ限定し、初回表示だけは前jobの方針を復元する。failed/cancelled状態で利用者が選んだ次のsourceとAI索引の含め方を、Refresh/Primary直前Renderで上書きしない。準備中・準備完了時の凍結と再起動同意は維持。修正のnative確認は次の専用ZIP07で実施する（この節の初稿時点では未確認）。
