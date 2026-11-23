"""Fixed generated compatibility smoke; run with the staged Python, not the host.

This loads the explicitly supplied existing model (possibly CUDA). It never
downloads, scans media, measures search quality, or changes model/ranking settings.
"""
import argparse
import io
import json
import math
from pathlib import Path
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='NEW result JSON outside the release')
    args = parser.parse_args()
    python = Path(sys.executable).resolve()
    if python.parent.name.casefold() != 'python' or python.parent.parent.name.casefold() != 'runtime':
        parser.error('Run with the staged runtime/python/python.exe; no host fallback')
    release = python.parents[2]
    if not (release / 'manifest.json').is_file():
        parser.error('A completed staging manifest is required')
    if args.output.exists() or args.output.resolve().is_relative_to(release) or not args.output.parent.is_dir():
        parser.error('Use a new output JSON in an existing directory outside the release')
    from ai_process import EncoderProcess
    from ai_profiles import DEFAULT_PROFILE
    from PIL import Image, ImageDraw
    import ai_process
    if not Path(ai_process.__file__).resolve().is_relative_to(release / 'backend/app'):
        parser.error('Worker code must come from the staged backend')
    model = DEFAULT_PROFILE.model_path(Path.cwd(), models_root=args.models)
    before = {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in model.iterdir() if p.is_file()}
    worker = EncoderProcess(python, model, DEFAULT_PROFILE)
    process = None
    report = {'pass': False, 'quality_measured': False, 'fixed_operations': ['document', 'query', 'image'],
              'runtime': str(python), 'profile': DEFAULT_PROFILE.key}
    started = time.monotonic()
    try:
        image = Image.new('RGB', (384, 384), 'white')
        ImageDraw.Draw(image).ellipse((96, 96, 288, 288), fill='blue')
        png = io.BytesIO()
        image.save(png, format='PNG')
        inputs = {'document': 'アルファ起動確認。青い円の画像。', 'query': '青い円', 'image': png.getvalue()}
        vectors = {}
        for name, value in inputs.items():
            vector = worker.encode(name, value)
            process = worker.process
            if vector is None or len(vector) != 768 or not all(math.isfinite(x) for x in vector):
                raise RuntimeError('Invalid vector dimensions or values')
            norm = math.sqrt(sum(x*x for x in vector))
            if abs(norm - 1) >= 0.0001:
                raise RuntimeError('Vector is not normalized')
            vectors[name] = {'dimensions': len(vector), 'norm': norm}
        report.update(inference_pass=True, device=worker.device, vectors=vectors)
    except Exception as error:
        report['error'] = type(error).__name__
    finally:
        worker.close()
        report['worker_closed'] = process is None or process.poll() is not None
        report['model_size_mtime_unchanged'] = before == {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in model.iterdir() if p.is_file()}
        report['pass'] = bool(report.get('inference_pass') and report['worker_closed'] and report['model_size_mtime_unchanged'])
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)
        with args.output.open('x', encoding='utf-8') as output:
            json.dump(report, output, indent=2, ensure_ascii=False)
        print(json.dumps(report, ensure_ascii=False))
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
