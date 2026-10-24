"""Build a draft catalog from one explicitly selected model folder.

No model/download/runtime execution, source changes, or registry activation.
Publisher, hosting and license/NOTICE rights require separate review.
"""
import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from ai_acquisition import Catalog
from ai_model_pack import inspect_model, model_prefix, model_validator
from ai_profiles import ModelProfile
from ai_runtime import digest, files, object_pairs
from tagger_profile import WDProfile
from storage_lease import plain_path
from build_ai_runtime_catalog import write_new


def role(name):
    leaf = Path(name).name.lower()
    if leaf.startswith(('license', 'notice', 'copying')):
        return 'license'
    if leaf == 'selected_tags.csv':
        return 'labels'
    if leaf in ('tokenizer.json', 'tokenizer.model', 'vocab.json', 'vocab.txt', 'merges.txt', 'special_tokens_map.json', 'tokenizer_config.json'):
        return 'tokenizer'
    if leaf.endswith(('.safetensors', '.onnx', '.bin')):
        return 'weights'
    return 'configuration'


def _identity(path):
    info = plain_path(path).stat()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink


def build_catalog(root, profile, *, key, base_url, license, license_url, allowed_hosts, cancelled=lambda: False):
    root = plain_path(root, directory=True)
    location = urlsplit(base_url)
    if (any(c.isspace() for c in base_url) or location.scheme != 'https' or not location.hostname
            or location.query or location.fragment or location.username or location.password):
        raise ValueError('Explicit HTTPS artifact base required')
    inspect_model(root, profile, cancelled=cancelled)
    prefix = model_prefix(profile)
    revision = profile.revision if isinstance(profile, ModelProfile) else profile.data()['revision']
    document = {'format': 'aredoko-acquisition-v1', 'id': key, 'revision': revision, 'kind': 'model',
                'license': license, 'license_url': license_url, 'allowed_hosts': list(allowed_hosts), 'entries': []}
    identities = {}
    total_bytes = 0
    for path in files(root, cancelled):
        if len(identities) >= 100000:
            raise ValueError('Model file inventory exceeds limit')
        name = path.relative_to(root).as_posix()
        before = _identity(path)
        total_bytes += before[2]
        if total_bytes > 64 * 1024**3:
            raise ValueError('Model pack exceeds limit')
        checksum = digest(path, cancelled=cancelled)
        identities[name] = before
        document['entries'].append({'path': prefix + '/' + name, 'url': base_url.rstrip('/') + '/' + quote(name, safe='/'),
                                    'bytes': before[2], 'sha256': checksum, 'role': role(name)})
    raw = json.dumps(document, ensure_ascii=False, indent=2).encode('utf-8')
    catalog = Catalog.parse(raw)
    model_validator(profile, catalog)
    if {p.relative_to(root).as_posix(): _identity(p) for p in files(root, cancelled)} != identities:
        raise ValueError('Model source changed during catalog preparation')
    if cancelled():
        raise InterruptedError('Model catalog preparation cancelled')
    return raw, catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-directory', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--profile-kind', choices=('embedding', 'wd'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    for name in ('id', 'base-url', 'license', 'license-url'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--allow-host', action='append', required=True)
    args = parser.parse_args()
    path = plain_path(args.profile)
    if path.stat().st_size > 8192:
        raise ValueError('Profile exceeds limit')
    value = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=object_pairs)
    profile = ModelProfile.from_dict(value) if args.profile_kind == 'embedding' else WDProfile.from_dict(value)
    raw, catalog = build_catalog(args.model_directory, profile, key=args.id, base_url=args.base_url,
        license=args.license, license_url=args.license_url, allowed_hosts=args.allow_host)
    write_new(raw, args.output, args.model_directory)
    print(json.dumps({'catalog_id': catalog.fingerprint, 'kind': catalog.kind, 'files': len(catalog.entries),
        'bytes': sum(entry.size for entry in catalog.entries), 'registered': False, 'downloaded': False, 'inference_verified': False}))

if __name__ == '__main__':
    main()
