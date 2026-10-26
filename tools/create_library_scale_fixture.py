"""Isolated display/count fixture: metadata records are NOT filesystem scan evidence."""
import hashlib
import json
from pathlib import Path
import sys
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from production import ProductionCatalog
from create_preview_fixture import png

def digest(folder):
    value=hashlib.sha256()
    for path in sorted(folder.rglob('*.png')):
        value.update(path.relative_to(folder).as_posix().encode())
        value.update(path.read_bytes());value.update(str(path.stat().st_mtime_ns).encode())
    return value.hexdigest()

def create(target,count=50_000,root_count=258,*,materialize_images=False):
    if not 120<=count<=50_000 or not 2<=root_count<=258:raise ValueError('Bounded fixture size required')
    if type(materialize_images) is not bool:raise ValueError('Explicit generated-file mode required')
    target.mkdir(parents=True,exist_ok=False)
    db=target/'catalog.sqlite';generated=target/'generated';generated.mkdir()
    actual=count if materialize_images else min(75,count);catalog=ProductionCatalog(db)
    try:
        roots=[];paths=[]
        for n in range(root_count):
            name=f'root-{n:03d}'
            if n in (0,root_count-1):name+='-'+('とりあえず保存した素材フォルダ-'*4)
            path=generated/name
            if len(str(path.resolve()))>230:raise ValueError('Generated root exceeds fixture path bound')
            path.mkdir();paths.append(path);roots.append(catalog.add_root(str(path.resolve())))
        locations=[];metadata=[];mappings=[];per_root={str(root):0 for root in roots}
        types=[('audio','.wav'),('material','.svg'),('video','.mp4'),('book','.cbz'),('archive','.zip')]
        image=png(width=180,height=240)
        for n in range(1,count+1):
            if n<=actual:
                at=(n-1)%root_count if materialize_images else 0
                root=roots[at];kind='image';name=f'{n:05d}-'+('長い作品名・日本語の素材-'*3)+'.png'
                path=paths[at]/name
                # Full mode creates ordinary independent files, not hardlinks.
                path.write_bytes(image);size=len(image);mtime=path.stat().st_mtime_ns
            else:
                root=roots[1+(n-actual-1)%(root_count-1)];kind,suffix=types[n%len(types)]
                name=f'架空メタデータ-{n:05d}'+suffix;size=0;mtime=1
            per_root[str(root)]+=1
            tags=['架空データ','大量表示検証','用途説明・'+('静かな夜の街やデザイン素材の整理に使うメタデータ。'*2)]
            if n==count:tags.append('最後の検証候補')
            locations.append((n,root,name,kind,size,mtime,'present','2026-10-13','2026-10-13'))
            metadata.append((n,name,kind,json.dumps(tags,ensure_ascii=False),'長い本棚・'+('素材の分類-'*8),int(n%100==0)))
            mappings.append((n,n))
        # Direct insertion is test-only; do not add synthetic seeding to production.
        with catalog.connect() as connection:
            connection.executemany('INSERT INTO library_locations(id,root_id,relative_path,kind,size_bytes,mtime_ns,status,discovered_at,last_seen_at) VALUES(?,?,?,?,?,?,?,?,?)',locations)
            connection.executemany('INSERT INTO items(id,title,kind,tags,shelf,favorite) VALUES(?,?,?,?,?,?)',metadata)
            connection.executemany('INSERT INTO item_locations(item_id,location_id) VALUES(?,?)',mappings)
        info={'metadata_count':count,'actual_png_files':actual,'registered_root_count':root_count,'roots':roots,
            'all_items_backed_by_generated_files':materialize_images,
            'per_root':per_root,'long_root_id':roots[-1],'last_item_id':count,
            'max_root_path_chars':max(len(str(p.resolve())) for p in paths),'source_digest':digest(generated),
            'filesystem_scan_run':False,'generated_only':True}
        (target/'fixture.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
        return info
    finally:catalog.close()
