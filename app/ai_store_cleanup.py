"""Remove derived vectors from catalog-owned profile DBs before metadata purge.

Each sidecar is its own transaction. On failure the main catalog transaction is
not committed; confirmed metadata stays intact and the inactive root can retry.
Already removed derived vectors may need rebuilding after a failed multi-file
operation. No source media or arbitrary caller-supplied paths are opened here.
"""
from contextlib import closing
import hashlib
from pathlib import Path
import re
import sqlite3
import stat

from ai_profiles import LEGACY_PROFILE

PURGE_AI_ERROR = 'AI index cleanup failed; library records were kept'
VECTOR_TABLES = ('ai_vectors', 'ai_video_frames', 'ai_source_contracts', 'ai_proposal_vectors', 'ai_page_vectors')


def _ordinary(path):
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError(PURGE_AI_ERROR)


def purge_profile_stores(catalog_path, root_id):
    """Only exact ModelProfile.store_path names plus a verified profile key.

    The caller holds the catalog write guard and its transaction. The read-only
    attachment sees the still-present membership of this already inactive root.
    SQL subqueries avoid materializing IDs or hitting SQLite's variable limit.
    """
    catalog = Path(catalog_path).absolute()
    pattern = re.compile(re.escape(catalog.name) + r'\.ai(?:\.[0-9a-f]{24})?\.sqlite')
    try:
        stores = sorted(p for p in catalog.parent.iterdir() if pattern.fullmatch(p.name))
        for path in stores:
            _ordinary(path)
            # mode=rw never creates a missing database after enumeration.
            with closing(sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=1)) as db:
                with db:
                    db.execute('PRAGMA trusted_schema=OFF')
                    profiles = db.execute('SELECT value FROM ai_profile LIMIT 2').fetchall()
                    if len(profiles) != 1 or type(profiles[0][0]) is not str:
                        raise ValueError(PURGE_AI_ERROR)
                    key = profiles[0][0]
                    if key == LEGACY_PROFILE:
                        expected = catalog.name + '.ai.sqlite'
                    elif re.fullmatch(r'embedding-profile:[0-9a-f]{64}', key):
                        expected = catalog.name + '.ai.' + hashlib.sha256(key.encode()).hexdigest()[:24] + '.sqlite'
                    else:
                        raise ValueError(PURGE_AI_ERROR)
                    if path.name != expected:
                        raise ValueError(PURGE_AI_ERROR)
                    tables = {r[0] for r in db.execute("SELECT name FROM main.sqlite_master WHERE type='table'")}
                    if 'ai_vectors' not in tables:
                        raise ValueError(PURGE_AI_ERROR)
                    db.execute('ATTACH DATABASE ? AS library', (catalog.as_uri() + '?mode=ro',))
                    membership = ('SELECT m.item_id FROM library.item_locations m '
                                  'JOIN library.library_locations l ON l.id=m.location_id '
                                  'JOIN library.library_roots r ON r.id=l.root_id '
                                  'WHERE r.id=? AND r.enabled=0')
                    for table in VECTOR_TABLES:
                        if table in tables:
                            db.execute(f'DELETE FROM main.{table} WHERE item_id IN ({membership})', (root_id,))
    except (OSError, sqlite3.Error, ValueError) as error:
        raise ValueError(PURGE_AI_ERROR) from error
