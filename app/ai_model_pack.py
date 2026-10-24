"""Model-layout validation for trusted acquisition; never load model code.

Acquisition verifies every catalog byte first. This module then validates the
profile-specific layout and provenance before that version becomes visible.
"""
import json
from pathlib import PurePosixPath
from ai_profiles import ModelProfile
from tagger_profile import WDProfile
from ai_acquisition import Catalog
from ai_runtime import object_pairs, relative
from storage_lease import plain_path


def model_prefix(profile):
    if isinstance(profile, ModelProfile):
        return relative(profile.directory)
    if isinstance(profile, WDProfile):
        return relative(str(PurePosixPath(profile.data()['model_directory']).relative_to('models')))
    raise ValueError('An application-owned model profile is required')


def _json(path, limit):
    path = plain_path(path)
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Model metadata exceeds limit')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=object_pairs)


def inspect_model(directory, profile, *, entries=None, cancelled=lambda: False):
    """Inspect one explicit model folder, without imports, hashing or inference."""
    model_prefix(profile)
    directory = plain_path(directory, directory=True)
    def check():
        if cancelled():
            raise InterruptedError('Model validation cancelled')
    def require(name, role=None):
        check()
        name = relative(name)
        path = plain_path(directory / name)
        if path.stat().st_size <= 0:
            raise ValueError('Empty model artifact')
        if entries is not None:
            entry = entries.get(name)
            if entry is None or entry.size != path.stat().st_size or role is not None and entry.role != role:
                raise ValueError('Model artifact is missing from its declared role')
        return path
    check()
    if isinstance(profile, WDProfile):
        if _json(require('aredoko-source.json', 'configuration'), 8192) != profile.identity():
            raise ValueError('Tagger provenance mismatch')
        for name, expected in profile.data()['artifacts'].items():
            role = 'weights' if name == 'model.onnx' else 'labels'
            path = require(name, role)
            if path.stat().st_size != expected['size']:
                raise ValueError('Tagger artifact mismatch')
            if entries is not None and entries[name].sha256 != expected['sha256']:
                raise ValueError('Tagger catalog differs from its fixed profile')
    else:
        marker = require('aredoko-revision.txt', 'configuration')
        with marker.open('rb') as stream:
            revision = stream.read(257)
        if len(revision) > 256 or revision.decode('utf-8').strip() != profile.revision:
            raise ValueError('Model revision mismatch')
        if not isinstance(_json(require('config.json', 'configuration'), 1024**2), dict):
            raise ValueError('Invalid model configuration')
        weights = [name for name in ('model.safetensors', 'pytorch_model.bin') if (directory / name).exists()]
        if not weights:
            index = _json(require('model.safetensors.index.json', 'configuration'), 1024**2)
            mapping = index.get('weight_map') if isinstance(index, dict) else None
            if not isinstance(mapping, dict) or not mapping:
                raise ValueError('Invalid model weight index')
            weights = {relative(name) for name in mapping.values()}
        for name in weights:
            require(name, 'weights')
        tokenizers = [name for name in ('tokenizer.json', 'tokenizer.model') if (directory / name).exists()]
        if not tokenizers:
            raise ValueError('Model tokenizer is missing')
        for name in tokenizers:
            require(name, 'tokenizer')
    check()
    return {'state': 'model_layout_verified', 'revision': profile.revision if isinstance(profile, ModelProfile) else profile.data()['revision'],
            'model_loaded': False, 'inference_verified': False}


def model_validator(profile, catalog):
    """Bind the app-owned profile to a catalog; downloaded JSON is never code."""
    prefix = model_prefix(profile) + '/'
    revision = profile.revision if isinstance(profile, ModelProfile) else profile.data()['revision']
    if not isinstance(catalog, Catalog) or catalog.kind != 'model' or catalog.revision != revision:
        raise ValueError('Model catalog/profile revision mismatch')
    if any(not entry.path.startswith(prefix) for entry in catalog.entries):
        raise ValueError('Model catalog escapes its profile directory')
    entries = {entry.path[len(prefix):]: entry for entry in catalog.entries}
    if not any(entry.role == 'license' and entry.size > 0 for entry in entries.values()):
        raise ValueError('The model pack must include license/NOTICE files')
    if isinstance(profile, WDProfile):
        for name, expected in profile.data()['artifacts'].items():
            entry = entries.get(name)
            if entry is None or (entry.size, entry.sha256) != (expected['size'], expected['sha256']):
                raise ValueError('Tagger catalog differs from its fixed profile')
    def validate(root, cancelled):
        inspect_model(plain_path(root, directory=True) / model_prefix(profile), profile,
                      entries=entries, cancelled=cancelled)
    return validate
