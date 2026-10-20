"""Measure generated viewer-source stages only, not GPU/GUI or HoneyView parity."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import random
import statistics
import sys
import time
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from production import ProductionCatalog
from previews import PreviewReader
from storage_lease import plain_path


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();target=Path(os.path.abspath(args.output))
    if not target.is_relative_to(ROOT/'data/ai-ui'):parser.error('Use a new data/ai-ui output')
    plain_path(target.parent,directory=True);target.mkdir(exist_ok=False)
    from PIL import Image,ImageDraw
    media=target/'generated-media';media.mkdir()
    frames=[]
    for n in range(48):
        image=Image.new('RGB',(320,240),(30,80,120));draw=ImageDraw.Draw(image)
        draw.rectangle((n*5,40,n*5+60,180),fill=(235,90,40));frames.append(image)
    frames[0].save(media/'moving.gif',save_all=True,append_images=frames[1:],duration=60,loop=0)
    noise=Image.frombytes('L',(1024,1440),random.Random(21).randbytes(1024*1440));encoded=io.BytesIO();noise.save(encoded,format='JPEG',quality=82)
    with zipfile.ZipFile(media/'book.cbz','w',compression=zipfile.ZIP_STORED) as archive:
        for n in range(64):archive.writestr(f'{n:03d}.jpg',encoded.getvalue())
    def snapshot():return {p.name:[hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns] for p in media.iterdir()}
    before=snapshot();catalog=ProductionCatalog(target/'catalog.sqlite')
    try:
        root=catalog.add_root(str(media));catalog.index.scan(root);catalog.sync_index()
        ids={r['title']:r['id'] for r in catalog.search()['items']};reader=PreviewReader(catalog)
        begun=time.perf_counter();manifest=reader.image_manifest(ids['moving.gif'])
        for n in range(manifest['frame_count']):reader.image_frame(ids['moving.gif'],n,manifest['revision'])
        preload=time.perf_counter()-begun
        begun=time.perf_counter();raw,_=reader.read_original(ids['moving.gif']);raw_seconds=time.perf_counter()-begun
        stages=[]
        for n in range(10):
            begun=time.perf_counter();book=reader.manifest(ids['book.cbz']);manifest_seconds=time.perf_counter()-begun
            begun=time.perf_counter();data,_=reader.read_page(ids['book.cbz'],n,book['revision'],original=True);page_seconds=time.perf_counter()-begun
            begun=time.perf_counter();catalog.save_reader_progress(ids['book.cbz'],{'revision':book['revision'],'page':n,'mode':'single'},reader);save_seconds=time.perf_counter()-begun
            stages.append({'manifest':manifest_seconds,'original_page':page_seconds,'save_position':save_seconds})
            assert data==encoded.getvalue()
        report={'pass':True,'generated_gif_frames':manifest['frame_count'],'generated_cbz_pages':64,
                'generated_cbz_bytes':(media/'book.cbz').stat().st_size,
                'legacy_prepare_all_frame_sources_seconds':preload,'new_original_source_read_seconds':raw_seconds,
                'cbz_stages':stages,'cbz_median_source_plus_save_seconds':statistics.median(sum(stage.values()) for stage in stages),
                'source_unchanged':snapshot()==before,'limits':'CPU source stages only; Windows decode/presentation/HTTP and HoneyView not measured; not an end-to-end speedup or parity claim.'}
        assert report['source_unchanged']
        (target/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k!='cbz_stages'}))
    finally:catalog.close()


if __name__=='__main__':main()
