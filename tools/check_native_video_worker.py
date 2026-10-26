"""Explicit GPU API smoke over three generated RGB frames; no DB or media file.

This verifies native video input through the real private worker, not video
search quality, long-video indexing, audio tracks or normal GUI integration.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--gpu',action='store_true',required=True)
    args=parser.parse_args();target=args.output.resolve()
    if not target.is_relative_to(REPO/'data/ai-ui') or target.exists():parser.error('New dedicated output required')
    target.mkdir(parents=True)
    report={'pass':False,'gpu_inference':False,'gui':False,'db_used':False,'download':False,
            'scope':'native video input API only; generated RGB frames, no quality acceptance',
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    encoder=process=None
    try:
        import torch
        from PIL import Image,ImageDraw
        from ai_process import EncoderProcess
        from ai_profiles import video_profile_for
        from runtime_paths import model_directory
        from video_input import VideoWindow
        if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable; defer')
        free,_=torch.cuda.mem_get_info()
        if free<3*1024**3:raise RuntimeError('Less than 3 GiB free; defer before loading')
        frames=[]
        for number in range(3):
            with Image.new('RGB',(128,128),'white') as image:
                ImageDraw.Draw(image).rectangle((8+number*24,40,40+number*24,72),fill='red')
                frames.append(image.tobytes())
        window=VideoWindow(0,3000,128,128,tuple(frames))
        before=[hashlib.sha256(frame).hexdigest() for frame in window.frames]
        profile=video_profile_for();model=model_directory(REPO,profile.directory)
        if (model/'aredoko-revision.txt').read_text(encoding='utf-8').strip()!=profile.revision:
            raise RuntimeError('Existing model revision marker mismatch')
        encoder=EncoderProcess(sys.executable,model,profile,gpu_budget_mib=3072)
        vector=encoder.encode('video',window);process=encoder.process
        report['gpu_inference']=encoder.device=='cuda';report['worker_pid']=process.pid
        query=encoder.encode('query','赤い四角が映っている動画')
        def valid(value):return len(value)==768 and all(math.isfinite(x) for x in value) and abs(sum(x*x for x in value)-1)<1e-4
        report.update(profile=profile.key,revision=profile.revision,frame_count=len(window.frames),
                      dimension=len(vector),video_normalized=valid(vector),query_normalized=valid(query),
                      query_cosine=sum(a*b for a,b in zip(vector,query)),
                      telemetry=encoder.telemetry,allocator_budget_mib=encoder.gpu_budget_mib,
                      source_pixels_unchanged=before==[hashlib.sha256(frame).hexdigest() for frame in window.frames])
        report['pass']=report['gpu_inference'] and report['video_normalized'] and report['query_normalized'] and report['source_pixels_unchanged']
    except Exception:report['error']=traceback.format_exc()
    finally:
        if encoder:
            if process is None:process=encoder.process
            encoder.close()
        report['owned_worker_stopped']=process is not None and process.poll() is not None
        report['owned_worker_exit']=process.poll() if process is not None else None
        report['pass']=report['pass'] and report['owned_worker_stopped']
        (target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));return 0 if report['pass'] else 1


if __name__=='__main__':raise SystemExit(main())
