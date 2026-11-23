"""Prepare a NEW portable runtime from explicit, already installed Windows assets.

No download, installer, source modification or model copying. This is preparation,
not clean-machine or AI inference acceptance. Run the staged probe afterwards.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import zipfile

from package_release import validate_output
from release_runtime import configure_embedded_python, python_layout
from storage_lease import plain_path, storage_parent


def selected_files(base, *, exclude_site=False):
    """Enumerate only explicit runtime inputs, refusing links before descending."""
    plain_path(base, directory=True)
    for child in sorted(base.iterdir()):
        if child.name == '__pycache__' or child.suffix.lower() == '.pdb':
            continue
        if exclude_site and child.name.casefold() == 'site-packages':
            continue
        plain_path(child, directory=child.is_dir())
        if child.is_dir():
            yield from selected_files(child)
        else:
            yield child


def prepare(base, site_packages, output, *, include_ai=False, check=False):
    base, site_packages, output = (Path(os.path.abspath(p)) for p in (base, site_packages, output))
    validate_output(output)
    for source in (base, site_packages):
        plain_path(source, directory=True)
        if output.is_relative_to(source) or source.is_relative_to(output):
            raise ValueError('Runtime source and output directories must not overlap')
    if (base / 'pyvenv.cfg').exists():
        raise ValueError('Supply the base CPython installation, not its venv')
    for name in ('python.exe', 'pythonw.exe', 'python3.dll', 'LICENSE.txt'):
        plain_path(base / name)
    stems = [p.stem for p in base.glob('python3*.dll') if re.fullmatch(r'python3(?:1[1-9]|[2-9][0-9])', p.stem)]
    if len(stems) != 1:
        raise ValueError('One CPython 3.11+ runtime DLL is required')
    stem = stems[0]
    native = [p for p in base.iterdir() if p.is_file() and p.suffix.lower() in ('.exe', '.dll') and
              (p.name.startswith('python') or p.name.startswith('vcruntime'))]
    native += [base / 'LICENSE.txt']
    for path in native:
        plain_path(path)
    stdlib = list(selected_files(base / 'Lib', exclude_site=True))
    if not (base / 'Lib/encodings/__init__.py') in stdlib:
        raise ValueError('CPython standard library is incomplete')
    dlls = list(selected_files(base / 'DLLs'))
    pillow = site_packages / 'PIL'
    plain_path(pillow / '__init__.py')
    metadata = [p for p in site_packages.iterdir() if p.name.casefold().startswith('pillow-') and p.name.endswith('.dist-info')]
    if len(metadata) != 1:
        raise ValueError('One Pillow distribution metadata directory is required')
    wheel = plain_path(metadata[0] / 'WHEEL').read_text(encoding='utf-8')
    if not re.search(r'^Tag: cp' + stem.removeprefix('python') + r'-[^\r\n]*-win_amd64\s*$', wheel, re.MULTILINE):
        raise ValueError('Pillow ABI/architecture does not match the CPython runtime')
    # AI mode copies all explicitly supplied site-packages, including dependency
    # metadata/licenses. It never collects models, Scripts, pyvenv.cfg or caches.
    package_roots = [site_packages] if include_ai else [pillow, metadata[0]]
    for name in ('pillow.libs', 'Pillow.libs'):
        sibling = site_packages / name
        if not include_ai and sibling.exists() and sibling not in package_roots:
            package_roots.append(sibling)
    packages = sorted({p for source in package_roots for p in selected_files(source)})
    if any(p.suffix == '.egg-link' or p.name.startswith('__editable__') for p in packages):
        raise ValueError('Editable packages must be replaced with prepared portable packages')
    if include_ai:
        for name in ('torch', 'transformers', 'sentence_transformers', 'numpy', 'onnxruntime'):
            plain_path(site_packages / name / '__init__.py')
    info = {'pass': True, 'prepared': not check, 'python_stem': stem, 'ai_runtime_included': include_ai,
            'input_files': len(native) + len(stdlib) + len(dlls) + len(packages),
            'input_bytes': sum(p.stat().st_size for p in native + stdlib + dlls + packages),
            'runtime_imports_verified': False, 'clean_machine_verified': False}
    if check:
        return info
    storage_parent(output)
    output.mkdir()
    plain_path(output, directory=True)
    for path in native:
        shutil.copy2(path, output / path.name)
    with zipfile.ZipFile(output / (stem + '.zip'), 'x', zipfile.ZIP_DEFLATED) as archive:
        for path in stdlib:
            archive.write(path, path.relative_to(base / 'Lib').as_posix())
    for path in dlls:
        target = output / 'DLLs' / path.relative_to(base / 'DLLs')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    for path in packages:
        target = output / 'Lib/site-packages' / path.relative_to(site_packages)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    configure_embedded_python(output, stem)
    python_layout(output, include_ai)
    (output / 'runtime-preparation.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-python', type=Path, required=True, help='Explicit existing CPython installation')
    parser.add_argument('--site-packages', type=Path, required=True, help='Explicit already authorized dependency directory')
    parser.add_argument('--output-dir', type=Path, required=True, help='New runtime directory only')
    parser.add_argument('--include-ai-runtime', action='store_true')
    parser.add_argument('--check', action='store_true', help='Inspect inputs without creating/writing output or executing them')
    args = parser.parse_args()
    print(json.dumps(prepare(args.base_python, args.site_packages, args.output_dir,
                             include_ai=args.include_ai_runtime, check=args.check)))


if __name__ == '__main__':
    main()
