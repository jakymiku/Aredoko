"""One bounded offline CPU classification request; no persistent model process."""
import argparse
import base64
import csv
import io
import json
import os
from pathlib import Path
import sys
import threading

from tagger_profile import WDProfile, RUNTIME_VERSION

MAX_IMAGE_BYTES=8*1024**2
MAX_REQUEST=12*1024**2


def prepare_image(data, size):
    import numpy as np
    from PIL import Image, ImageOps
    if type(data) is not bytes or not 1<=len(data)<=MAX_IMAGE_BYTES:
        raise ValueError('Image byte limit')
    with Image.open(io.BytesIO(data)) as original:
        if not 0<original.width*original.height<=16_000_000:
            raise ValueError('Image pixel limit')
        # Explicitly use the first animation frame. Honor photo orientation.
        original.seek(0)
        image=ImageOps.exif_transpose(original).convert('RGBA')
    background=Image.new('RGBA',image.size,(255,255,255,255))
    background.alpha_composite(image)
    rgb=background.convert('RGB')
    side=max(rgb.size)
    square=Image.new('RGB',(side,side),(255,255,255))
    square.paste(rgb,((side-rgb.width)//2,(side-rgb.height)//2))
    if side!=size:square=square.resize((size,size),Image.Resampling.BICUBIC)
    # Official ONNX path: NHWC BGR float32 in 0..255 (not timm normalization).
    return np.ascontiguousarray(np.asarray(square,dtype=np.float32)[:,:,::-1][None,...])


def labels(path, count):
    with Path(path).open(encoding='utf-8',newline='') as file:
        reader=csv.DictReader(file)
        if reader.fieldnames!=['tag_id','name','category','count']:
            raise ValueError('Label header mismatch')
        rows=[]
        for row in reader:
            if len(rows)>=count:raise ValueError('Label count mismatch')
            if not row['name'] or len(row['name'])>300 or row['category'] not in ('0','4','9'):
                raise ValueError('Invalid label')
            rows.append((row['name'],int(row['category'])))
    if len(rows)!=count:raise ValueError('Label count mismatch')
    return rows


def infer(session, data, profile):
    import numpy as np
    config=profile.data()
    inputs=session.get_inputs()
    outputs=session.get_outputs()
    size=config['input_size']
    if (len(inputs)!=1 or len(outputs)!=1 or inputs[0].type!='tensor(float)'
            or len(inputs[0].shape)!=4 or inputs[0].shape[1:]!=[size,size,3]
            or len(outputs[0].shape)!=2 or outputs[0].shape[1]!=config['label_count']):
        raise ValueError('Incompatible ONNX signature')
    scores=np.asarray(session.run([outputs[0].name],{inputs[0].name:prepare_image(data,size)})[0])
    if (scores.shape!=(1,config['label_count']) or not np.isfinite(scores).all()
            or (scores<0).any() or (scores>1).any()):
        raise ValueError('Invalid classification output')
    return scores[0].tolist()


def main():
    if hasattr(sys.stdin, 'reconfigure'): sys.stdin.reconfigure(encoding='utf-8')
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'): sys.stderr.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser()
    parser.add_argument('--profile-json',required=True)
    parser.add_argument('--parent-pid',type=int,required=True)
    parser.add_argument('--models-root',type=Path)
    args=parser.parse_args()
    from ai_worker import monitor_parent
    threading.Thread(target=monitor_parent,args=(args.parent_pid,),daemon=True).start()
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    try:
        line=sys.stdin.buffer.readline(MAX_REQUEST+1)
        if not line or len(line)>MAX_REQUEST:raise ValueError('Request limit')
        request=json.loads(line)
        if type(request) is not dict or set(request)!={'image'}:raise ValueError('Invalid request')
        data=base64.b64decode(request['image'],validate=True)
        profile=WDProfile.from_dict(json.loads(args.profile_json))
        directory=profile.verify(Path(__file__).resolve().parents[1],hashes=True,models_root=args.models_root)
        labels(directory/'selected_tags.csv',profile.data()['label_count'])
        import onnxruntime as ort
        if ort.__version__!=RUNTIME_VERSION:raise ValueError('Unexpected ONNX Runtime version')
        options=ort.SessionOptions()
        options.intra_op_num_threads=profile.data()['cpu_threads']
        options.inter_op_num_threads=1
        options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
        # CPU-only first slice: no CUDA DLL installation, driver or GPU fallback.
        session=ort.InferenceSession(str(directory/'model.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
        result={'key':profile.key,'scores':infer(session,data,profile)}
    except Exception as error:
        result={'error':type(error).__name__}
    print(json.dumps(result,allow_nan=False,separators=(',',':')),flush=True)


if __name__=='__main__':main()
