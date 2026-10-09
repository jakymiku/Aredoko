"""Opt-in local library index management; does not touch the fictional demo catalog."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from library_index import LibraryIndex


def main(argv=None):
    parser = argparse.ArgumentParser(description='Aredoko read-only media location index')
    parser.add_argument('--db', type=Path, default=ROOT / 'data' / 'library-index.sqlite')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('roots', help='List registered library roots')
    add = sub.add_parser('add', help='Register an existing directory; never scans automatically')
    add.add_argument('directory', type=Path)
    add.add_argument('--exclude', action='append', default=[], metavar='GLOB')
    rules = sub.add_parser('rules', help='Replace custom exclusions (defaults are retained); no scan')
    rules.add_argument('root_id', type=int)
    rules.add_argument('--exclude', action='append', default=[], metavar='GLOB')
    scan = sub.add_parser('scan', help='Scan a registered root without modifying media files')
    scan.add_argument('root_id', type=int)
    scan.add_argument('--dry-run', action='store_true', help='Report changes without writing the index')
    listing = sub.add_parser('locations', help='List indexed locations')
    listing.add_argument('root_id', type=int)
    listing.add_argument('--status', choices=('present', 'missing', 'excluded'))
    listing.add_argument('--limit', type=int, default=100)
    listing.add_argument('--offset', type=int, default=0)
    args = parser.parse_args(argv)
    try:
        index = LibraryIndex(args.db)
        if args.command == 'roots':
            result = index.roots()
        elif args.command == 'add':
            result = {'root_id': index.add_root(args.directory, args.exclude)}
        elif args.command == 'rules':
            result = {'excludes': index.set_excludes(args.root_id, args.exclude)}
        elif args.command == 'scan':
            result = index.scan(args.root_id, dry_run=args.dry_run)
        else:
            result = index.locations(args.root_id, args.status, args.limit, args.offset)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, KeyError, OSError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
