"""Safe atomic restore pointer switch and ready-failure rollback.

Implements safe target directory placement, atomic launch-settings switch,
sentinel-based crash recovery, and history recording for Aredoko.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import threading
from functools import wraps

from storage_lease import plain_path, storage_parent, storage_lease
from storage_backup import CATALOG, validate_restored

PENDING_FILE = 'restore-pending.json'
ROLLBACK_FILE = 'launch-settings.rollback.json'
LAUNCH_SETTINGS_FILE = 'launch-settings.json'
HISTORY_FILE = 'restore-history.json'
RESTORES_DIR = 'restores'

RESTORE_ID_PATTERN = re.compile(r'^[0-9a-fA-F_-]{8,64}\Z')


class RestoreSwitchError(RuntimeError):
    """Raised when restore switch or rollback cannot proceed safely."""


_switch_lock = threading.RLock()
_switch_owner = threading.local()


def _serialized(operation):
    @wraps(operation)
    def invoke(data_dir, *args, **kwargs):
        data_path = plain_path(data_dir, directory=True)
        with _switch_lock:
            held = getattr(_switch_owner, 'paths', set())
            if data_path in held:
                return operation(data_path, *args, **kwargs)
            with storage_lease(data_path / 'restore-switch'):
                _switch_owner.paths = held | {data_path}
                try:
                    return operation(data_path, *args, **kwargs)
                finally:
                    _switch_owner.paths = held
    return invoke


def is_restore_pending(data_dir):
    """Return True if a restore switch is currently pending."""
    data_path = Path(os.path.abspath(data_dir))
    return (data_path / PENDING_FILE).is_file()


def get_restore_pending_info(data_dir):
    """Return the contents of restore-pending.json if present, else None."""
    data_path = Path(os.path.abspath(data_dir))
    pending_path = data_path / PENDING_FILE
    if not pending_path.is_file():
        return None
    try:
        return json.loads(pending_path.read_text(encoding='utf-8-sig'))
    except Exception:
        return None


def get_restore_history(data_dir):
    """Return the list of restore history entries recorded in restore-history.json."""
    data_path = Path(os.path.abspath(data_dir))
    history_path = data_path / HISTORY_FILE
    if not history_path.is_file():
        return []
    try:
        raw = json.loads(history_path.read_text(encoding='utf-8-sig'))
        if isinstance(raw, dict) and isinstance(raw.get('entries'), list):
            return raw['entries']
        elif isinstance(raw, list):
            return raw
    except Exception:
        return []
    return []


def _record_history(data_path, entry):
    """Append a receipt entry to restore-history.json atomically."""
    history_path = data_path / HISTORY_FILE
    entries = []
    if history_path.is_file():
        try:
            raw = json.loads(history_path.read_text(encoding='utf-8-sig'))
            if isinstance(raw, dict) and isinstance(raw.get('entries'), list):
                entries = raw['entries']
            elif isinstance(raw, list):
                entries = raw
        except Exception:
            entries = []
    entries.append(entry)
    data = {
        'format': 'aredoko-restore-history',
        'version': 1,
        'entries': entries,
    }
    tmp = data_path / f".{HISTORY_FILE}.tmp.{secrets.token_hex(8)}"
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    tmp.replace(history_path)
    plain_path(history_path)


@_serialized
def apply_restore_switch(data_dir, staging_path, restore_id=None):
    """Move/place verified staging into data_dir / 'restores' / <restore_id> and switch settings.

    1. Validates data_dir and staging_path using plain_path checks.
    2. Ensures staging contains verified catalog and no live SQLite companion files.
    3. Moves staging directory to data_dir / 'restores' / <restore_id>.
    4. Backs up current launch-settings.json to launch-settings.rollback.json.
    5. Creates restore-pending.json sentinel recording previous settings and target dir.
    6. Atomically updates launch-settings.json pointing database/settings to restore directory.

    Returns:
        dict: receipt with restore_id, target_restore_dir, settings, and pending status.
    """
    data_path = Path(os.path.abspath(data_dir))
    staging = Path(os.path.abspath(staging_path))
    plain_path(data_path, directory=True)
    plain_path(staging, directory=True)

    if (data_path / PENDING_FILE).exists() or (data_path / ROLLBACK_FILE).exists():
        raise RestoreSwitchError("A restore switch is already pending")

    staging_catalog = staging / CATALOG
    if not staging_catalog.is_file():
        raise RestoreSwitchError(f"Staging directory missing {CATALOG}")
    plain_path(staging_catalog)

    if any(Path(str(staging_catalog) + s).exists() for s in ('-wal', '-shm', '-journal')):
        raise RestoreSwitchError("Staging catalog has live SQLite companion files")

    try:
        restored_report=validate_restored(staging)
    except (ValueError, RuntimeError, OSError) as error:
        raise RestoreSwitchError('Staging verification failed; current library preserved') from error

    if restore_id is None:
        restore_id = secrets.token_hex(16)
    else:
        if not isinstance(restore_id, str) or not RESTORE_ID_PATTERN.fullmatch(restore_id):
            raise ValueError(f"Invalid restore ID: {restore_id}")

    restores_base = data_path / RESTORES_DIR
    storage_parent(restores_base / 'marker')
    target_restore_dir = restores_base / restore_id

    if target_restore_dir.exists():
        raise RestoreSwitchError(f"Restore target directory already exists: {target_restore_dir}")

    if staging.resolve() == target_restore_dir.resolve() or staging.resolve() in data_path.resolve().parents:
        raise RestoreSwitchError("Invalid staging path overlap")

    launch_settings_path = data_path / LAUNCH_SETTINGS_FILE
    rollback_path = data_path / ROLLBACK_FILE
    previous_settings_existed = launch_settings_path.is_file()
    previous_settings = {}

    if previous_settings_existed:
        plain_path(launch_settings_path)
        try:
            previous_settings = json.loads(launch_settings_path.read_text(encoding='utf-8-sig'))
            if not isinstance(previous_settings, dict):
                raise RestoreSwitchError('Existing launch settings are not an object')
        except Exception as e:
            raise RestoreSwitchError(f"Failed to read existing launch settings: {e}") from e

    try:
        shutil.move(str(staging), str(target_restore_dir))
    except Exception as e:
        raise RestoreSwitchError(f"Failed to place staging directory into target: {e}") from e

    plain_path(target_restore_dir, directory=True)
    plain_path(target_restore_dir / CATALOG)

    if previous_settings_existed:
        tmp_rollback = data_path / f".{ROLLBACK_FILE}.tmp.{secrets.token_hex(8)}"
        tmp_rollback.write_text(json.dumps(previous_settings, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        tmp_rollback.replace(rollback_path)
        plain_path(rollback_path)

    new_settings = dict(previous_settings)
    new_settings['database'] = str((target_restore_dir / CATALOG).resolve())

    restored_ai_settings = target_restore_dir / 'settings' / 'ai-settings.json'
    if restored_ai_settings.is_file():
        new_settings['ai_settings'] = str(restored_ai_settings.resolve())
        # The selected profile in the restored settings must not be overridden
        # by a command-line profile retained from the old library.
        new_settings.pop('ai_profile', None)

    restored_viewer_settings = target_restore_dir / 'settings' / 'viewer-settings.json'
    if restored_viewer_settings.is_file():
        new_settings['viewer_settings'] = str(restored_viewer_settings.resolve())

    # Online backup captures the explicitly configured active tagger profile.
    # Rebase the sole restored profile instead of retaining a path to the old DB.
    tagger_entries=[entry for entry in restored_report['entries'] if entry['role']=='tagger_profile']
    if len(tagger_entries)==1:
        new_settings['tagger_profile']=str((target_restore_dir/tagger_entries[0]['path']).resolve())

    restored_profiles = target_restore_dir / 'profiles'
    if restored_profiles.is_dir():
        new_settings['ai_profiles_dir'] = str(restored_profiles.resolve())

    pending_path = data_path / PENDING_FILE
    pending_data = {
        'format': 'aredoko-restore-pending',
        'version': 1,
        'restore_id': restore_id,
        'target_restore_dir': str(target_restore_dir.resolve()),
        'created_at': datetime.now(timezone.utc).isoformat(),
        'previous_settings_existed': previous_settings_existed,
        'previous_settings': previous_settings,
        'rollback_file': str(rollback_path.resolve()) if previous_settings_existed else None,
        'attempted': False,
        'status': 'pending',
    }
    tmp_pending = data_path / f".{PENDING_FILE}.tmp.{secrets.token_hex(8)}"
    tmp_pending.write_text(json.dumps(pending_data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    tmp_pending.replace(pending_path)
    plain_path(pending_path)

    tmp_settings = data_path / f".{LAUNCH_SETTINGS_FILE}.tmp.{secrets.token_hex(8)}"
    tmp_settings.write_text(json.dumps(new_settings, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    tmp_settings.replace(launch_settings_path)
    plain_path(launch_settings_path)

    return {
        'restore_id': restore_id,
        'target_restore_dir': str(target_restore_dir.resolve()),
        'settings': new_settings,
        'previous_settings': previous_settings,
        'pending_file': str(pending_path.resolve()),
        'status': 'pending',
    }


@_serialized
def commit_restore_switch(data_dir):
    """Commit the pending restore switch upon reaching ready state.

    1. Cleans up restore-pending.json and launch-settings.rollback.json.
    2. Records successful restoration receipt in restore-history.json.

    Returns:
        dict: receipt of the committed restoration, or None if no restore was pending.
    """
    data_path = Path(os.path.abspath(data_dir))
    pending_path = data_path / PENDING_FILE
    if not pending_path.is_file():
        return None

    try:
        pending_data = json.loads(plain_path(pending_path).read_text(encoding='utf-8-sig'))
        if not isinstance(pending_data, dict):
            raise ValueError('Pending record must be an object')
        restore_id = pending_data.get('restore_id')
        if not isinstance(restore_id, str) or RESTORE_ID_PATTERN.fullmatch(restore_id) is None:
            raise ValueError('Invalid restore identity')
        target = plain_path(data_path / RESTORES_DIR / restore_id, directory=True)
        target_dir = pending_data.get('target_restore_dir')
        if not isinstance(target_dir, str) or Path(target_dir) != target:
            raise ValueError('Restore target changed')
        current = json.loads(plain_path(data_path / LAUNCH_SETTINGS_FILE).read_text(encoding='utf-8-sig'))
        if not isinstance(current, dict) or current.get('database') != str(target / CATALOG):
            raise ValueError('Current launch target does not match pending restore')
    except (ValueError, OSError) as error:
        raise RestoreSwitchError('Cannot confirm restore; recovery evidence preserved') from error

    receipt = {
        'restore_id': restore_id,
        'target_restore_dir': target_dir,
        'switched_at': pending_data.get('created_at'),
        'committed_at': datetime.now(timezone.utc).isoformat(),
        'status': 'committed',
    }

    if target_dir and Path(target_dir).is_dir():
        rec_json = Path(target_dir) / 'recovery.json'
        if rec_json.is_file():
            try:
                receipt['recovery_meta'] = json.loads(rec_json.read_text(encoding='utf-8-sig'))
            except Exception:
                pass

    if pending_data.get('status')!='committed':
        _record_history(data_path, receipt)
        pending_data['status']='committed'
        pending_data['committed_at']=receipt['committed_at']
        temporary=data_path/f'.restore-commit-{secrets.token_hex(8)}'
        try:
            with temporary.open('x',encoding='utf-8') as stream:
                json.dump(pending_data,stream,ensure_ascii=False)
                stream.flush();os.fsync(stream.fileno())
            temporary.replace(pending_path)
        finally:
            if temporary.exists():temporary.unlink()
    else:
        receipt['committed_at']=pending_data.get('committed_at')

    # Once marked committed, cleanup failures must never undo a ready library.
    # Delete the rollback copy first so the committed sentinel remains as proof.
    try:
        (data_path/ROLLBACK_FILE).unlink(missing_ok=True)
        pending_path.unlink(missing_ok=True)
    except OSError:
        receipt['cleanup_pending']=True
    return receipt


@_serialized
def rollback_restore_switch(data_dir, error=None):
    """Roll back launch-settings.json from launch-settings.rollback.json on startup failure.

    1. Restores launch-settings.json from launch-settings.rollback.json (or deletes it
       if previous_settings_existed was False).
    2. Removes restore-pending.json and records rollback event in restore-history.json.
    3. Ensures subsequent launch starts cleanly with original user data.

    Returns:
        dict: receipt of rollback, or None if nothing to roll back.
    """
    data_path = Path(os.path.abspath(data_dir))
    pending_path = data_path / PENDING_FILE
    rollback_path = data_path / ROLLBACK_FILE
    launch_settings_path = data_path / LAUNCH_SETTINGS_FILE

    if not pending_path.is_file() and not rollback_path.is_file():
        return None

    pending_data = {}
    if pending_path.is_file():
        try:
            pending_data = json.loads(pending_path.read_text(encoding='utf-8-sig'))
        except Exception:
            pass

    if not isinstance(pending_data, dict):
        pending_data = {}
    if pending_data.get('status')=='committed':
        raise RestoreSwitchError('Restore already committed; rollback refused')
    previous_existed = pending_data.get('previous_settings_existed')

    if rollback_path.is_file():
        plain_path(rollback_path)
        rollback_text = rollback_path.read_text(encoding='utf-8-sig')
        try:
            rollback_settings = json.loads(rollback_text)
        except (ValueError, UnicodeError) as error:
            raise RestoreSwitchError('Invalid rollback settings; recovery evidence preserved') from error
        if not isinstance(rollback_settings, dict):
            raise RestoreSwitchError('Invalid rollback settings; recovery evidence preserved')
        tmp = data_path / f".{LAUNCH_SETTINGS_FILE}.tmp.{secrets.token_hex(8)}"
        tmp.write_text(rollback_text, encoding='utf-8')
        tmp.replace(launch_settings_path)
        rollback_path.unlink(missing_ok=True)
    elif previous_existed is False:
        launch_settings_path.unlink(missing_ok=True)
    elif 'previous_settings' in pending_data and isinstance(pending_data['previous_settings'], dict):
        tmp = data_path / f".{LAUNCH_SETTINGS_FILE}.tmp.{secrets.token_hex(8)}"
        tmp.write_text(json.dumps(pending_data['previous_settings'], indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        tmp.replace(launch_settings_path)

    else:
        raise RestoreSwitchError('No valid previous settings; recovery evidence preserved')

    receipt = {
        'restore_id': pending_data.get('restore_id'),
        'target_restore_dir': pending_data.get('target_restore_dir'),
        'switched_at': pending_data.get('created_at'),
        'rolled_back_at': datetime.now(timezone.utc).isoformat(),
        'status': 'rolled_back',
        'error': str(error) if error else None,
    }
    _record_history(data_path, receipt)

    pending_path.unlink(missing_ok=True)

    return receipt


@_serialized
def check_pending_restore(data_dir):
    """Check if a previous restore attempt was left pending and handle auto-rollback if needed.

    If restore-pending.json is present:
    - If already attempted during a previous launch (unhandled exit/crash before ready),
      automatically rolls back to original user data and returns True.
    - If first launch attempt for this restore, marks attempted=True and returns False.
    - If sentinel is corrupted or invalid, rolls back and returns True.

    Returns:
        bool: True if a rollback was executed, False otherwise.
    """
    data_path = Path(os.path.abspath(data_dir))
    pending_path = data_path / PENDING_FILE
    rollback_path = data_path / ROLLBACK_FILE

    if not pending_path.is_file() and not rollback_path.is_file():
        return False

    if pending_path.is_file():
        try:
            pending_data = json.loads(pending_path.read_text(encoding='utf-8-sig'))
        except Exception:
            rollback_restore_switch(data_path, error="Corrupted restore-pending sentinel")
            return True

        if not isinstance(pending_data, dict):
            rollback_restore_switch(data_path, error="Invalid restore-pending sentinel format")
            return True

        if pending_data.get('status')=='committed':
            commit_restore_switch(data_path)
            return False

        if pending_data.get('attempted', True):
            rollback_restore_switch(data_path, error="Previous restore attempt did not reach ready state")
            return True
        else:
            pending_data['attempted'] = True
            pending_data['attempted_at'] = datetime.now(timezone.utc).isoformat()
            pending_data['attempted_pid'] = os.getpid()
            tmp_pending = data_path / f".{PENDING_FILE}.tmp.{secrets.token_hex(8)}"
            tmp_pending.write_text(json.dumps(pending_data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
            tmp_pending.replace(pending_path)
            return False

    elif rollback_path.is_file():
        rollback_restore_switch(data_path, error="Orphaned rollback settings found")
        return True

    return False
