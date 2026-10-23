# Restore review follow-up

## 2026-10-24 restore review correction

Reviewed a821c07 against current source. P5 is PARTIAL, not ready to skip to P6: production_server still reports restore_supported=False; RestoreJobManager/apply_restore_switch have no production GUI/API caller. Owned job shutdown, unsaved edits, restart and packaged launch integration still need implementation/acceptance.

Fixed rollback handling for non-object JSON sentinels (previously AttributeError), invalid rollback copies (previously overwrote current settings with invalid JSON), and missing recovery information (previously erased evidence and falsely reported success). Preserve current settings and sentinel when safe recovery cannot be established. Tests: test_restore_switch.py 15 PASS /3.875s, generated temporary data only; no GUI/GPU or full regression replay. No installed Alpha update or shutdown.

Next: review packaged import path (launcher imports restore_switch from ROOT/app whereas packaged backend lives under backend/app), restored config/vector/profile paths, source/destination ownership and switch serialization before exposing restore. These are review targets, not verified fixes. Then wire authenticated restore staging and explicit restart into native settings. Existing GUI caps remain. This focused correction does not constitute a full audit of a821c07.


## Launcher follow-up (2026-10-24)

Rollback-reloaded settings now receive the same writable-location validation as initial settings, including ai_profiles_dir. A restored pointer cannot bypass the release-directory write prohibition. Launcher explicitly selects backend/app in packaged layout; release_runtime already inserted that directory, so this was implicit dependency cleanup, not proof of an existing import failure.

Focused restore16 PASS (3.722s); lifecycle10 PASS (15.933s). No native GUI/build rerun for Python-only change. Next remains restore ownership/serialization and config/vector mapping review, then authenticated restore API/native restart integration. P5 remains partial; no Alpha replacement/shutdown.

## Restore worker ownership correction

Cancellation now only requests the worker to stop; it does not remove an in-use staging directory or claim terminal completion while the worker still runs. Completion and accepted cancellation share the job lock. Cleanup validates ordinary paths and creation identity; a pre-existing extraction directory is refused and preserved. ZIP limits are checked before payload decoding; CRC is checked during bounded extraction rather than an uncancellable testzip pass. Duplicate/case-aliased/backslash/colon entries are rejected and files are created exclusively. Related23 tests PASS/3.437s, including live-worker cancel, pre-existing canary preservation and limit-before-decode. P5 still partial; next support the directory bundles produced by the existing live backup and connect authenticated staging.
