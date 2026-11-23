"""Source-owned acquisition registrations. Never discover user/downloaded catalogs.

Only reviewed immutable catalogs and their exact profile definitions belong in
TRUSTED_CATALOGS. Model metadata never implies that a runtime is installed.
"""
from dataclasses import dataclass
import hashlib
import json
import re
from ai_acquisition import Catalog, validate_runtime
from ai_model_pack import model_validator
from ai_profiles import ModelProfile
from ai_runtime import object_pairs, relative
from storage_lease import plain_path
from tagger_profile import WDProfile

@dataclass(frozen=True)
class Registration:
    catalog_path: str
    catalog_id: str
    profile_path: str | None = None
    profile_sha256: str | None = None
    profile_kind: str | None = None

# Pinned upstream model assets; only explicit user consent starts acquisition.
# Runtime packs are separate and not registered until their publisher is ready.
TRUSTED_CATALOGS: tuple[Registration, ...] = (
    Registration('config/acquisition/embeddinggemma-2.json',
                 '8ee756badd8a85a24d1dbf80103be005b2b9c21b3e91d009a8568704d634406e',
                 'config/ai-profiles/embeddinggemma-2.json',
                 'c451ac93432261aa291924c2b328915bdfc8669ed3018a85ce9cb361102f7b42', 'embedding'),
    Registration('config/acquisition/wd-swinv2-v3.json',
                 'a03b0332560b8e852354b31bf39465d9f068ae7b93099a2be8141ca7ff597b13',
                 'config/tagger-profiles/wd-swinv2-v3.json',
                 '3d63503ccc163ab761a93fd4e363dad35ae6ec8839168607cf72cf04b6eba6c5', 'wd'),
)


def _read(root, name, limit):
    name = relative(name)
    if not name.startswith('config/') or not name.endswith('.json'):
        raise ValueError('Catalog/profile must be application configuration')
    with plain_path(root / name).open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Acquisition configuration exceeds limit')
    return raw


def load_trusted_specs(root, registrations=None):
    """Return catalog/validator pairs, or reject the registry without any I/O jobs."""
    declarations = TRUSTED_CATALOGS if registrations is None else registrations
    if not isinstance(declarations, tuple) or len(declarations) > 256:
        raise ValueError('Invalid application acquisition registry')
    if not declarations:
        return ()
    root = plain_path(root, directory=True)
    specifications = []
    seen = set()
    for entry in declarations:
        if not isinstance(entry, Registration) or not isinstance(entry.catalog_id, str) or re.fullmatch('[0-9a-f]{64}', entry.catalog_id) is None:
            raise ValueError('Pinned application catalog identity required')
        if entry.catalog_id in seen:
            raise ValueError('Duplicate registered acquisition catalog')
        seen.add(entry.catalog_id)
        if not isinstance(entry.catalog_path, str) or not entry.catalog_path.startswith('config/acquisition/'):
            raise ValueError('Catalog must be explicitly registered below config/acquisition')
        catalog = Catalog.parse(_read(root, entry.catalog_path, 32 * 1024**2))
        if catalog.fingerprint != entry.catalog_id:
            raise ValueError('Registered acquisition catalog changed')
        if catalog.kind == 'runtime':
            if any(value is not None for value in (entry.profile_path, entry.profile_sha256, entry.profile_kind)):
                raise ValueError('Runtime registry must use its runtime validator')
            validator = validate_runtime
        else:
            if (entry.profile_kind not in ('embedding', 'wd') or not isinstance(entry.profile_path, str)
                    or not isinstance(entry.profile_sha256, str) or re.fullmatch('[0-9a-f]{64}', entry.profile_sha256) is None):
                raise ValueError('Model registry requires an exact profile binding')
            raw = _read(root, entry.profile_path, 8192)
            if hashlib.sha256(raw).hexdigest() != entry.profile_sha256:
                raise ValueError('Registered model profile changed')
            document = json.loads(raw.decode('utf-8'), object_pairs_hook=object_pairs)
            profile = ModelProfile.from_dict(document) if entry.profile_kind == 'embedding' else WDProfile.from_dict(document)
            validator = model_validator(profile, catalog)
        specifications.append((catalog, validator))
    return tuple(specifications)
