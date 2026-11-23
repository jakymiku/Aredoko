"""Bounded OCR scoring, independent of an OCR runtime or embedding model."""
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from search_terms import normalize_document, split_terms
from search_quality import metrics

MAX_PAGES = 32
MAX_TEXT = 2048
MAX_JSON = 512 * 1024
PRODUCER_KEYS = {'adapter', 'version', 'model', 'model_revision', 'preprocessing'}


def read_json(path):
    with Path(path).open('rb') as stream:
        data = stream.read(MAX_JSON + 1)
    if len(data) > MAX_JSON: raise ValueError('Evaluation JSON exceeds limit')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=unique)


def digest(fixture):
    return hashlib.sha256(json.dumps(fixture, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def text(value):
    if (type(value) is not str or len(value) > MAX_TEXT or
            any((ord(c) < 32 and c not in '\n\r\t') or 0xd800 <= ord(c) <= 0xdfff for c in value)):
        raise ValueError('Invalid or oversized evaluation text')
    return value


def rank_pages(pages, predictions, query):
    terms = split_terms(query)
    if not terms: raise ValueError('Empty evaluation query')
    # Same-page AND, then distinct item IDs in the fixture's stable ID order.
    return sorted({p['item'] for p in pages if p['id'] in predictions and
                   all(t in normalize_document(predictions[p['id']]) for t in terms)})


def validate_fixture(fixture):
    if type(fixture) is not dict or set(fixture) != {'version', 'id', 'language', 'pages', 'queries'} or type(fixture['version']) is not int or fixture['version'] != 1:
        raise ValueError('Unsupported OCR fixture')
    if fixture['language'] != 'ja' or type(fixture['id']) is not str or not re.fullmatch(r'[a-z0-9-]{1,64}', fixture['id']): raise ValueError('Invalid fixture identity')
    pages = fixture['pages']
    if type(pages) is not list or not 1 <= len(pages) <= MAX_PAGES: raise ValueError('Invalid fixture pages')
    seen = set()
    for page in pages:
        if type(page) is not dict or set(page) != {'id','item','layout','font_size','contrast','text'}: raise ValueError('Invalid fixture page')
        if not all(type(page[k]) is str and re.fullmatch(r'[a-z0-9-]{1,64}', page[k]) for k in ('id','item')) or page['id'] in seen:
            raise ValueError('Duplicate or invalid page identity')
        seen.add(page['id']); text(page['text'])
        if page['layout'] not in ('horizontal','vertical') or type(page['font_size']) is not int or not 16 <= page['font_size'] <= 64 or type(page['contrast']) is not int or not 0 <= page['contrast'] <= 192:
            raise ValueError('Invalid page rendering')
    queries = fixture['queries']
    if type(queries) is not list or not 1 <= len(queries) <= 64: raise ValueError('Invalid fixture queries')
    seen = set()
    for q in queries:
        if type(q) is not dict or set(q) != {'id','query','expected_items'} or type(q['id']) is not str or q['id'] in seen:
            raise ValueError('Invalid or duplicate query')
        seen.add(q['id'])
        if type(q['query']) is not str or not 1 <= len(q['query']) <= 300 or type(q['expected_items']) is not list:
            raise ValueError('Invalid query expectation')
        expected = rank_pages(pages, {p['id']:p['text'] for p in pages}, q['query'])
        if q['expected_items'] != expected: raise ValueError('Ground-truth query expectation mismatch')
    return fixture


def distance(reference, hypothesis):
    """Levenshtein over Unicode codepoints, bounded memory (two short rows)."""
    reference, hypothesis = text(reference), text(hypothesis)
    if reference == hypothesis: return 0
    if len(reference) < len(hypothesis): reference, hypothesis = hypothesis, reference
    previous = list(range(len(hypothesis) + 1))
    for i, a in enumerate(reference, 1):
        current = [i]
        for j, b in enumerate(hypothesis, 1):
            current.append(min(previous[j]+1, current[j-1]+1, previous[j-1]+(a != b)))
        previous = current
    return previous[-1]


def canonical(value):
    return ''.join(normalize_document(value).split())


def control(fixture, kind):
    validate_fixture(fixture)
    if kind not in ('perfect','empty'): raise ValueError('Unknown scoring control')
    return {'version':1,'fixture_sha256':digest(fixture),
            'producer':{'adapter':'scoring-control','version':'1','model':kind,'model_revision':'1','preprocessing':'reference-copy' if kind=='perfect' else 'empty-output'},
            'pages':[{'page_id':p['id'],'text':p['text'] if kind=='perfect' else ''} for p in fixture['pages']]}


def evaluate(fixture, output):
    validate_fixture(fixture)
    if (type(output) is not dict or set(output) != {'version','fixture_sha256','producer','pages'} or
            type(output['version']) is not int or output['version'] != 1 or output['fixture_sha256'] != digest(fixture)):
        raise ValueError('Predictions do not match frozen fixture')
    producer = output['producer']
    if type(producer) is not dict or set(producer) != PRODUCER_KEYS or any(type(v) is not str or not 1 <= len(v) <= 256 or any(ord(c)<32 for c in v) for v in producer.values()):
        raise ValueError('Invalid OCR producer')
    pages = output['pages']
    if type(pages) is not list or len(pages) > MAX_PAGES: raise ValueError('Invalid predictions')
    known = {p['id'] for p in fixture['pages']}; predictions = {}
    for row in pages:
        if type(row) is not dict or set(row) != {'page_id','text'} or type(row['page_id']) is not str or row['page_id'] not in known or row['page_id'] in predictions:
            raise ValueError('Unknown or duplicate prediction page')
        predictions[row['page_id']] = text(row['text'])
    results = []; raw_errors = norm_errors = raw_length = norm_length = blanks = blank_fp = 0
    for p in fixture['pages']:
        ref = unicodedata.normalize('NFC', p['text'].replace('\r\n','\n'))
        hyp = unicodedata.normalize('NFC', predictions.get(p['id'],'').replace('\r\n','\n'))
        norm_ref, norm_hyp = canonical(ref), canonical(hyp)
        raw, norm = distance(ref,hyp), distance(norm_ref,norm_hyp)
        raw_errors += raw; norm_errors += norm; raw_length += len(ref); norm_length += len(norm_ref)
        if not norm_ref:
            blanks += 1; blank_fp += bool(norm_hyp)
        results.append({'page_id':p['id'],'missing':p['id'] not in predictions,'reference_chars':len(ref),
                        'errors':raw,'cer':raw/len(ref) if ref else None,
                        'normalized_errors':norm,'normalized_cer':norm/len(norm_ref) if norm_ref else None})
    queries = []; positives = []; negatives = []
    for q in fixture['queries']:
        ranked = rank_pages(fixture['pages'],predictions,q['query'])
        score = metrics(ranked,{item:1 for item in q['expected_items']})
        queries.append({'id':q['id'],'ranked_items':ranked,'expected_items':q['expected_items'],'metrics':score})
        if score is None: negatives.append(bool(ranked))
        else: positives.append(score)
    return {'version':1,'fixture_id':fixture['id'],'fixture_sha256':digest(fixture),'producer':producer,
            'measurement_kind':'scoring-control; no OCR inference' if producer['adapter']=='scoring-control' else 'supplied OCR outputs; runtime provenance not independently verified',
            'scope':'synthetic Japanese pages; offline literal same-page AND, item aggregation; not real-library or AI ranking quality',
            'normalization':'raw NFC + LF; normalized NFKC/casefold/kana-fold with whitespace removed; retrieval retains whitespace',
            'summary':{'pages':len(results),'missing_pages':sum(p['missing'] for p in results),
                       'errors':raw_errors,'reference_chars':raw_length,'cer':raw_errors/raw_length if raw_length else None,
                       'normalized_cer':norm_errors/norm_length if norm_length else None,'blank_pages':blanks,'blank_false_positives':blank_fp,
                       'positive_queries':len(positives),'negative_queries':len(negatives),
                       'no_answer_false_positive_rate':sum(negatives)/len(negatives) if negatives else None,
                       'retrieval_means':{key:sum(s[key] for s in positives)/len(positives) for key in positives[0]} if positives else None},
            'pages':results,'queries':queries}
