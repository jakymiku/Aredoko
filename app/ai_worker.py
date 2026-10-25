"""Offline embedding adapter worker. JSON stdin/stdout; dependencies isolated."""
import argparse
import base64
import contextlib
import io
import json
import os
import sys
import threading
import time

from ai_profiles import DEFAULT_PROFILE, ModelProfile

def monitor_parent(pid):
    if os.name != 'nt': return
    import ctypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong]
    kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
    handle=kernel.OpenProcess(0x00100000,False,pid)
    if not handle: os._exit(1)
    kernel.WaitForSingleObject(handle,0xFFFFFFFF)
    os._exit(0)

def main():
    if hasattr(sys.stdin, 'reconfigure'): sys.stdin.reconfigure(encoding='utf-8')
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'): sys.stderr.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('--model',required=True)
    parser.add_argument('--parent-pid',type=int,default=os.getppid())
    parser.add_argument('--profile-json')
    args = parser.parse_args()
    profile=ModelProfile.from_dict(json.loads(args.profile_json)) if args.profile_json else DEFAULT_PROFILE
    threading.Thread(target=monitor_parent,args=(args.parent_pid,),daemon=True).start()
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    # Library status/progress may print to stdout; preserve the protocol channel.
    wire = sys.stdout
    with contextlib.redirect_stdout(sys.stderr):
        import torch
        from PIL import Image
        from ai_adapters import load_adapter
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        dtype = torch.bfloat16 if profile.precision=='auto-bf16' and device == 'cuda' and torch.cuda.is_bf16_supported() else torch.float32
        model=load_adapter(profile,args.model,device,dtype)
        actual_dimension=model.dimension
    print(json.dumps({'ready':True,'device':device,'dimension':actual_dimension,'profile':profile.key}),file=wire,flush=True)
    for line in sys.stdin:
        try:
            request = json.loads(line)
            operation = request['operation']
            started=time.perf_counter()
            with contextlib.redirect_stdout(sys.stderr), torch.inference_mode():
                if operation == 'image':
                    if 'cover' not in profile.modalities: raise ValueError('Unsupported modality')
                    data = base64.b64decode(request['image'],validate=True)
                    if len(data) > 8*1024*1024: raise ValueError('Source limit')
                    try:
                        with Image.open(io.BytesIO(data)) as original:
                            if not 0 < original.width*original.height <= 16_000_000: raise ValueError('Pixel limit')
                            from PIL import ImageOps
                            image = ImageOps.exif_transpose(original).convert('RGB')
                            image.thumbnail((768,768))
                    except (OSError,ValueError,Image.DecompressionBombError):
                        print(json.dumps({'skip':True}),file=wire,flush=True)
                        continue
                    vector = model.encode_image(image)
                elif operation in ('query','document'):
                    text = request['text']
                    if not isinstance(text,str) or len(text)>4096: raise ValueError('Text limit')
                    vector=model.encode_text(operation,text)
                else: raise ValueError('Invalid operation')
            response = {'vector':vector.tolist(),'elapsed_ms':round((time.perf_counter()-started)*1000,1),
                        'peak_memory_mib':round(torch.cuda.max_memory_allocated()/1024**2,1) if device=='cuda' else 0}
        except Exception as ex:
            import traceback
            traceback.print_exc(file=sys.stderr)
            response = {'error': f'{type(ex).__name__}: {ex}'}
        print(json.dumps(response,allow_nan=False),file=wire,flush=True)

if __name__ == '__main__': main()

