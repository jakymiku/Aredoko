"""Run with the packaged interpreter; import checks only, no models/downloads."""
import argparse
from contextlib import closing
import io
import json
import struct
import sys


def probe(ai=False):
    if sys.version_info < (3, 11) or struct.calcsize('P') != 8:
        raise RuntimeError('Python 3.11+ x64 is required')
    import ctypes
    import sqlite3
    from PIL import Image
    with closing(sqlite3.connect(':memory:')) as db:
        assert db.execute('SELECT 1').fetchone() == (1,)
    buffer = io.BytesIO()
    Image.new('RGB', (2, 2)).save(buffer, format='PNG')
    with Image.open(io.BytesIO(buffer.getvalue())) as image:
        image.load()
    if ai:
        import torch
        import transformers
        import sentence_transformers
        import numpy
        import onnxruntime
    return {'pass': True, 'python': '.'.join(map(str, sys.version_info[:3])),
            'architecture': 'x64', 'backend_imports': True, 'ai_imports': ai,
            'model_inference_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ai', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(probe(args.ai)))
    except Exception as error:
        print(json.dumps({'pass': False, 'error': type(error).__name__, 'detail': str(error)}))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
