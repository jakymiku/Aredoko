"""Offline embedding adapter worker. JSON stdin/stdout; dependencies isolated."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import contextlib
import io
import json
import os
import sys
import threading
import time

from ai_profiles import DEFAULT_PROFILE, ModelProfile

MAX_WIRE_LINE = 32 * 1024 * 1024
MAX_BATCH_TEXTS = 64
MAX_BATCH_IMAGES = 16


def _decode_image_b64(raw_b64, Image, ImageOps):
    try:
        data = base64.b64decode(raw_b64, validate=True)
        if len(data) > 8 * 1024 * 1024:
            return None
        with Image.open(io.BytesIO(data)) as original:
            if not 0 < original.width * original.height <= 16_000_000:
                return None
            image = ImageOps.exif_transpose(original).convert('RGB')
            image.thumbnail((768, 768))
            return image
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def _is_oom(error):
    return type(error).__name__ == 'OutOfMemoryError' or 'out of memory' in str(error).lower()


def _auto_tune_batch(model, torch, device, profile, Image):
    if device != 'cuda' or 'cover' not in profile.modalities:
        return {
            'tuned_image_batch': 2,
            'tuned_text_batch': 16,
            'tuned_images_per_sec': 0.0,
            'vram_free_mib': 0,
            'device': device,
            'source': 'cpu-default',
        }
    try:
        free_bytes, _ = torch.cuda.mem_get_info()
        free_mib = int(free_bytes // (1024 * 1024))
    except (RuntimeError, AttributeError):
        free_mib = 0
    candidates = (2, 4, 8) if free_mib >= 4000 else ((2, 4) if free_mib >= 2000 else (1, 2))
    sizes = ((768, 512), (512, 768), (640, 640), (768, 432))
    samples = [Image.new('RGB', sizes[i % len(sizes)], ((i * 37) % 255, (i * 73) % 255, (i * 19) % 255)) for i in range(8)]
    best_bs, best_ips = 1, 0.0
    try:
        with torch.inference_mode():
            model.encode_images(samples[:1], batch_size=1)
            torch.cuda.synchronize()
            for bs in candidates:
                try:
                    t0 = time.perf_counter()
                    model.encode_images(samples, batch_size=bs)
                    torch.cuda.synchronize()
                    ips = len(samples) / max(1e-6, time.perf_counter() - t0)
                    if ips > best_ips * 1.05:
                        best_bs, best_ips = bs, ips
                except Exception as ex:
                    if not _is_oom(ex):
                        raise
                    torch.cuda.empty_cache()
                    break
    finally:
        for im in samples:
            im.close()
    return {
        'tuned_image_batch': best_bs,
        'tuned_text_batch': 32,
        'tuned_images_per_sec': round(best_ips, 1),
        'vram_free_mib': free_mib,
        'device': device,
        'source': 'gpu-benchmark',
    }

def select_device(torch):
    if os.environ.get('AREDOKO_AI_DEVICE','').strip().lower()=='cpu':
        return 'cpu','cpu'
    if torch.cuda.is_available():
        return 'cuda','cuda'
    try:
        import torch_directml
        if torch_directml.is_available():
            return torch_directml.device(),'dml'
    except (ImportError,RuntimeError,OSError,AttributeError):
        pass
    return 'cpu','cpu'

def _cuda_bf16_supported(torch):
    try:
        return bool(torch.cuda.is_bf16_supported())
    except (RuntimeError,AttributeError):
        return False

def configure_gpu_budget(torch,device,budget_mib,*,budget_if_cuda=False):
    """Optional owner-supplied CUDA allocator limit, applied before model load."""
    if budget_mib is None:return
    if type(budget_mib) is not int or not 256<=budget_mib<=65536:
        raise ValueError('Invalid worker GPU budget')
    if device!='cuda':
        if budget_if_cuda:return
        raise RuntimeError('Budgeted GPU worker requires CUDA')
    budget=budget_mib*1024**2
    if budget_if_cuda and getattr(getattr(torch,'version',None),'hip',None) is not None:
        try:
            free,total=torch.cuda.mem_get_info()
            if free<budget:raise RuntimeError('Insufficient free GPU memory; defer worker load')
            torch.cuda.set_per_process_memory_fraction(min(1.,budget/total))
        except (RuntimeError,AttributeError) as err:
            if 'Insufficient free GPU memory' in str(err):raise
            return
    else:
        free,total=torch.cuda.mem_get_info()
        if free<budget:raise RuntimeError('Insufficient free GPU memory; defer worker load')
        torch.cuda.set_per_process_memory_fraction(min(1.,budget/total))

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
    parser.add_argument('--gpu-budget-mib',type=int)
    parser.add_argument('--budget-if-cuda',action='store_true')
    args = parser.parse_args()
    profile=ModelProfile.from_dict(json.loads(args.profile_json)) if args.profile_json else DEFAULT_PROFILE
    threading.Thread(target=monitor_parent,args=(args.parent_pid,),daemon=True).start()
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    # Library status/progress may print to stdout; preserve the protocol channel.
    wire = sys.stdout
    try:
        with contextlib.redirect_stdout(sys.stderr):
            import torch
            from PIL import Image, ImageOps
            from ai_adapters import load_adapter
            torch_device,device=select_device(torch)
            configure_gpu_budget(torch,device,args.gpu_budget_mib,budget_if_cuda=args.budget_if_cuda)
            dtype = torch.bfloat16 if profile.precision=='auto-bf16' and device == 'cuda' and _cuda_bf16_supported(torch) else torch.float32
            model=load_adapter(profile,args.model,torch_device,dtype)
            actual_dimension=model.dimension
    except Exception as error:
        from inference_errors import startup_error
        import traceback
        traceback.print_exc(file=sys.stderr)
        print(json.dumps(startup_error(error)),file=wire,flush=True)
        return
    print(json.dumps({'ready':True,'device':device,'dimension':actual_dimension,'profile':profile.key}),file=wire,flush=True)
    auto_tune = None
    def ensure_auto_tune():
        nonlocal auto_tune
        if auto_tune is None:
            auto_tune = _auto_tune_batch(model, torch, device, profile, Image)
        return auto_tune
    # Existing single/batch messages fit below this private wire bound.
    # A malformed oversized line terminates the owner rather than parsing a
    # partial next message or allocating without a limit.
    with ThreadPoolExecutor(max_workers=4) as executor:
        while line := sys.stdin.readline(MAX_WIRE_LINE + 1):
            if len(line) > MAX_WIRE_LINE:
                print(json.dumps({'error':'SourceLimit'}),file=wire,flush=True);break
            try:
                request = json.loads(line)
                operation = request['operation']
                started=time.perf_counter()
                with contextlib.redirect_stdout(sys.stderr), torch.inference_mode():
                    if operation == 'image':
                        if 'cover' not in profile.modalities: raise ValueError('Unsupported modality')
                        image = _decode_image_b64(request['image'], Image, ImageOps)
                        if image is None:
                            print(json.dumps({'skip':True}),file=wire,flush=True)
                            continue
                        try:
                            vector = model.encode_image(image)
                        finally:
                            image.close()
                        response = {'vector':vector.tolist(),'elapsed_ms':round((time.perf_counter()-started)*1000,1),
                                    'peak_memory_mib':round(torch.cuda.max_memory_allocated()/1024**2,1) if device=='cuda' else 0}
                    elif operation == 'document_batch':
                        texts = request.get('texts')
                        mode = request.get('mode', 'normal')
                        if mode not in ('normal', 'turbo'): raise ValueError('Invalid batch mode')
                        if (type(texts) is not list or not 1 <= len(texts) <= MAX_BATCH_TEXTS
                                or any(not isinstance(t, str) or len(t) > 4096 for t in texts)):
                            raise ValueError('Invalid text batch')
                        tuned = ensure_auto_tune()
                        bs = 64 if (mode == 'turbo' and device == 'cuda') else min(tuned['tuned_text_batch'], 16)
                        try:
                            vectors = model.encode_texts('document', texts, batch_size=bs)
                        except Exception as ex:
                            if not _is_oom(ex): raise
                            if device == 'cuda': torch.cuda.empty_cache()
                            vectors = model.encode_texts('document', texts, batch_size=1)
                        response = {'vectors':[v.tolist() if hasattr(v, 'tolist') else list(v) for v in vectors],
                                    'elapsed_ms':round((time.perf_counter()-started)*1000,1),
                                    'peak_memory_mib':round(torch.cuda.max_memory_allocated()/1024**2,1) if device=='cuda' else 0,
                                    'auto_tune':tuned}
                    elif operation == 'image_batch':
                        if 'cover' not in profile.modalities: raise ValueError('Unsupported modality')
                        images_b64 = request.get('images')
                        mode = request.get('mode', 'normal')
                        if mode not in ('normal', 'turbo'): raise ValueError('Invalid batch mode')
                        if (type(images_b64) is not list or not 1 <= len(images_b64) <= MAX_BATCH_IMAGES
                                or any(not isinstance(item, str) for item in images_b64)):
                            raise ValueError('Invalid image batch')
                        tuned = ensure_auto_tune()
                        bs = tuned['tuned_image_batch'] if mode == 'turbo' else min(tuned['tuned_image_batch'], 4)
                        if len(images_b64) > 1:
                            if mode == 'turbo':
                                decoded = list(executor.map(lambda s: _decode_image_b64(s, Image, ImageOps), images_b64))
                            else:
                                sem = threading.Semaphore(2)
                                def _dec_limited(s):
                                    with sem:
                                        return _decode_image_b64(s, Image, ImageOps)
                                decoded = list(executor.map(_dec_limited, images_b64))
                        else:
                            decoded = [_decode_image_b64(images_b64[0], Image, ImageOps)]
                        valid = [(idx, im) for idx, im in enumerate(decoded) if im is not None]
                        out = [None] * len(images_b64)
                        try:
                            if valid:
                                valid_imgs = [im for _, im in valid]
                                try:
                                    vectors = model.encode_images(valid_imgs, batch_size=bs)
                                except Exception as ex:
                                    if not _is_oom(ex): raise
                                    if device == 'cuda': torch.cuda.empty_cache()
                                    vectors = model.encode_images(valid_imgs, batch_size=1)
                                for (idx, _), vec in zip(valid, vectors):
                                    out[idx] = vec.tolist() if hasattr(vec, 'tolist') else list(vec)
                        finally:
                            for _, im in valid:
                                im.close()
                        response = {'vectors':out,
                                    'elapsed_ms':round((time.perf_counter()-started)*1000,1),
                                    'peak_memory_mib':round(torch.cuda.max_memory_allocated()/1024**2,1) if device=='cuda' else 0,
                                    'auto_tune':tuned}
                    elif operation=='video':
                        if 'video' not in profile.modalities:raise ValueError('Unsupported modality')
                        from video_protocol import parse_video_request
                        vector=model.encode_video(parse_video_request(request))
                        response = {'vector':vector.tolist(),'elapsed_ms':round((time.perf_counter()-started)*1000,1),
                                    'peak_memory_mib':round(torch.cuda.max_memory_allocated()/1024**2,1) if device=='cuda' else 0}
                    elif operation=='audio':
                        if 'audio' not in profile.modalities:raise ValueError('Unsupported modality')
                        from audio_protocol import parse_audio_request
                        window=parse_audio_request(request)
                        if window.is_digital_silence:
                            print(json.dumps({'skip':True,'reason':'digital_silence'}),file=wire,flush=True);continue
                        vector=model.encode_audio(window)
                        response = {'vector':vector.tolist(),'elapsed_ms':round((time.perf_counter()-started)*1000,1),
                                    'peak_memory_mib':round(torch.cuda.max_memory_allocated()/1024**2,1) if device=='cuda' else 0}
                    elif operation in ('query','document'):
                        text = request['text']
                        if not isinstance(text,str) or len(text)>4096: raise ValueError('Text limit')
                        vector=model.encode_text(operation,text)
                        response = {'vector':vector.tolist(),'elapsed_ms':round((time.perf_counter()-started)*1000,1),
                                    'peak_memory_mib':round(torch.cuda.max_memory_allocated()/1024**2,1) if device=='cuda' else 0}
                    else: raise ValueError('Invalid operation')
            except Exception as ex:
                import traceback
                traceback.print_exc(file=sys.stderr)
                response = {'error': type(ex).__name__}
            print(json.dumps(response,allow_nan=False),file=wire,flush=True)

if __name__ == '__main__': main()

