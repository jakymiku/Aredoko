"""One native acceptance using existing generated PNGs; never scans private media."""
import json
import re
import sqlite3
import threading
import time
from pathlib import Path

from create_library_scale_fixture import digest
from native_ui_tools import process_memory

REPO=Path(__file__).resolve().parents[1]


def copy_fixture(source,destination):
    source=source.resolve()
    if not source.is_relative_to(REPO/'data/ai-ui') or (source/'fixture.json').stat().st_size>16384:
        raise ValueError('Explicit bounded generated fixture required')
    fixture=json.loads((source/'fixture.json').read_text(encoding='utf-8'))
    if not (fixture.get('generated_only') is True and fixture.get('metadata_count')==50000
            and fixture.get('actual_png_files')==50000 and fixture.get('all_items_backed_by_generated_files') is True):
        raise ValueError('Expected 50k existing generated real-file fixture')
    folder=(source/'generated').resolve()
    if digest(folder)!=fixture['source_digest']:raise ValueError('Generated source digest changed')
    # Read-only source connection; all edits, auxiliary DBs and owner locks belong
    # to the new native run. Roots still reference only the generated PNGs.
    with sqlite3.connect((source/'catalog.sqlite').as_uri()+'?mode=ro',uri=True) as original:
        roots=original.execute('SELECT path FROM library_roots').fetchall()
        if not roots or any(not Path(row[0]).resolve().is_relative_to(folder) for row in roots):
            raise ValueError('Fixture has roots outside generated media')
        with sqlite3.connect(destination) as copied:original.backup(copied)
    return fixture,lambda:digest(folder)


def install_cancel_gate(handler):
    release=threading.Event()
    original=handler.results.provider
    def provider(conditions,consume,cancelled):
        def gated(page):
            def next_page(number):
                if number==1 and not release.is_set():
                    deadline=time.monotonic()+50
                    while not release.wait(.05):
                        if cancelled():raise InterruptedError('Bounded native snapshot cancellation')
                        if time.monotonic()>deadline:raise TimeoutError('Native progress gate expired')
                return page(number)
            return consume(next_page)
        return original(conditions,gated,cancelled)
    handler.results.provider=provider
    return release


def cancel_then_prepare(ui,tree,shot,check,report,release):
    ui('wait-for','TxtCount','--value','準備中 120 / 50,000','-t','20000')
    check('building publishes progress without partial rows',not any(re.fullmatch(r'Item\d+',name) for name in tree()))
    shot('snapshot-building')
    ui('invoke','BtnCancelSearch');ui('wait-for','TxtCount','--value','中断','--contains','-t','10000')
    shot('snapshot-cancelled');release.set()
    began=time.monotonic();ui('invoke','BtnSearch')
    ui('wait-for','Item1','-t','60000')
    report['native_retry_to_first_item_seconds']=round(time.monotonic()-began,3)


def audit(ui,tree,shot,report,check,pid,cat,thumbnails,*,input_guard):
    def sample(label):
        cards=sum(re.fullmatch(r'Item\d+',name) is not None for name in tree())
        report.setdefault('edge_memory',[]).append({'label':label,'native_keyed_cards':cards,'frontend':process_memory(pid)})
        check(label+' native card exposure bounded',0<cards<100)
    def jump(last,key,text):
        ui('focus','BtnLayout')
        if not input_guard():raise RuntimeError('Owned test window lost foreground')
        ui('send-keys','ctrl+end' if last else 'ctrl+home','--via','send-input')
        ui('wait-for','TxtPageNumber','--value',text,'-t','15000')
        ui('wait-for','Item'+str(key),'-p','IsOffscreen','--value','False','-t','10000')
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        with thumbnails.lock:cached=len(thumbnails.cache)
        if cached:break
        time.sleep(.1)
    check('visible generated PNG thumbnails available',cached>0)
    sample('first');shot('thumbnails-first')
    ui('invoke','Item1','--action','select');ui('invoke','BtnDetails')
    ui('wait-for','TxtTags','-p','IsEnabled','--value','True','-t','10000')
    old_tags=cat.get(1)['tags'];ui('set-value','TxtTags','real-library-unsaved')
    jump(True,50000,'49,881–50,000 / 50,000');sample('last');shot('real-last')
    ui('wait-for','TxtTags','--value','real-library-unsaved','-t','5000')
    check('last-item jump preserves first-item draft',cat.get(1)['tags']==old_tags)
    jump(False,1,'1–120 / 50,000');sample('returned-first')
    ui('wait-for','TxtTags','--value','real-library-unsaved','-t','5000')
    ui('set-value','TxtTags',', '.join(old_tags));ui('invoke','BtnCloseDetails')
    ui('set-value','TxtQuery','50000');ui('wait-for','TxtCount','--value','1 件','-t','15000')
    ui('wait-for','Item50000','-p','IsOffscreen','--value','False','-t','10000')
    shot('filtered-last');check('filtered result remains scoped',tree()['TxtPageNumber']['name']=='1–1 / 1')
    with thumbnails.lock:
        report['thumbnails']={'jobs_created':thumbnails.order,'cache_entries':len(thumbnails.cache),'cache_bytes':thumbnails.bytes}
    check('thumbnail work is bounded rather than full-library',0<report['thumbnails']['jobs_created']<600)
    check('unsaved tags were not committed',cat.get(1)['tags']==old_tags)
