"""Isolated generated library for similarity checks. No model or private roots.

--prepare-only writes a new fixture; otherwise serves its production API on
loopback until Ctrl+C. An occupied port is refused before fixture creation.
"""
import argparse
from dataclasses import replace
import hashlib
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import json
from pathlib import Path
import secrets
import sys
import threading
import zipfile

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from ai_profiles import DEFAULT_PROFILE
from ai_process import AIUnavailable
from ai_search import AISearch,AIBusy,revision
from ai_settings import AIProfileSettings
from production import ProductionCatalog
from production_server import production_handler
from create_preview_fixture import png


class NoInference:
    available=False
    resident=False
    def __init__(self,text_only=False):
        self.profile=replace(DEFAULT_PROFILE,dimension=3,modalities=('text',) if text_only else ('text','cover'))
        self.calls=0
    def encode(self,*args):
        self.calls+=1
        raise AssertionError('The sandbox must never infer or load an AI model')
    def close(self):pass


class RecordedSimilarity(AISearch):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.requests=[];self.request_lock=threading.Lock()
        self.fail=None;self.delay=False
        self.entered=threading.Event();self.proceed=threading.Event();self.proceed.set()
    def similar(self,item_id,kind='',view='all',page=0,limit=60,**kwargs):
        entry={'item_id':item_id,'kind':kind,'view':view,'page':page,'limit':limit,**kwargs}
        with self.request_lock:self.requests.append(entry)
        try:
            if self.delay:
                self.entered.set()
                if not self.proceed.wait(8):raise AIUnavailable('生成テストの遅延が時間切れになりました。')
            if self.fail=='unavailable':raise AIUnavailable('生成テスト：AIサービスを一時停止しています。')
            if self.fail=='busy':raise AIBusy('生成テスト：AI索引を作成中です。')
            result=super().similar(item_id,kind,view,page,limit,**kwargs)
            entry['ids']=[row['id'] for row in result['items']];entry['total']=result['total'];entry['status']=result['similarity_status']
            return result
        except Exception as ex:
            entry['failed']=type(ex).__name__;raise


class SimilaritySandbox:
    def __init__(self,target,scenario='indexed'):
        self.target=Path(target).resolve()
        if scenario not in ('indexed','unindexed','text-only'):raise ValueError('Unknown sandbox scenario')
        if not self.target.is_relative_to((REPO/'data/ai-ui').resolve()) or self.target==(REPO/'data/ai-ui').resolve():
            raise ValueError('Sandbox must be a new folder inside data/ai-ui')
        self.target.mkdir(parents=True,exist_ok=False)
        self.catalog=self.ai=None
        try:
            self.catalog=ProductionCatalog(self.target/'catalog.sqlite')
            roots=[]
            for number in (1,2):
                folder=self.target/f'media-{number}';folder.mkdir()
                for index in range(1,73 if number==1 else 2):
                    color=(220,30,30) if index%3 else (30,50,220)
                    (folder/f'generated-{index:03}.png').write_bytes(png(60,80,color))
                if number==1:
                    (folder/'generated-unindexed.png').write_bytes(png(60,80,(30,200,30)))
                    (folder/'generated-video.mp4').write_bytes(b'generated unsupported video placeholder')
                    with zipfile.ZipFile(folder/'generated-cover.cbz','w') as archive:
                        archive.writestr('page1.png',png(60,80,(220,30,30)))
                root=self.catalog.add_root(str(folder));roots.append(root)
                self.catalog.start_scan(root);self.catalog._worker.join(10)
                if self.catalog.scan_state()['state']!='complete':raise RuntimeError('Generated scan failed')
            self.scope={'root_ids':[roots[0]],'kind':'','shelf':None}
            settings=self.target/'settings.json'
            settings.write_text(json.dumps({'version':1,'profile':'default','scope':self.scope}),encoding='utf-8')
            self.profiles=AIProfileSettings(REPO,settings)
            self.encoder=NoInference(scenario=='text-only')
            self.ai=RecordedSimilarity(self.catalog,self.encoder)
            self.ids={}
            for row in self.catalog.search(limit=120)['items']:
                self.catalog.update([row['id']],{'tags':['生成素材'],'shelf':'テスト棚','favorite':row['title']=='generated-002.png'})
                row=self.catalog.get(row['id'])
                self.ids[f"{row['root_id']}:{row['title']}"]=row['id']
                vectors={'text':[0,1,0]}
                if scenario!='unindexed' and row['kind'] in ('image','book') and row['title']!='generated-unindexed.png' and 'cover' in self.ai.profile.modalities:
                    vectors['cover']=[0,0,1] if row['title'].startswith('generated-') and row['title'][10:13].isdigit() and int(row['title'][10:13])%3==0 else [1,0,0]
                self.ai.store.put(row['id'],revision(row),vectors)
            self.roots=roots
            self.manifest={'fixture':'aredoko-similarity-v1','actual_model':False,'scenario':scenario,'scope':self.scope,
                'root_ids':roots,'ids':self.ids,'source_total':len(self.ids),'profile':self.ai.profile.key,
                'notes':'Generated PNG/CBZ; deterministic cover vectors. Not model retrieval-quality evidence.'}
            (self.target/'manifest.json').write_text(json.dumps(self.manifest,ensure_ascii=False,indent=2),encoding='utf-8')
            self.source_before=self.source_digest()
            self.settings_before=settings.read_bytes()
        except Exception:
            self.close();raise
    def source_digest(self):
        return {p.relative_to(self.target).as_posix():(p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest())
                for p in self.target.glob('media-*/*') if p.is_file()}
    def item(self,name,root=0):return self.ids[f'{self.roots[root]}:{name}']
    def handler(self):return production_handler(self.catalog,secrets.token_urlsafe(32),ai=self.ai,profiles=self.profiles)
    def close(self):
        if self.ai is not None:
            self.ai.proceed.set();self.ai.close();self.ai=None
        if self.catalog is not None:self.catalog.close();self.catalog=None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--scenario',choices=('indexed','unindexed','text-only'),default='indexed')
    parser.add_argument('--port',type=int,default=8769)
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args()
    if not 1<=args.port<=65535:parser.error('Invalid port')
    server=sandbox=None
    try:
        # Binding first also prevents accidental attachment to a running user API.
        if not args.prepare_only:server=ThreadingHTTPServer(('127.0.0.1',args.port),BaseHTTPRequestHandler)
        sandbox=SimilaritySandbox(args.output,args.scenario)
        if args.prepare_only:
            print('Generated fixture: '+str(sandbox.target));return
        server.RequestHandlerClass=sandbox.handler()
        print(f'Generated similarity sandbox: http://127.0.0.1:{server.server_port}',flush=True)
        print('Contract vectors only; no AI model. Close with Ctrl+C.',flush=True)
        server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        if server:server.server_close()
        if sandbox:
            intact=sandbox.source_before==sandbox.source_digest()
            (sandbox.target/'source-check.json').write_text(json.dumps({'unchanged':intact,'encoder_calls':sandbox.encoder.calls}),encoding='utf-8')
            sandbox.close()

if __name__=='__main__':main()
