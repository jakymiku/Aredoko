"""Explicit setup only; runtime uses local_files_only and never downloads."""
from pathlib import Path
from huggingface_hub import snapshot_download
MODEL_REVISION = '914f7f89142e33e77833254d9c9b90c3cef7303b'
target = Path(__file__).resolve().parents[1] / 'models' / 'embeddinggemma-2'
snapshot_download('google/embeddinggemma-2', revision=MODEL_REVISION, local_dir=target,
                  ignore_patterns=['README.md', '.gitattributes'])
(target / 'aredoko-revision.txt').write_text(MODEL_REVISION, encoding='utf-8')
print('Model stored locally. No library source uploaded.')

