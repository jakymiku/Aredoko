"""Generated loopback original/304 timing; excludes Windows decode and rendering."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import random
import statistics
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from production import ProductionCatalog
from production_server import production_handler,DisabledAI


def measure(samples=12):
    if not 3<=samples<=100:raise ValueError('Use 3..100 samples')
    from PIL import Image
    buffer=io.BytesIO()
    Image.frombytes('RGB',(512,768),random.Random(21).randbytes(512*768*3)).save(buffer,format='PNG')
    data=buffer.getvalue();results={}
    with tempfile.TemporaryDirectory(prefix='aredoko-viewer-http-') as folder:
        base=Path(folder);media=base/'generated media';media.mkdir()
        (media/'image.png').write_bytes(data)
        with zipfile.ZipFile(media/'book.cbz','w',compression=zipfile.ZIP_STORED) as archive:
            for n in range(4):archive.writestr(f'p{n}.png',data)
        sources={p.name:(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns) for p in media.iterdir()}
        catalog=ProductionCatalog(base/'catalog.sqlite')
        server=None;worker=None
        try:
            root=catalog.add_root(str(media));catalog.index.scan(root);catalog.sync_index()
            ids={row['title']:row['id'] for row in catalog.search()['items']}
            server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(catalog,'generated-token',ai=DisabledAI()))
            worker=threading.Thread(target=server.serve_forever);worker.start()
            origin=f'http://127.0.0.1:{server.server_port}'
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            def get(route,tag=None):
                headers={'X-Aredoko-Token':'generated-token'}
                if tag is not None:headers['If-None-Match']=tag
                start=time.perf_counter()
                try:response=opener.open(urllib.request.Request(origin+route,headers=headers),timeout=10)
                except urllib.error.HTTPError as error:
                    if error.code!=304:raise
                    response=error
                with response:
                    body=response.read()
                    return response.status,response.headers.get('ETag'),len(body),(time.perf_counter()-start)*1000
            with opener.open(urllib.request.Request(origin+f"/api/library/reader/{ids['book.cbz']}",headers={'X-Aredoko-Token':'generated-token'})) as response:
                revision=json.load(response)['revision']
            routes={'image':f"/api/library/preview/{ids['image.png']}/original",
                    'archive_page':f"/api/library/reader/{ids['book.cbz']}/original/0?revision={revision}"}
            for kind,route in routes.items():
                _,tag,_,_=get(route)
                full=[];unchanged=[];full_bytes=unchanged_bytes=0
                # Alternate order to reduce systematic sequential/cache bias.
                for n in range(samples):
                    for conditional in ([False,True] if n%2==0 else [True,False]):
                        status,current,size,elapsed=get(route,tag if conditional else None)
                        if conditional:
                            assert status==304 and current==tag and size==0
                            unchanged.append(elapsed);unchanged_bytes+=size
                        else:
                            assert status==200 and current==tag and size==len(data)
                            full.append(elapsed);full_bytes+=size
                def summary(values):
                    values=sorted(values)
                    return {'median_ms':statistics.median(values),'p95_ms':values[min(len(values)-1,int(.95*len(values)))]}
                results[kind]={'full_200':{**summary(full),'body_bytes':full_bytes},
                               'revalidated_304':{**summary(unchanged),'body_bytes':unchanged_bytes}}
            after={p.name:(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns) for p in media.iterdir()}
            assert after==sources
        finally:
            if server is not None:server.shutdown();server.server_close()
            if worker is not None:worker.join(5)
            catalog.close()
    return {'pass':True,'samples_per_mode':samples,'original_page_bytes':len(data),
            'scope':'generated warm loopback HTTP only; not Windows decode/render/HoneyView parity',
            'source_unchanged':True,'results':results}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--samples',type=int,default=12)
    args=parser.parse_args();print(json.dumps(measure(args.samples),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
