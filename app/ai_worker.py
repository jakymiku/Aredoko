"""Offline EmbeddingGemma worker. JSON stdin/stdout; dependencies isolated."""
import argparse
import base64
import contextlib
import io
import json
import os
import sys
import threading
import time

REVISION = '914f7f89142e33e77833254d9c9b90c3cef7303b'

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
    parser = argparse.ArgumentParser()
    parser.add_argument('--model',required=True)
    parser.add_argument('--parent-pid',type=int,default=os.getppid())
    args = parser.parse_args()
    threading.Thread(target=monitor_parent,args=(args.parent_pid,),daemon=True).start()
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    # Library status/progress may print to stdout; preserve the protocol channel.
    wire = sys.stdout
    with contextlib.redirect_stdout(sys.stderr):
        import torch
        from PIL import Image
        from sentence_transformers import SentenceTransformer
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        dtype = torch.bfloat16 if device == 'cuda' and torch.cuda.is_bf16_supported() else torch.float32
        model = SentenceTransformer(args.model,local_files_only=True,device=device,
            config_kwargs={'audio_config':None},model_kwargs={'torch_dtype':dtype},
            trust_remote_code=False)
    print(json.dumps({'ready':True,'device':device,'dimension':768,'revision':REVISION}),file=wire,flush=True)
    for line in sys.stdin:
        try:
            request = json.loads(line)
            operation = request['operation']
            started=time.perf_counter()
            with contextlib.redirect_stdout(sys.stderr), torch.inference_mode():
                if operation == 'image':
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
                    vector = model.encode({'image':image},normalize_embeddings=True)
                elif operation in ('query','document'):
                    text = request['text']
                    if not isinstance(text,str) or len(text)>4096: raise ValueError('Text limit')
                    vector = model.encode(text,prompt_name='SearchQuery' if operation=='query' else 'Document',
                                          normalize_embeddings=True)
                else: raise ValueError('Invalid operation')
            response = {'vector':vector.tolist(),'elapsed_ms':round((time.perf_counter()-started)*1000,1),
                        'peak_memory_mib':round(torch.cuda.max_memory_allocated()/1024**2,1) if device=='cuda' else 0}
        except Exception as ex:
            response = {'error':type(ex).__name__}
        print(json.dumps(response,allow_nan=False),file=wire,flush=True)

if __name__ == '__main__': main()

