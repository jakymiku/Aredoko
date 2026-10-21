"""Build a NEW optional AI pack from explicit prepared assets; never downloads."""
import argparse
import ast
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from ai_runtime import FORMAT, MARKER, REQUIRED_MODULES, OPTIONAL_MODULES, validate_abi, files, digest, inspect_runtime
from package_release import copy_payload, validate_output
from release_runtime import python_layout
from storage_lease import plain_path,storage_parent


def source_abi(source):
    stem=python_layout(source,False)
    for name in REQUIRED_MODULES:plain_path(source/f'Lib/site-packages/{name}/__init__.py')
    version=plain_path(source/'Lib/site-packages/torch/version.py')
    if version.stat().st_size>65536:raise ValueError('Torch version document exceeds limit')
    values={}
    # Parse declarations as data. Never import source torch or run a probe.
    for node in ast.parse(version.read_text(encoding='utf-8')).body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            name=node.targets[0].id;value=node.value
        elif isinstance(node,ast.AnnAssign) and isinstance(node.target,ast.Name):name=node.target.id;value=node.value
        else:continue
        if name in ('__version__','cuda') and isinstance(value,ast.Constant):values[name]=value.value
    if '__version__' not in values or 'cuda' not in values:raise ValueError('Torch version declarations are missing')
    modules=list(REQUIRED_MODULES)
    modules.extend(m for m in OPTIONAL_MODULES if (source/f'Lib/site-packages/{m}/__init__.py').is_file())
    abi={'python':'3.'+stem.removeprefix('python3'),'architecture':'x64','engine':'pytorch',
         'compute':'cuda' if values['cuda'] is not None else 'cpu','torch':values['__version__'],
         'cuda':values['cuda'],'modules':modules}
    return validate_abi(abi),stem


def prepare(source,output,*,check=False):
    source=plain_path(source,directory=True);output=Path(os.path.abspath(output))
    validate_output(output)
    if output.is_relative_to(source) or source.is_relative_to(output):raise ValueError('AI pack output overlaps input')
    if (source/MARKER).exists():raise ValueError('Select a prepared runtime, not an existing sealed pack')
    abi,stem=source_abi(source)
    if check:return {'abi':abi,'prepared':False,'inference_verified':False,'downloads':False}
    storage_parent(output);copy_payload(source,output)
    # Isolate packages from the source application's old backend/tools paths.
    (output/(stem+'._pth')).write_text(stem+'.zip\n.\nDLLs\nLib/site-packages\nimport site\n',encoding='utf-8')
    entries=[{'path':p.relative_to(output).as_posix(),'bytes':p.stat().st_size,'sha256':digest(p)} for p in files(output)]
    manifest={'format':FORMAT,'abi':abi,'entries':entries,'files_count':len(entries),'total_bytes':sum(e['bytes'] for e in entries)}
    with (output/MARKER).open('x',encoding='utf-8') as stream:json.dump(manifest,stream,ensure_ascii=False,indent=2)
    info=inspect_runtime(output,verify=True)
    return {**info,'prepared':True,'inference_verified':False,'downloads':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    print(json.dumps(prepare(args.source,args.output,check=args.check),ensure_ascii=True))

if __name__=='__main__':main()
