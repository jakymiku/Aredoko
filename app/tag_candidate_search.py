"""Explicit latest-batch pending-label search. Never modifies confirmed tags."""
import json
from shelves import shelf_clause
from library_index import TYPES
from search_terms import normalize, split_terms
from tag_suggestions import SuggestionConflict
from ai_search import AIBusy


def validate_candidate_search(query='', kind='', view='all', page=0, root_ids=None, shelf=None, model=None, shelf_ids=None):
    if not isinstance(query,str) or len(query)>300 or kind not in ('',*TYPES) or view not in ('all','favorites','unreviewed','shelf'):
        raise ValueError('Invalid candidate search')
    if type(page) is not int or not 0<=page<=1000000:raise ValueError('Invalid page')
    if shelf is not None and (not isinstance(shelf,str) or len(shelf)>80):raise ValueError('Invalid shelf')
    if model is not None and (not isinstance(model,str) or not 1<=len(model)<=256):raise ValueError('Invalid model')
    if root_ids is not None:
        if (type(root_ids) is not list or not 1<=len(root_ids)<=256 or
            any(type(i) is not int or not 1<=i<=9223372036854775807 for i in root_ids) or len(set(root_ids))!=len(root_ids)):
            raise ValueError('Invalid roots')
        root_ids=sorted(root_ids)
    shelf_clause(shelf,shelf_ids)
    terms=split_terms(query)
    return terms


def search_candidates(service, query='', kind='', view='all', page=0, root_ids=None, shelf=None, model=None, shelf_ids=None):
    terms=validate_candidate_search(query,kind,view,page,root_ids,shelf,model,shelf_ids)
    catalog=service.catalog
    # Snapshot the DB scope and bounded page source checks against root edits.
    # No model is called; only these <=60 sources are checked for freshness.
    with catalog._guard:
        with catalog.connect() as db:
            db.create_function('candidate_normalize',1,normalize,deterministic=True)
            where=["l.status<>'excluded'",'l.root_id IN (SELECT id FROM library_roots WHERE enabled=1)',
                   'b.id=(SELECT max(latest.id) FROM tag_proposal_batches latest WHERE latest.item_id=i.id)',
                   "EXISTS(SELECT 1 FROM tag_proposals p WHERE p.batch_id=b.id AND p.state='pending')"]
            values=[]
            if root_ids is not None:
                placeholders=','.join('?' for _ in root_ids)
                active=db.execute(f'SELECT count(*) FROM library_roots WHERE enabled=1 AND id IN ({placeholders})',root_ids).fetchone()[0]
                if active!=len(root_ids):raise ValueError('Unknown registered root')
                where.append(f'l.root_id IN ({placeholders})');values.extend(root_ids)
            if kind:where.append('i.kind=?');values.append(kind)
            where.extend({'all':[],'favorites':['i.favorite=1'],'unreviewed':['i.reviewed=0'],'shelf':["i.shelf<>''"]}[view])
            shelf_where,shelf_values=shelf_clause(shelf,shelf_ids)
            where.extend(shelf_where);values.extend(shelf_values)
            if model is not None:where.append("json_extract(b.producer_json,'$.model')=?");values.append(model)
            for term in terms:
                where.append("EXISTS(SELECT 1 FROM tag_proposals p WHERE p.batch_id=b.id AND p.state='pending' AND instr(candidate_normalize(p.tag),?)>0)")
                values.append(term)
            clause=catalog.JOIN+' JOIN tag_proposal_batches b ON b.item_id=i.id WHERE '+' AND '.join(where)
            total=db.execute('SELECT count(*)'+clause,values).fetchone()[0]
            rows=db.execute('SELECT '+catalog.FIELDS+',b.id AS batch_id,b.source_revision,b.producer_json,b.evidence_json'+clause+' ORDER BY i.id LIMIT 60 OFFSET ?',values+[page*60]).fetchall()
            items=[]
            for raw in rows:
                row=dict(raw)
                batch_id=row.pop('batch_id');revision=row.pop('source_revision')
                producer=json.loads(row.pop('producer_json'));evidence=json.loads(row.pop('evidence_json'))
                tags=[p[0] for p in db.execute("SELECT tag FROM tag_proposals WHERE batch_id=? AND state='pending' ORDER BY id",(batch_id,))]
                tags=[tag for tag in tags if not terms or any(term in normalize(tag) for term in terms)]
                item=catalog.item(row)
                try:state='current' if service._source(item['id'])['revision']==revision else 'stale'
                except SuggestionConflict:state='stale'
                except AIBusy:state='unverified'
                except (KeyError,OSError):state='unavailable'
                item['proposal_match']={'batch_id':batch_id,'source_revision':revision,'source_state':state,
                                        'state':'pending','tags':tags,'producer':producer,'evidence':evidence}
                items.append(item)
    return {'total':total,'page':page,'limit':60,'search_mode':'pending-proposals','items':items}
