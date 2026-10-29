"""Video scene/time evaluation from the two user-approved synthetic-asset ZIPs.

Prepare is CPU-only. Run explicitly opts into one bounded GPU batch on an existing
runtime/model. No real user video, normal DB/settings, UI, OCR, WD or download.
Slideshow scene retrieval is not motion, real-video or audio-track acceptance.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tools')]
from storage_lease import plain_path,storage_parent
from ai_runtime import MARKER,object_pairs
from collect_ai_runtime_notices import _read

SCENES=('bookA_p02','bookA_p04','bookB_p01','bookB_p02','asset_02')
QUERIES=[('夕焼けの教室','bookA_p02'),('雨の街角と赤い傘','bookA_p04'),('赤い鳥居の神社と巫女','bookB_p01'),
         ('夜の森の魔法陣と杖','bookB_p02'),('サイバーパンクのネオンの路地裏','asset_02'),
         ('red umbrella on a rainy street','bookA_p04'),('shrine with a red torii gate','bookB_p01')]
LAYOUTS={'scenes-ordered.mp4':tuple(zip(SCENES[:4],(16,16,16,1))),
         'scenes-reversed.mp4':tuple(zip(reversed(SCENES[:4]),(16,16,16,1))),
         'scene-control.mp4':((SCENES[-1],4),)}


def digest(path):
    h=hashlib.sha256()
    with plain_path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024**2),b''):h.update(block)
    return h.hexdigest()


def prepare(zips,output):
    from PIL import Image,ImageOps
    from evaluate_representative_assets import load_assets_from_zip
    from video_previews import _executable
    paths=[plain_path(p) for p in zips]
    allowed={ROOT.parent/'Aredoko-test'/n for n in ('Aredoko_search_test_images_8.zip','Aredoko_text_recognition_test_images_6.zip')}
    if len(paths)!=2 or set(paths)!=allowed:raise ValueError('The two explicitly approved representative ZIPs required')
    output=Path(os.path.abspath(output))
    if not output.is_relative_to(ROOT/'data/ai-ui') or output==ROOT/'data/ai-ui':raise ValueError('New dedicated fixture output required')
    if output.exists():raise FileExistsError('Keep existing fixture unchanged')
    sources=[{'name':p.name,'bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns,'sha256':digest(p)} for p in paths]
    assets=load_assets_from_zip(paths);storage_parent(output);output.mkdir();frames=output/'frames';frames.mkdir();media=output/'media';media.mkdir()
    names={}
    for i,key in enumerate(SCENES):
        with Image.open(io.BytesIO(assets[key]['data'])) as source:
            image=ImageOps.pad(source.convert('RGB'),(256,384),method=Image.Resampling.LANCZOS,color=(24,24,24))
            name=f'scene-{i}.png';image.save(frames/name);image.close();names[key]=name
    entries=[]
    for name,layout in LAYOUTS.items():
        lines=[];segments=[];cursor=0
        for scene,seconds in layout:
            lines.extend(["file '"+names[scene]+"'",'duration '+str(seconds)]);segments.append({'scene':scene,'start_ms':cursor,'end_ms':cursor+seconds*1000});cursor+=seconds*1000
        lines.append("file '"+names[layout[-1][0]]+"'");concat=frames/(Path(name).stem+'.txt');concat.write_text('\n'.join(lines)+'\n')
        destination=media/name
        subprocess.run([_executable('ffmpeg'),'-nostdin','-v','error','-f','concat','-safe','1','-i',str(concat),
            '-t',str(cursor/1000),'-vf','fps=1,format=yuv420p','-c:v','mpeg4','-q:v','2','-an','-y',str(destination)],check=True,timeout=45,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        entries.append({'path':name,'bytes':destination.stat().st_size,'sha256':digest(destination),'duration_ms':cursor,'segments':segments})
    after=[{'name':p.name,'bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns,'sha256':digest(p)} for p in paths]
    if sources!=after:raise ValueError('Representative source ZIP changed')
    value={'format':'aredoko-video-scene-fixture-v1','scope':'approved synthetic representative-asset slideshows, no motion/audio quality claim',
           'sources':sources,'videos':entries,'queries':[{'query':q,'scene':s} for q,s in QUERIES]}
    with (output/'fixture.json').open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
    return value


def fixture(root):
    root=plain_path(root,directory=True);raw=_read(root/'fixture.json',1024**2);value=json.loads(raw,object_pairs_hook=object_pairs)
    if not isinstance(value,dict) or value.get('format')!='aredoko-video-scene-fixture-v1' or not isinstance(value.get('videos'),list) or len(value['videos'])!=len(LAYOUTS):raise ValueError('Fixed scene fixture required')
    if value.get('queries')!=[{'query':q,'scene':s} for q,s in QUERIES]:raise ValueError('Fixed scene queries required')
    seen=set()
    for row in value['videos']:
        name=row.get('path')
        if not isinstance(name,str) or name not in LAYOUTS or name in seen:raise ValueError('Unexpected video fixture path')
        seen.add(name);cursor=0;expected=[]
        for scene,seconds in LAYOUTS[name]:expected.append({'scene':scene,'start_ms':cursor,'end_ms':cursor+seconds*1000});cursor+=seconds*1000
        p=plain_path(root/'media'/name)
        if (row.get('segments')!=expected or row.get('duration_ms')!=cursor or type(row.get('bytes')) is not int
            or p.stat().st_size!=row['bytes'] or digest(p)!=row.get('sha256')):raise ValueError('Scene fixture bytes or boundaries changed')
    if {p.name for p in plain_path(root/'media',directory=True).iterdir()}!=set(LAYOUTS):raise ValueError('Unexpected file in dedicated media')
    if _read(root/'fixture.json',1024**2)!=raw:raise ValueError('Fixture manifest changed')
    return value,hashlib.sha256(raw).hexdigest()


def assess(value,scene,items,id_names):
    gold={row['path']:(seg['start_ms'],seg['end_ms']) for row in value['videos'] for seg in row['segments'] if seg['scene']==scene}
    if not gold:raise ValueError('Expected scene absent from fixed fixture')
    ranks=[i+1 for i,row in enumerate(items) if id_names.get(row.get('id')) in gold]
    intervals=[]
    for row in items:
        name=id_names.get(row.get('id'))
        if name in gold:
            actual=(row.get('video_match_ms'),row.get('video_match_end_ms'))
            intervals.append({'file':name,'expected':list(gold[name]),'actual':list(actual),'match':actual==gold[name]})
    return {'top1':bool(ranks and ranks[0]==1),'recall_at3':sum(r<=3 for r in ranks)/len(gold),'reciprocal_rank':1/ranks[0] if ranks else 0,
            'interval_matches':sum(r['match'] for r in intervals),'expected_intervals':len(gold),'intervals':intervals}


def run(fixture_root,runtime,output):
    target=Path(os.path.abspath(output));runtime=plain_path(runtime,directory=True);fixture_root=plain_path(fixture_root,directory=True)
    if (not target.is_relative_to(ROOT/'data/ai-ui') or target==ROOT/'data/ai-ui' or target.exists()
        or not runtime.is_relative_to(ROOT/'data/ai-ui') or not fixture_root.is_relative_to(ROOT/'data/ai-ui')
        or Path(sys.executable).resolve()!=runtime/'python.exe' or target.is_relative_to(fixture_root) or target.is_relative_to(runtime)):
        raise ValueError('Explicit existing AI Python and new dedicated output required')
    value,fixture_sha=fixture(fixture_root);storage_parent(target);target.mkdir();cache=target/'cache';cache.mkdir()
    for name in ('HF_HOME','HUGGINGFACE_HUB_CACHE','TRANSFORMERS_CACHE','XDG_CACHE_HOME','LOCALAPPDATA','APPDATA','TEMP','TMP'):os.environ[name]=str(cache)
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    report={'completed':False,'pass':False,'gpu_inference':False,'gui':False,'download':False,'motion_quality_verified':False,
            'real_video_quality_verified':False,'audio_track_tested':False,'fixture_sha256':fixture_sha,'scope':value['scope'],
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    catalog=image_owner=feature=process=None
    try:
        from runtime_paths import bind_runtime,verify_runtime_pack,model_directory
        from ai_runtime import inspect_runtime
        manifest_sha=hashlib.sha256(_read(runtime/MARKER,32*1024**2)).hexdigest();bind_runtime(runtime,manifest_sha)
        started=time.monotonic();verify_runtime_pack(runtime/'python.exe');report['verification_seconds']=round(time.monotonic()-started,3)
        import torch
        if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable, defer before model')
        free,_=torch.cuda.mem_get_info();report['free_gpu_mib']=free//1024**2
        if free<3*1024**3:raise RuntimeError('Less than 3 GiB free; defer before model')
        from ai_process import EncoderProcess
        from ai_profiles import DEFAULT_PROFILE
        from ai_search import AISearch
        from production import ProductionCatalog
        from video_direct_feature import VideoDirectFeature
        model=model_directory(ROOT,DEFAULT_PROFILE.directory)
        if (model/'aredoko-revision.txt').read_text().strip()!=DEFAULT_PROFILE.revision:raise ValueError('Existing fixed model required')
        model_before={p.relative_to(model).as_posix():(p.stat().st_size,p.stat().st_mtime_ns) for p in model.rglob('*') if p.is_file()}
        catalog=ProductionCatalog(target/'catalog.sqlite');root=catalog.add_root(str(fixture_root/'media'));catalog.index.scan(root);catalog.sync_index()
        id_names={row['id']:row['title'] for row in catalog.search()['items']}
        if set(id_names.values())!=set(LAYOUTS):raise ValueError('Dedicated video library differs')
        image_owner=AISearch(catalog,EncoderProcess(str(runtime/'python.exe'),model,DEFAULT_PROFILE,gpu_budget_mib=3072))
        feature=VideoDirectFeature(catalog,image_owner,stage_parent=target)
        started=time.monotonic();feature.start({'consent':True,'conditions':{'root_ids':[root]}});feature.owner.thread.join(300)
        if feature.owner.thread.is_alive():feature.cancel();raise TimeoutError('Scene batch deadline reached')
        report['index_seconds']=round(time.monotonic()-started,3);report['status_after']=feature.status()
        if feature.status()['state']!='completed':raise RuntimeError('Scene index incomplete')
        process=feature.encoder.process;report['gpu_inference']=feature.encoder.device=='cuda';results=[]
        with feature.owner.index.store.connect() as db:report['stored_intervals']=db.execute('SELECT item_id,start_ms,end_ms FROM ai_video_direct_windows ORDER BY item_id,ordinal').fetchall()
        expected={(row['path'],seg['start_ms'],seg['end_ms']) for row in value['videos'] for seg in row['segments']}
        if {(id_names[i],start,end) for i,start,end in report['stored_intervals']}!=expected:raise ValueError('Stored scene coverage differs from fixture')
        for row in value['queries']:
            started=time.monotonic();result=feature.search(row['query'],root_ids=[root]);results.append({**row,**assess(value,row['scene'],result['items'],id_names),'seconds':round(time.monotonic()-started,3)})
        report['queries']=results;n=len(results)
        report['metrics']={'query_count':n,'top1':sum(r['top1'] for r in results)/n,'mean_recall_at3':sum(r['recall_at3'] for r in results)/n,
            'mrr':sum(r['reciprocal_rank'] for r in results)/n,'interval_matches':sum(r['interval_matches'] for r in results),'expected_intervals':sum(r['expected_intervals'] for r in results)}
        report['telemetry']=feature.encoder.telemetry;feature.release()
        origin=next(i for i,name in id_names.items() if name=='scenes-ordered.mp4')
        with patch.object(feature.encoder,'encode',side_effect=AssertionError('Cached similarity must not infer')):similar=feature.similar(origin,root_ids=[root])
        report['cached_similarity']=[{'file':id_names[r['id']],'origin_interval':[r['origin_match_ms'],r['origin_match_end_ms']],
            'candidate_interval':[r['video_match_ms'],r['video_match_end_ms']]} for r in similar['items']]
        report['cached_without_model']=not feature.encoder.resident;report['image_worker_not_started']=not image_owner.encoder.resident
        report['fixture_unchanged']=fixture(fixture_root)[1]==fixture_sha
        report['model_metadata_unchanged']=model_before=={p.relative_to(model).as_posix():(p.stat().st_size,p.stat().st_mtime_ns) for p in model.rglob('*') if p.is_file()}
        with catalog.connect() as db:report['db_integrity']=db.execute('PRAGMA integrity_check').fetchone()[0]
        report['completed']=True
        report['pass']=report['gpu_inference'] and report['cached_without_model'] and report['image_worker_not_started'] and report['fixture_unchanged'] and report['model_metadata_unchanged'] and report['db_integrity']=='ok'
    except Exception:report['error']=traceback.format_exc()
    finally:
        if feature:
            if process is None:process=feature.encoder.process
            feature.close()
        if image_owner:image_owner.close()
        if catalog:catalog.close()
        report['owned_worker_stopped']=process is not None and process.poll() is not None
        report['owned_worker_exit']=None if process is None else process.poll();report['pass']=report['pass'] and report['owned_worker_stopped']
        with (target/'report.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k not in ('queries','status_after','stored_intervals')},ensure_ascii=False))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    p=commands.add_parser('prepare');p.add_argument('--zip',type=Path,nargs=2,required=True);p.add_argument('--output',type=Path,required=True)
    p=commands.add_parser('run');p.add_argument('--fixture',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--gpu',action='store_true',required=True)
    a=parser.parse_args()
    if a.command=='prepare':value=prepare(a.zip,a.output);print(json.dumps({'prepared':True,'videos':len(value['videos']),'queries':len(value['queries']),'gpu':False}));return 0
    return 0 if run(a.fixture,a.runtime,a.output)['pass'] else 1


if __name__=='__main__':raise SystemExit(main())
