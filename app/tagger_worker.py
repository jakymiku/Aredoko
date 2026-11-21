"""One bounded offline CPU classification request; no persistent model process."""
import argparse
from array import array
import base64
import csv
import ctypes
import io
import json
import math
import os
from pathlib import Path
import sys
import threading

from tagger_profile import WDProfile, RUNTIME_VERSION
from storage_lease import plain_path

MAX_IMAGE_BYTES=8*1024**2
MAX_REQUEST=12*1024**2


class _OrtNodeArg:
    def __init__(self,name,type_name,shape):
        self.name=name;self.type=type_name;self.shape=shape


def bundled_ort_dll(repo):
    repo=Path(repo)
    candidates=(
        repo.parent/'bin/onnxruntime.dll',
        repo/'bin/onnxruntime.dll',
        repo/'data/development-tools/nuget/packages/microsoft.windows.ai.machinelearning/2.1.74/runtimes/win-x64/native/onnxruntime.dll',
    )
    for candidate in candidates:
        try:
            checked=plain_path(candidate)
            if checked.stat().st_size>1_000_000:
                return checked
        except (ValueError,OSError):
            continue
    return None


class OrtDllSession:
    """Minimal ctypes binding over Microsoft's bundled onnxruntime.dll (API v14)."""
    def __init__(self,dll_path,model_path,cpu_threads=4):
        dll_path=plain_path(dll_path);model_path=plain_path(model_path)
        self._env=self._opts=self._sess=self._alloc=None
        self._api=None
        try:
            with os.add_dll_directory(str(dll_path.parent)):
                self._dll=ctypes.CDLL(str(dll_path))
            self._dll.OrtGetApiBase.restype=ctypes.POINTER(ctypes.c_void_p)
            base=self._dll.OrtGetApiBase()
            get_api=ctypes.CFUNCTYPE(ctypes.POINTER(ctypes.c_void_p),ctypes.c_uint32)(base[0])
            api=get_api(14)
            if not api:raise RuntimeError('Unsupported ONNX Runtime C API')
            self._api=api
            self._get_err_msg=ctypes.CFUNCTYPE(ctypes.c_char_p,ctypes.c_void_p)(api[2])
            self._release_status=ctypes.CFUNCTYPE(None,ctypes.c_void_p)(api[93])
            self._release_env=ctypes.CFUNCTYPE(None,ctypes.c_void_p)(api[92])
            self._release_opts=ctypes.CFUNCTYPE(None,ctypes.c_void_p)(api[100])
            self._release_sess=ctypes.CFUNCTYPE(None,ctypes.c_void_p)(api[95])
            self._release_val=ctypes.CFUNCTYPE(None,ctypes.c_void_p)(api[96])
            self._release_mem=ctypes.CFUNCTYPE(None,ctypes.c_void_p)(api[94])
            self._release_ti=ctypes.CFUNCTYPE(None,ctypes.c_void_p)(api[98])
            self._release_tsi=ctypes.CFUNCTYPE(None,ctypes.c_void_p)(api[99])

            create_env=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_int,ctypes.c_char_p,ctypes.POINTER(ctypes.c_void_p))(api[3])
            create_opts=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p))(api[10])
            set_intra=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int)(api[24])
            set_inter=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int)(api[25])
            set_exec=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int)(api[13])
            create_sess=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p))(api[7])
            get_alloc=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p))(api[78])

            self._chk(create_env(3,b'aredoko',ctypes.byref(env:=ctypes.c_void_p())));self._env=env
            self._chk(create_opts(ctypes.byref(opts:=ctypes.c_void_p())));self._opts=opts
            self._chk(set_intra(opts,cpu_threads))
            self._chk(set_inter(opts,1))
            self._chk(set_exec(opts,0))
            self._chk(get_alloc(ctypes.byref(alloc:=ctypes.c_void_p())));self._alloc=alloc
            self._chk(create_sess(env,str(model_path),opts,ctypes.byref(sess:=ctypes.c_void_p())));self._sess=sess

            self._inputs=self._inspect_ports(is_input=True)
            self._outputs=self._inspect_ports(is_input=False)
        except Exception:
            self.close()
            raise

    def _chk(self,status):
        if status:
            message=self._get_err_msg(status).decode('utf-8','replace')
            self._release_status(status)
            raise RuntimeError(message)

    def _inspect_ports(self,*,is_input):
        api=self._api
        get_count=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t))(api[30 if is_input else 31])
        get_ti=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_void_p))(api[33 if is_input else 34])
        get_name=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p))(api[36 if is_input else 37])
        alloc_free=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p)(api[76])
        cast_ti=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p))(api[55])
        get_et=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_int))(api[60])
        get_dc=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t))(api[61])
        get_dims=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_int64),ctypes.c_size_t)(api[62])

        count=ctypes.c_size_t();self._chk(get_count(self._sess,ctypes.byref(count)))
        ports=[]
        for index in range(count.value):
            name_ptr=ctypes.c_void_p();self._chk(get_name(self._sess,index,self._alloc,ctypes.byref(name_ptr)))
            try:name=ctypes.string_at(name_ptr.value).decode('utf-8')
            finally:alloc_free(self._alloc,name_ptr)
            ti=ctypes.c_void_p();self._chk(get_ti(self._sess,index,ctypes.byref(ti)))
            try:
                tsi=ctypes.c_void_p();self._chk(cast_ti(ti,ctypes.byref(tsi)))
                et=ctypes.c_int();self._chk(get_et(tsi,ctypes.byref(et)))
                dc=ctypes.c_size_t();self._chk(get_dc(tsi,ctypes.byref(dc)))
                dims=(ctypes.c_int64*dc.value)();self._chk(get_dims(tsi,dims,dc.value))
                shape=[('batch' if d<0 else int(d)) for d in dims]
                ports.append(_OrtNodeArg(name,'tensor(float)' if et.value==1 else f'tensor({et.value})',shape))
            finally:
                self._release_ti(ti)
        return ports

    def get_inputs(self):return self._inputs
    def get_outputs(self):return self._outputs

    def run(self,output_names,input_feed):
        if len(output_names)!=1 or len(input_feed)!=1:raise ValueError('Single input/output inference expected')
        api=self._api
        create_mem=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.POINTER(ctypes.c_void_p))(api[69])
        create_tensor=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_int64),ctypes.c_size_t,ctypes.c_int,ctypes.POINTER(ctypes.c_void_p))(api[49])
        run_fn=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_char_p),ctypes.POINTER(ctypes.c_void_p),ctypes.c_size_t,ctypes.POINTER(ctypes.c_char_p),ctypes.c_size_t,ctypes.POINTER(ctypes.c_void_p))(api[9])
        get_shape_info=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p))(api[65])
        get_et=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_int))(api[60])
        get_dc=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t))(api[61])
        get_dims=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_int64),ctypes.c_size_t)(api[62])
        get_data=ctypes.CFUNCTYPE(ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p))(api[51])

        in_name,tensor=next(iter(input_feed.items()))
        if hasattr(tensor,'ctypes') and hasattr(tensor,'shape'):
            shape=[int(d) for d in tensor.shape];addr=tensor.ctypes.data;nbytes=tensor.nbytes
            keepalive=tensor
        elif isinstance(tensor,array) and tensor.typecode=='f':
            expected_shape=[1 if isinstance(d,str) else int(d) for d in self._inputs[0].shape]
            if math.prod(expected_shape)!=len(tensor):raise ValueError('Input tensor shape mismatch')
            shape=expected_shape;addr,count=tensor.buffer_info();nbytes=count*4
            keepalive=tensor
        else:
            raise TypeError('Unsupported float32 input buffer')

        mem=in_val=out_val=None
        try:
            self._chk(create_mem(1,0,ctypes.byref(mem:=ctypes.c_void_p())))
            c_shape=(ctypes.c_int64*len(shape))(*shape)
            self._chk(create_tensor(mem,ctypes.c_void_p(addr),nbytes,c_shape,len(shape),1,ctypes.byref(in_val:=ctypes.c_void_p())))
            in_names=(ctypes.c_char_p*1)(in_name.encode('utf-8'))
            out_names=(ctypes.c_char_p*1)(output_names[0].encode('utf-8'))
            in_vals=(ctypes.c_void_p*1)(in_val.value)
            out_vals=(ctypes.c_void_p*1)(None)
            self._chk(run_fn(self._sess,None,in_names,in_vals,1,out_names,1,out_vals))
            out_val=ctypes.c_void_p(out_vals[0])
            tsi=ctypes.c_void_p();self._chk(get_shape_info(out_val,ctypes.byref(tsi)))
            try:
                et=ctypes.c_int();self._chk(get_et(tsi,ctypes.byref(et)))
                dc=ctypes.c_size_t();self._chk(get_dc(tsi,ctypes.byref(dc)))
                odims=(ctypes.c_int64*dc.value)();self._chk(get_dims(tsi,odims,dc.value))
                if et.value!=1 or dc.value!=2 or odims[0]!=1 or odims[1]<1:raise ValueError('Unexpected output tensor shape')
                out_len=int(odims[1])
            finally:
                self._release_tsi(tsi)
            out_ptr=ctypes.c_void_p();self._chk(get_data(out_val,ctypes.byref(out_ptr)))
            floats=list(ctypes.cast(out_ptr,ctypes.POINTER(ctypes.c_float*out_len)).contents)
            return [[floats]]
        finally:
            if out_val:self._release_val(out_val)
            if in_val:self._release_val(in_val)
            if mem:self._release_mem(mem)

    def close(self):
        if getattr(self,'_sess',None):self._release_sess(self._sess);self._sess=None
        if getattr(self,'_opts',None):self._release_opts(self._opts);self._opts=None
        if getattr(self,'_env',None):self._release_env(self._env);self._env=None

    def __del__(self):
        try:self.close()
        except Exception:pass


def prepare_image(data, size):
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
    try:
        import numpy as np
        return np.ascontiguousarray(np.asarray(square,dtype=np.float32)[:,:,::-1][None,...])
    except ModuleNotFoundError:
        r,g,b=square.split()
        return array('f',map(float,Image.merge('RGB',(b,g,r)).tobytes()))


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
    config=profile.data()
    inputs=session.get_inputs()
    outputs=session.get_outputs()
    size=config['input_size']
    if (len(inputs)!=1 or len(outputs)!=1 or inputs[0].type!='tensor(float)'
            or len(inputs[0].shape)!=4 or inputs[0].shape[1:]!=[size,size,3]
            or len(outputs[0].shape)!=2 or outputs[0].shape[1]!=config['label_count']):
        raise ValueError('Incompatible ONNX signature')
    raw=session.run([outputs[0].name],{inputs[0].name:prepare_image(data,size)})[0]
    if isinstance(raw,list):
        if len(raw)!=1 or len(raw[0])!=config['label_count']:
            raise ValueError('Invalid classification output')
        row=raw[0]
        if any(not math.isfinite(s) or not 0<=s<=1 for s in row):
            raise ValueError('Invalid classification output')
        return [float(s) for s in row]
    import numpy as np
    scores=np.asarray(raw)
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
    session=None
    try:
        line=sys.stdin.buffer.readline(MAX_REQUEST+1)
        if not line or len(line)>MAX_REQUEST:raise ValueError('Request limit')
        request=json.loads(line)
        if type(request) is not dict or set(request)!={'image'}:raise ValueError('Invalid request')
        data=base64.b64decode(request['image'],validate=True)
        profile=WDProfile.from_dict(json.loads(args.profile_json))
        repo=Path(__file__).resolve().parents[1]
        directory=profile.verify(repo,hashes=True,models_root=args.models_root)
        labels(directory/'selected_tags.csv',profile.data()['label_count'])
        try:
            import onnxruntime as ort
        except ModuleNotFoundError as error:
            dll=bundled_ort_dll(repo)
            if dll is None:
                from inference_errors import startup_error
                print(json.dumps(startup_error(error)),flush=True)
                return
            try:
                session=OrtDllSession(dll,directory/'model.onnx',cpu_threads=profile.data()['cpu_threads'])
            except Exception as dll_error:
                from inference_errors import startup_error
                print(json.dumps(startup_error(dll_error)),flush=True)
                return
        except Exception as error:
            from inference_errors import startup_error
            print(json.dumps(startup_error(error)),flush=True)
            return
        else:
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
    finally:
        if hasattr(session,'close'):session.close()
    print(json.dumps(result,allow_nan=False,separators=(',',':')),flush=True)


if __name__=='__main__':main()
