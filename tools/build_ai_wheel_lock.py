"""Convert an explicit pip JSON report into a draft official-wheel-only lock.

No network, installation or registration. Review the produced lock before
shipping it as a source-owned acquisition definition.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote, unquote, urlsplit, urlunsplit

ROOTS = {'torch': '2.9.1+cu128', 'torchvision': '0.24.1+cu128',
         'sentence-transformers': '6.1.0', 'transformers': '5.19.0', 'pillow': '12.3.0'}
TORCH_HASHES = {'torch': 'ad9183864acdd99fc5143d7ca9d3d2e7ddfc9a9600ff43217825d4e5e9855ccc',
                'torchvision': 'c38b0ece839de439de81ed0e81e915c200975972c0b9419608fa9568aa74ecec'}


def build(report):
    environment = report.get('environment', {})
    if (report.get('version') != '1' or environment.get('sys_platform') != 'win32'
            or environment.get('python_full_version') != '3.13.17'
            or environment.get('platform_machine', '').lower() not in ('amd64', 'x86_64')):
        raise ValueError('Expected a CPython 3.13.17 Windows x64 resolution report')
    entries = []
    names = set()
    for item in report.get('install', []):
        metadata = item.get('metadata', {})
        name = re.sub(r'[-_.]+', '-', metadata.get('name', '')).lower()
        version = metadata.get('version', '')
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name) or not re.fullmatch(r'[a-zA-Z0-9.+!-]+', version) or name in names:
            raise ValueError('Invalid or duplicate distribution')
        names.add(name)
        if item.get('is_yanked') or item.get('is_direct') and name not in TORCH_HASHES:
            raise ValueError('Yanked/direct project dependencies are not accepted')
        download = item.get('download_info', {})
        parsed = urlsplit(download.get('url', ''))
        digest = download.get('archive_info', {}).get('hashes', {}).get('sha256', '')
        if parsed.scheme == 'file' and name in TORCH_HASHES:
            # Resolve against an already verified local heavyweight wheel to
            # avoid another multi-GB network transfer. Preserve its official
            # immutable origin in the lock, never the local/private filename.
            filename = name + '-' + ROOTS[name] + '-cp313-cp313-win_amd64.whl'
            if digest != TORCH_HASHES[name] or unquote(parsed.path.rsplit('/', 1)[-1]) != filename:
                raise ValueError('Local PyTorch wheel is not the pinned official artifact')
            parsed = urlsplit('https://download-r2.pytorch.org/whl/cu128/' + quote(filename))
        allowed = {'download.pytorch.org', 'download-r2.pytorch.org'} if name in ('torch', 'torchvision') else {'files.pythonhosted.org'}
        if (parsed.scheme != 'https' or parsed.hostname not in allowed or parsed.username or parsed.password
                or parsed.query or parsed.port not in (None, 443)):
            raise ValueError('Expected an official wheel origin')
        filename = unquote(parsed.path.rsplit('/', 1)[-1])
        if not re.fullmatch(r'[A-Za-z0-9_.+!-]+\.whl', filename):
            raise ValueError('Source archives and unsafe wheel filenames are not accepted')
        tags = filename[:-4].rsplit('-', 3)
        if len(tags) != 4:
            raise ValueError('Invalid wheel tags')
        python_tags, abi_tags, platforms = (set(value.split('.')) for value in tags[-3:])
        portable = 'py3' in python_tags and abi_tags == {'none'} and platforms == {'any'}
        native = platforms == {'win_amd64'} and (
            'cp313' in python_tags and bool(abi_tags & {'cp313', 'abi3'})
            or abi_tags == {'abi3'} and any(re.fullmatch(r'cp3\d+', tag) and 32 <= int(tag[2:]) <= 313 for tag in python_tags))
        if not (portable or native):
            raise ValueError('Wheel is incompatible with CPython 3.13 Windows x64')
        if not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('Official SHA256 required for every wheel')
        if name in TORCH_HASHES and digest != TORCH_HASHES[name]:
            raise ValueError('Changed official PyTorch artifact')
        if parsed.fragment and parsed.fragment != 'sha256=' + digest:
            raise ValueError('Conflicting wheel hash')
        entries.append({'name': name, 'version': version, 'filename': filename,
                        'url': urlunsplit(parsed._replace(fragment='')), 'sha256': digest})
    selected = {entry['name']: entry['version'] for entry in entries}
    if not 5 <= len(entries) <= 200 or any(selected.get(name) != version for name, version in ROOTS.items()):
        raise ValueError('Missing or changed supported AI roots')
    entries.sort(key=lambda entry: entry['name'])
    value = {'format': 'aredoko-ai-wheel-lock-v1', 'review_status': 'draft',
             'target': 'cp313-win_amd64-cu128', 'python': '3.13.17', 'entries': entries}
    requirements = ''.join(f"{entry['name']}=={entry['version']} --hash=sha256:{entry['sha256']}\n" for entry in entries)
    return value, requirements


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.report.stat().st_size > 32 * 1024**2:
        raise ValueError('Pip report exceeds limit')
    value, requirements = build(json.loads(args.report.read_text(encoding='utf-8')))
    args.output.mkdir()  # A partial draft is not an app-ready registration.
    raw = json.dumps(value, indent=2, ensure_ascii=False).encode('utf-8')
    (args.output / 'lock.json').write_bytes(raw)
    (args.output / 'requirements.txt').write_text(requirements, encoding='utf-8')
    print(json.dumps({'draft': True, 'wheels': len(value['entries']), 'lock_sha256': hashlib.sha256(raw).hexdigest()}))


if __name__ == '__main__':
    main()
