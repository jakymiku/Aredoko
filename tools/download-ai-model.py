"""Explicit setup only; custom profiles reuse the capped setup proxy."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from ai_profiles import load_profile, DEFAULT_PROFILE

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--profile',type=Path)
    args=parser.parse_args()
    profile=load_profile(args.profile)
    target=profile.model_path(Path(__file__).resolve().parents[1])
    marker=target/'aredoko-revision.txt'
    source=target/'aredoko-source.json'
    identity={'model_id':profile.model_id,'revision':profile.revision}
    if target.exists() and any(target.iterdir()):
        recorded=json.loads(source.read_text(encoding='utf-8')) if source.is_file() else None
        legacy=(profile.model_id==DEFAULT_PROFILE.model_id and profile.revision==DEFAULT_PROFILE.revision
                and marker.is_file() and marker.read_text(encoding='utf-8').strip()==profile.revision)
        if recorded!=identity and not (recorded is None and legacy):
            raise ValueError('Use an empty directory for a different model revision')
    target.mkdir(parents=True,exist_ok=True)
    # Record intent before download, permitting an interrupted setup to resume.
    source.write_text(json.dumps(identity),encoding='utf-8')
    from huggingface_hub import snapshot_download
    snapshot_download(profile.model_id,revision=profile.revision,local_dir=target,
                      ignore_patterns=['README.md','.gitattributes'])
    marker.write_text(profile.revision,encoding='utf-8')
    print('Model stored locally. No library source uploaded.')

if __name__=='__main__': main()
