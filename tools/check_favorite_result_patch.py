"""One CPU-only large-result favorite edit; reuse generated media, copy its DB.

No normal library, model, GUI, GPU, network or source writes. Snapshot creation
is measured separately; this is not a repeated search benchmark.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'app'),str(REPO/'tools')]
from create_library_scale_fixture import digest
from production import ProductionCatalog
from result_sessions import ResultSessions


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();source=args.fixture.resolve();target=args.output.resolve();allowed=(REPO/'data/ai-ui').resolve()
    if (not source.is_relative_to(allowed) or not target.is_relative_to(allowed) or target.exists()
            or source.is_relative_to(target) or target.is_relative_to(source)):parser.error('Existing generated fixture and fresh independent data/ai-ui output required')
    marker=source/'fixture.json'
    if marker.stat().st_size>16384:parser.error('Fixture metadata exceeds limit')
    fixture=json.loads(marker.read_text(encoding='utf-8'))
    if (fixture.get('generated_only') is not True or fixture.get('all_items_backed_by_generated_files') is not True
            or not 120<=fixture.get('metadata_count',0)<=50000):parser.error('Bounded generated real-file fixture required')
    if digest(source/'generated')!=fixture['source_digest']:parser.error('Generated fixture source digest changed')
    print('verified existing generated fixture',flush=True)
    source_db=source/'catalog.sqlite';original=(source_db.stat().st_mtime_ns,hashlib.sha256(source_db.read_bytes()).hexdigest())
    target.mkdir(parents=True)
    with sqlite3.connect(source_db.as_uri()+'?mode=ro',uri=True) as old,sqlite3.connect(target/'catalog.sqlite') as new:old.backup(new)
    catalog=ProductionCatalog(target/'catalog.sqlite');calls=[]
    def provider(conditions,consume,cancelled):
        calls.append(1)
        return catalog.search(limit=120,result_sink=consume,cancelled=cancelled,**{k:v for k,v in conditions.items() if k!='mode'})
    owner=ResultSessions(catalog,provider,parent=target);sid='a'*32
    report={'pass':False,'source_files':{name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in
        ('app/result_sessions.py','app/production.py','app/selection_edits.py')},'gui':False,'gpu':False,'model':False,'fixture_reused':True,'normal_data_used':False}
    try:
        began=time.perf_counter();reply=owner.create(sid,{'mode':'literal','view':'all'});report['snapshot_seconds']=time.perf_counter()-began
        print('snapshot ready',reply['total'],flush=True)
        first=owner.read(sid,0,1)['items'][0];last=owner.read(sid,reply['total']-1,1)['items'][0]
        previous=catalog.get(first['id']);checked=[];session=owner.sessions[sid];currents=session._currents
        def selected(items,**options):
            checked.extend(row['id'] for row in items);return currents(items,**options)
        session._currents=selected
        try:
            began=time.perf_counter();result=owner.edit(sid,[first['id']],'favorite_add',[],keep_session=True);report['edit_seconds']=time.perf_counter()-began
        finally:session._currents=currents
        current=owner.read(sid,0,1)['items'][0];remaining=owner.read(sid,reply['total']-1,1)['items'][0]
        after=catalog.get(first['id'])
        report.update(total=reply['total'],kept_session=result['kept_session'],selected_source_checks=checked,
            provider_calls=len(calls),first_id_unchanged=current['id']==first['id'],last_id_unchanged=remaining['id']==last['id'],
            favorite_saved=current['favorite'] is True,other_metadata_unchanged={k:v for k,v in previous.items() if k!='favorite'}=={k:v for k,v in after.items() if k!='favorite'},
            workspace_bytes=session.bytes(),original_fixture_db_unchanged=original==(source_db.stat().st_mtime_ns,hashlib.sha256(source_db.read_bytes()).hexdigest()))
        with catalog.connect() as db:report['catalog_integrity']=db.execute('PRAGMA integrity_check').fetchone()[0]
        report['pass']=(reply['total']==fixture['metadata_count'] and result['kept_session'] and checked==[first['id']] and len(calls)==1
            and all(report[key] for key in ('first_id_unchanged','last_id_unchanged','favorite_saved','other_metadata_unchanged','original_fixture_db_unchanged')) and report['catalog_integrity']=='ok')
    finally:
        report['owned_results_closed']=owner.close();catalog.close()
        report['pass']=report['pass'] and report['owned_results_closed']
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));return 0 if report['pass'] else 1


if __name__=='__main__':raise SystemExit(main())
