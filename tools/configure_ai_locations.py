"""Developer local setup entry; the product GUI/owned validation job comes next."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from ai_profiles import load_profile
from ai_runtime_preferences import AIRuntimePreferences,UNSET


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings',type=Path,required=True,help='Explicit launch-settings.json, never discovered')
    parser.add_argument('--profile',type=Path)
    runtime=parser.add_mutually_exclusive_group()
    runtime.add_argument('--runtime-root',type=Path)
    runtime.add_argument('--use-bundled-runtime',action='store_true')
    models=parser.add_mutually_exclusive_group()
    models.add_argument('--models-root',type=Path)
    models.add_argument('--default-models-root',action='store_true')
    parser.add_argument('--consent',action='store_true',help='Explicitly trust the selected local runtime and save restart-only locations')
    args=parser.parse_args()
    controller=AIRuntimePreferences(args.settings,Path(__file__).resolve().parents[1],load_profile(args.profile))
    runtime_root=str(args.runtime_root) if args.runtime_root is not None else None if args.use_bundled_runtime else UNSET
    models_root=str(args.models_root) if args.models_root is not None else None if args.default_models_root else UNSET
    if runtime_root is UNSET and models_root is UNSET:result=controller.snapshot()
    else:
        try:result=controller.select(runtime_root=runtime_root,models_root=models_root,consent=args.consent)
        except (ValueError,OSError,RuntimeError) as error:parser.error(str(error))
    print(json.dumps(result,ensure_ascii=True))

if __name__=='__main__':main()
