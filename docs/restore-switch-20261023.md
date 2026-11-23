# P5 Safe Restore Switch & Startup Failure Rollback（2026-10-23・最新）

バックアップZIPバンドルからの安全な復元（リストア）について、新規ステージング先での事前完全検証、所有ランチャー設定のアトミック切替、および起動ready到達前失敗時の自動ロールバック機構を実装した。

## 1. 実装の要点

### A. ステージング復元ジョブ (`app/restore_jobs.py`)
- `RestoreJobManager` / `RestoreJob`:
  - 認証済みまたは所有ランチャーから安全なバックグラウンドジョブとして実行。
  - `storage_backup.restore()` を使用し、独立した一時ステージングディレクトリに展開・検証。
  - Zip Slip / Directory Traversal 対策（`resolve().is_relative_to()`）、Symlink/Reparse Point 排除、SQLite companion files (`-wal`, `-shm`, `-journal`) 排除、`MAX_FILES = 148` および `max_bytes` 上限を厳格適用。
  - 中止（`cancel`）要求時は抽出・ステージングディレクトリを安全に削除してキャンセル状態へ移行。
  - 本番ポインタや既存DBには一切触れず、ステージング完了まで隔離。

### B. 安全なアトミック起動切替とロールバック (`app/restore_switch.py`)
- `apply_restore_switch(data_dir, staging_path, restore_id=None)`:
  - 検証済みのステージングディレクトリを `data_dir / 'restores' / <restore_id>` へ移動。
  - 既存の `launch-settings.json` を `data_dir / 'launch-settings.rollback.json'` へバックアップ。
  - センチネルファイル `data_dir / 'restore-pending.json'`（`attempted: False`）を作成。
  - `launch-settings.json` の `database`（および存在する設定・プロファイル）を新ディレクトリへアトミックに指向更新。
- `commit_restore_switch(data_dir)`:
  - アプリケーションが `ready` 状態に到達した時点で呼び出される。
  - `restore-pending.json` およびロールバック用バックアップを削除し、`restore-history.json` に正常復元レシートを記録。
- `rollback_restore_switch(data_dir, error=None)`:
  - アプリ起動中（`ready` 到達前）に例外・クラッシュ・タイムアウトが発生した場合に呼び出される。
  - `launch-settings.rollback.json` から `launch-settings.json` を復元（以前設定が存在しなかった場合は削除）。
  - `restore-pending.json` を削除し、`restore-history.json` にロールバックイベントとエラー詳細を記録。
- `check_pending_restore(data_dir)`:
  - 電源断や予期せぬ外部プロセス強制終了により `ready` 未到達のまま落ちていた場合、次回起動時に自動検知してロールバックを実行し、既存の正常な通常データで再起動。

### C. ランチャー統合 (`tools/launch_release.py`)
- `launch()` 開始時（`storage_lease` 取得後）に `check_pending_restore(data)` を実行。未完了復元のロールバックがあれば設定を安全に再読込。
- `run_session()` において `ready` 到達時に `commit_restore_switch(effective_data)` を実行。
- `run_session()` および `launch()` の例外捕捉部において、`ready` 前エラー発生時に `rollback_restore_switch()` を確実に実行。

## 2. 検証結果

- **単体テスト (`tests/test_restore_jobs.py`)**: 20 tests PASS / 3.155s
  - 正常ZIPステージング、破損ZIP拒否、欠損manifest/catalog拒否、不正SHA-256拒否、Zip Slip拒否、symlink拒否、companion files拒否、途中キャンセル時クリーンアップ、属性/辞書アクセス互換。
- **切替＆ロールバックテスト (`tests/test_restore_switch.py`)**: 12 tests PASS / 3.252s
  - 正常切替→起動ready→commitのレシート記録、起動失敗時の自動ロールバックと元DB保全、前回異常終了（attempted=True）の次回起動時自動ロールバック、壊れたセンチネルの安全ロールバック。
- **既存バックアップ・ライフサイクル回帰テスト**:
  - `test_storage_backup.py` 28 tests PASS
  - `test_live_backup.py` 8 tests PASS
  - `test_release_lifecycle.py` 10 tests PASS
- **C# Core テスト**: 925+ assertions PASS
- **WinUI x64 Release ビルド**: 0 errors / 既知の 5 warnings (WUI1001×3, IL2104×2)
- **実データ保全**: `%LOCALAPPDATA%\Aredoko` および `Aredoko-test` は完全に未変更・不変。
