"""Fixed evaluator suites: never accept an arbitrary source/manifest path."""
import hashlib,json
from pathlib import Path
SUITES={'baseline-v1':('search-quality-v1.json','94260e45459d539285d7cde257214cddc9c39263b454a15b8e3c3b1e2e15afa8'),
        'holdout-v2':('search-quality-v2.json','021e0984797727c6a79c97fb588165ce49db7c4e12fcdb1f265e02a7793b08fa')}
def load_suite(name):
    file,expected=SUITES[name]
    raw=(Path(__file__).resolve().parents[1]/'tests/fixtures'/file).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('Frozen manifest SHA256 mismatch')
    data=json.loads(raw);items={item['key']:item for item in data['items']}
    if len(items)!=len(data['items']) or len({case['id'] for case in data['cases']})!=len(data['cases']):raise ValueError('Duplicate manifest keys')
    for case in data['cases']:
        if not set(case['relevance'])<=items.keys() or any(type(g) is not int or g not in (1,2) for g in case['relevance'].values()):raise ValueError('Invalid qrels')
        if bool(case['relevance'])!=(case['group']!='no-answer'):raise ValueError('Empty qrels are only no-answer')
    return raw,data
