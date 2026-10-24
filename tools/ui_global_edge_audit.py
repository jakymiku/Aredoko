"""50k synthetic metadata, 80 generated PNGs. Not a real 50k media scan."""
import json,os,re
from native_ui_tools import process_memory
from create_preview_fixture import png


def create_metadata(cat,media,count=50000):
    root=cat.add_root(str(media));data=png(120,160,(55,110,175));stamps={}
    for index in [*range(40),*range(count-40,count)]:
        path=media/f'generated-{index:05}.png';path.write_bytes(data);stamps[index]=path.stat().st_mtime_ns
    with cat.connect() as db:
        db.executemany('INSERT INTO library_locations(id,root_id,relative_path,kind,size_bytes,mtime_ns,status,discovered_at,last_seen_at) VALUES(?,?,?,?,?,?,?,?,?)',
            ((index+1,root,f'generated-{index:05}.png','image',len(data),stamps.get(index,0),'present','2026-10-25','2026-10-25') for index in range(count)))
        db.executemany('INSERT INTO items(id,title,kind,tags,shelf,favorite) VALUES(?,?,?,?,?,?)',
            ((index+1,f'generated-{index:05}.png','image','[]','',0) for index in range(count)))
        db.executemany('INSERT INTO item_locations(item_id,location_id) VALUES(?,?)',((index+1,index+1) for index in range(count)))


def audit(ui,tree,shot,report,check,pid,cat):
    report['metadata_fixture']={'records':50000,'actual_generated_pngs':80,'filesystem_scan':False,'quality_or_scan_benchmark':False}
    def extent():
        text=tree().get('TxtPageNumber',{}).get('name','').replace(',','')
        match=re.fullmatch(r'(\d+)–(\d+) / (\d+)',text)
        return tuple(map(int,match.groups())) if match else None
    def sample(label):
        visible=tree();cards=sum(re.fullmatch(r'Item\d+',name) is not None for name in visible)
        report.setdefault('edge_memory',[]).append({'label':label,'native_keyed_cards':cards,'frontend':process_memory(pid),'test_host_backend':process_memory(os.getpid())})
        check(label+' native card exposure bounded',0<cards<100)
    def jump(last,expected,key):
        ui('focus','BtnLayout');ui('send-keys','ctrl+end' if last else 'ctrl+home','--via','send-input')
        ui('wait-for','TxtPageNumber','--value',f'{expected[0]:,}–{expected[1]:,} / {expected[2]:,}','-t','15000')
        check('exact scoped range '+str(expected),extent()==expected)
        ui('wait-for','Item'+str(key),'-p','IsOffscreen','--value','False','-t','10000')
    ui('invoke','Item1','--action','select');ui('wait-for','TxtTags','-p','IsEnabled','--value','True','-t','10000')
    ui('set-value','TxtTags','global-edge-unsaved');sample('first')
    jump(True,(49881,50000,50000),50000)
    ui('wait-for','TxtTags','--value','global-edge-unsaved','-t','5000');check('jump does not autosave first-item draft',cat.get(1)['tags']==[])
    shot('global-last');sample('last')
    ui('focus','TxtTags');ui('send-keys','ctrl+home','--via','send-input')
    check('Ctrl Home in editor does not move result range',extent()==(49881,50000,50000))
    jump(False,(1,120,50000),1);ui('wait-for','TxtTags','--value','global-edge-unsaved','-t','5000')
    shot('global-first');sample('returned-first');ui('set-value','TxtTags','')
    ui('set-value','TxtQuery','generated-0000');ui('wait-for','TxtCount','--value','10 件','-t','10000')
    jump(True,(1,10,10),10);shot('filtered-last')
    check('filtered jump never escapes to full-library last item',tree().get('Item50000',{}).get('isOffscreen',True))
    check('no generated item tags were saved',cat.search(query='global-edge-unsaved')['total']==0)
