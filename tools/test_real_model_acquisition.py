"""Explicitly consented real model transfer acceptance; never load models."""
import argparse,json,sys,time,urllib.request
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import patch
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from ai_acquisition import acquire
from ai_acquisition_registry import load_trusted_specs
from ai_download_jobs import AIDownloadJobs


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--catalog',action='append',required=True)
    parser.add_argument('--consent',action='store_true')
    parser.add_argument('--resume-record',choices=('report.json','resume-report-02.json'),default='report.json')
    parser.add_argument('--resume-existing',action='store_true',help='Continue the prior failed acceptance without deleting its partials/report')
    args=parser.parse_args();target=args.output.resolve()
    if not args.consent:parser.error('Explicit transfer consent required')
    if not target.is_relative_to(REPO/'data/ai-ui'):
        parser.error('Dedicated repository evidence required')
    previous=None
    if args.resume_existing:
        previous=json.loads((target/args.resume_record).read_bytes())
        result_name='resume-report-03.json' if args.resume_record=='resume-report-02.json' else 'resume-report-02.json'
        if not previous.get('closed') or previous.get('pass') or (target/result_name).exists():
            parser.error('One failed, closed prior acceptance required')
    elif target.exists():parser.error('New dedicated evidence required')
    specifications=load_trusted_specs(REPO)
    selected=[pair for pair in specifications if pair[0].key in args.catalog]
    if len(selected)!=len(set(args.catalog)) or any(c.kind!='model' for c,_ in selected):
        parser.error('Explicit registered model IDs required')
    if not args.resume_existing:target.mkdir(parents=True)
    report={'pass':False,'models_loaded':False,'gpu_inference':False,'settings_changed':False,
            'consent':'explicit human approval 2026-10-25: both models approx 2GB, dedicated output only',
            'models':[],'requests':[]}
    pending_cancel=None;current_key=None;errors=[]
    report['downloader_sha256']=__import__('hashlib').sha256((REPO/'app/ai_acquisition.py').read_bytes()).hexdigest()
    if previous is not None:report['previous_report']=args.resume_record
    original_open=urllib.request.OpenerDirector.open
    class ObservedResponse:
        def __init__(self,response):self.response=response
        def __getattr__(self,name):return getattr(self.response,name)
        def __enter__(self):return self
        def __exit__(self,*args):self.response.close()
        def read(self,*args):
            try:return self.response.read(*args)
            except Exception as error:
                errors.append({'catalog':current_key,'operation':'read','type':type(error).__name__,'errno':getattr(error,'errno',None)})
                raise
    def observed_open(opener,request,*pos,**kw):
        try:
            response=original_open(opener,request,*pos,**kw)
        except Exception as error:
            errors.append({'catalog':current_key,'type':type(error).__name__,'http_status':getattr(error,'code',None)})
            raise
        report['requests'].append({'catalog':current_key,'request_host':urlsplit(request.full_url).hostname,
            'file':urlsplit(request.full_url).path.rsplit('/',1)[-1],'range':request.get_header('Range'),
            'status':response.status,'content_range':response.headers.get('Content-Range'),
            'final_host':urlsplit(response.geturl()).hostname})  # Never persist signed query URLs.
        return ObservedResponse(response)
    last_print=0;last_stage=None
    def transfer(catalog,root,**options):
        original_progress=options.pop('progress')
        def progress(value):
            nonlocal last_print,last_stage,pending_cancel
            original_progress(value)
            if pending_cancel==catalog.key and value['stage']=='downloading' and value['bytes_received']>=8*1024**2:
                pending_cancel=None
                jobs.cancel(jobs.snapshot()['job_id'])
            if time.monotonic()-last_print>10 or last_stage!=value['stage']:
                print(json.dumps({'catalog':catalog.key,**value}),flush=True)
                last_print=time.monotonic();last_stage=value['stage']
        return acquire(catalog,root,progress=progress,**options)
    def finish(timeout):
        deadline=time.monotonic()+timeout
        while jobs.thread.is_alive() and time.monotonic()<deadline:
            jobs.thread.join(.5)
        if jobs.thread.is_alive():
            jobs.cancel(jobs.snapshot()['job_id']);jobs.close()
            raise RuntimeError('Transfer deadline reached')
        return jobs.snapshot()
    jobs=AIDownloadJobs(target/'downloads',specifications=tuple(selected),download=transfer)
    try:
        with patch.object(urllib.request.OpenerDirector,'open',observed_open):
            for catalog,validator in selected:
                current_key=catalog.key;pending_cancel=catalog.key
                body={'consent':True,'catalog_id':catalog.fingerprint,'bytes_per_second':None}
                model={'key':catalog.key,'catalog_id':catalog.fingerprint,'bytes':sum(e.size for e in catalog.entries)}
                report['models'].append(model)
                print(json.dumps({'starting':catalog.key,'bytes':model['bytes'],'rate_limit':None}),flush=True)
                prior=next((m for m in (previous or {}).get('models',[]) if m['key']==catalog.key),None)
                if prior is not None:
                    if prior['catalog_id']!=catalog.fingerprint or not prior.get('cancelled'):
                        raise RuntimeError('Prior cancellation catalog changed')
                    pending_cancel=None
                    model['cancelled']=True;model['prior_cancelled']=args.resume_record
                else:
                    jobs.start(body);cancelled=finish(180)
                    model['cancelled']=cancelled['state']=='cancelled' and not cancelled['published']
                    if not model['cancelled']:raise RuntimeError('Expected real cancellation before publication')
                stage=jobs.root/('.acquire-'+catalog.fingerprint)
                model['partial_files']={p.name:p.stat().st_size for p in (stage/'parts').glob('*.part')}
                if not any(0<size<max(e.size for e in catalog.entries) for size in model['partial_files'].values()):
                    raise RuntimeError('Partial transfer evidence missing')
                model['published_before_resume']=any(p.name.startswith(catalog.key+'-') for p in jobs.root.iterdir())
                if model['published_before_resume']:raise RuntimeError('Cancelled acquisition published unexpectedly')
                resumed_index=len(report['requests']);started=time.monotonic()
                jobs.start(body);complete=finish(1800)
                model['complete']=complete['state']=='complete' and complete['published']
                model['error_code']=complete.get('error_code')
                model['resume_seconds']=round(time.monotonic()-started,3)
                model['resume_requests']=report['requests'][resumed_index:]
                model['range_206']=any(r['range'] is not None and r['status']==206 for r in model['resume_requests'])
                if not model['complete']:raise RuntimeError('Real transfer or validation failed')
                if not model['range_206']:raise RuntimeError('Server did not demonstrate a ranged resume')
                model['verified_bytes']=complete['bytes_verified'];model['root']=complete['result']['root']
                if complete['bytes_verified']!=model['bytes']:raise RuntimeError('Full catalog byte validation not reached')
                print(json.dumps({'completed':catalog.key,'verified_bytes':model['verified_bytes'],'range_206':model['range_206']}),flush=True)
            report['pass']=True
    except Exception as error:
        report['failure_type']=type(error).__name__
        report['failure_reason']=str(error) if type(error) is RuntimeError else 'See sanitized transport errors'
        report['last_job']=jobs.snapshot()
    finally:
        report['closed']=jobs.close()
        report['transport_errors']=errors
        (target/(result_name if args.resume_existing else 'report.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'pass':report['pass'],'closed':report['closed'],'models':[(m['key'],m.get('complete')) for m in report['models']]}),flush=True)
    return 0 if report['pass'] and report['closed'] else 1

if __name__=='__main__':raise SystemExit(main())
