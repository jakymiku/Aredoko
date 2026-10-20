"""Explicit local runtime locations; never search PATH or download assets."""
import os
from pathlib import Path


def worker_python(repo, override=None):
    return Path(os.path.abspath(override)) if override is not None else Path(repo) / '.venv-ai/Scripts/python.exe'


def model_directory(repo, relative, models_root=None):
    base = Path(os.path.abspath(models_root if models_root is not None else Path(repo) / 'models'))
    target = base / relative
    # Inspect lexical ancestors before resolve() can hide links/junctions.
    for part in reversed((target, *target.parents)):
        if part.is_symlink() or (part.exists() and getattr(part.stat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Linked model directory is not allowed')
    if not target.resolve().is_relative_to(base.resolve()):
        raise ValueError('Model directory escapes models')
    return target
