"""Explicit offline backup/recovery; no original-media access, downloads or GUI."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from storage_backup import backup,restore,DEFAULT_MAX_BYTES
from storage_lease import StorageBusyError

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    create=commands.add_parser('backup');create.add_argument('--catalog',type=Path,required=True)
    create.add_argument('--settings',type=Path);create.add_argument('--viewer-settings',type=Path);create.add_argument('--profiles',type=Path)
    create.add_argument('--profile-file',type=Path,action='append',default=[])
    create.add_argument('--tagger-profile-file',type=Path,action='append',default=[])
    create.add_argument('--omit-ai',action='store_true')
    recover=commands.add_parser('restore');recover.add_argument('--bundle',type=Path,required=True);recover.add_argument('--without-ai',action='store_true')
    for command in (create,recover):command.add_argument('--output',type=Path,required=True);command.add_argument('--max-bytes',type=int,default=DEFAULT_MAX_BYTES)
    args=parser.parse_args()
    try:
        result=backup(args.catalog,args.output,settings=args.settings,viewer_settings=args.viewer_settings,profiles=args.profiles,extra_profiles=args.profile_file,tagger_profiles=args.tagger_profile_file,include_vectors=not args.omit_ai,max_bytes=args.max_bytes) if args.command=='backup' else restore(args.bundle,args.output,without_vectors=args.without_ai,max_bytes=args.max_bytes)
    except (ValueError,OSError,sqlite3.Error,StorageBusyError,InterruptedError) as error:
        print(json.dumps({'error':str(error),'type':type(error).__name__},ensure_ascii=False),file=sys.stderr);return 2
    print(json.dumps(result,ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())
