"""Generated-only .NET HTTP probe; no GUI, GPU, normal port or inference."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import secrets
import subprocess
import sys
import threading
import time

REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'app'),str(REPO/'tools')]
from production import ProductionCatalog
from production_server import production_handler,DisabledAI
from ai_settings import AIProfileSettings
from wd_tagger import DisabledTagger
from owned_http_server import OwnedHTTPServer


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--explicit-ipv4',action='store_true',help='Compare direct IPv4 socket setup instead of server no-delay')
    parser.add_argument('--keep-alive',action='store_true',help='Compare fixture-only persistent HTTP connections')
    parser.add_argument('--production',action='store_true',help='Measure the actual production handler without transport overrides')
    parser.add_argument('--animation',action='store_true',help='Also exercise real Core binary animation reads on ten generated frames')
    args=parser.parse_args();target=args.output.resolve()
    if sum((args.keep_alive,args.explicit_ipv4,args.production))>1:parser.error('Select one transport comparison')
    if target.exists() or not target.is_relative_to(REPO/'data/ai-ui'):parser.error('New dedicated data/ai-ui output required')
    target.mkdir(parents=True);media=target/'media';media.mkdir()
    from PIL import Image
    if args.animation:
        frames=[Image.new('RGBA',(512,256),(50+i*30,100,160,255)) for i in range(5)]
        try:frames[0].save(media/'generated.png',save_all=True,append_images=frames[1:],duration=80,loop=2)
        finally:
            for frame in frames:frame.close()
    else:
        with Image.frombytes('RGB',(512,768),random.Random(21).randbytes(512*768*3)) as image:
            image.save(media/'generated.png')
    source=media/'generated.png';before=(hashlib.sha256(source.read_bytes()).hexdigest(),source.stat().st_mtime_ns)
    catalog=ProductionCatalog(target/'catalog.sqlite');root=catalog.add_root(str(media));catalog.index.scan(root);catalog.sync_index()
    item=catalog.search()['items'][0]['id'];report={'pass':False,'gui':False,'gpu':False,'samples_per_kind':3,'cases':[]}
    try:
        for enabled in ((True,) if args.production else (False,True)):
            server_timings=[]
            token=secrets.token_hex(32);instance=secrets.token_hex(16)
            profiles=AIProfileSettings(REPO,target/'ai-settings.json',profile_directory=target/'profiles',ai_python=str(target/'missing-python'),models_root=target/'missing-models')
            handler=production_handler(catalog,token,ai=DisabledAI(),tagger=DisabledTagger(),profiles=profiles,
                instance_id=instance,runtime_preferences=target/'launch-settings.json')
            class Variant(handler):
                disable_nagle_algorithm=handler.disable_nagle_algorithm if args.production else args.keep_alive or enabled and not args.explicit_ipv4
                protocol_version=handler.protocol_version if args.production else 'HTTP/1.1' if enabled and args.keep_alive else 'HTTP/1.0'
                def log_message(self,*args):pass
                def setup(self):
                    super().setup();self.probe_connection_started=time.perf_counter();self.probe_requests=0
                    if not args.production:self.connection.settimeout(5)
                def parse_request(self):
                    self.probe_parse_started=time.perf_counter();result=super().parse_request();self.probe_parse_finished=time.perf_counter();return result
                def send_header(self,name,value):
                    if args.keep_alive and enabled and name.lower()=='connection' and self.probe_requests<16:value='keep-alive'
                    return super().send_header(name,value)
                def do_GET(self):
                    self.probe_started=time.perf_counter();self.probe_requests+=1
                    return super().do_GET()
                def do_POST(self):
                    self.probe_started=time.perf_counter();self.probe_requests+=1
                    return super().do_POST()
                def send(self,*args,**kwargs):
                    sending=time.perf_counter();result=super().send(*args,**kwargs)
                    server_timings.append({'path':self.path,'request_started_qpc_seconds':self.probe_started,
                        'connection_started_qpc_seconds':self.probe_connection_started,'parse_started_qpc_seconds':self.probe_parse_started,
                        'parse_finished_qpc_seconds':self.probe_parse_finished,
                        'send_started_qpc_seconds':sending,'send_finished_qpc_seconds':time.perf_counter()})
                    return result
            server=OwnedHTTPServer(('127.0.0.1',0),Variant);worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            try:
                env={**os.environ,'AREDOKO_PROBE_TOKEN':token,'DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE':'true'}
                env['AREDOKO_PROBE_IPV4']='1' if enabled and args.explicit_ipv4 else '0'
                env['AREDOKO_PROBE_ANIMATION']='1' if args.animation else '0'
                result=subprocess.run(['dotnet','run','--project',str(REPO/'tests/Aredoko.Core.Tests/Aredoko.Core.Tests.csproj'),
                    '-c','Release','--no-build','--','--viewer-transport-probe',f'http://127.0.0.1:{server.server_port}/',str(item),instance],
                    cwd=REPO,env=env,capture_output=True,text=True,encoding='utf-8',timeout=30)
                (target/f'probe-{int(enabled)}.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
                if result.returncode:raise RuntimeError('Owned .NET probe failed; inspect dedicated log')
                report['cases'].append({'tcp_no_delay':Variant.disable_nagle_algorithm,'explicit_ipv4':enabled and args.explicit_ipv4,
                    'keep_alive':enabled and args.keep_alive,'production_policy':args.production,'results':json.loads(result.stdout),'server_timings':server_timings,'exit_code':result.returncode})
            finally:
                server.shutdown();server.server_close();worker.join(5)
                for owner in (handler.startup_scans,handler.thumbnails,handler.results,handler.animations,handler.setup_jobs,
                              handler.download_jobs,handler.backup_jobs,handler.restore_jobs):owner.close()
        report['sources_unchanged']=before==(hashlib.sha256(source.read_bytes()).hexdigest(),source.stat().st_mtime_ns)
        report['pass']=report['sources_unchanged']
    finally:
        catalog.close();(target/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report));return 0 if report['pass'] else 1


if __name__=='__main__':raise SystemExit(main())
