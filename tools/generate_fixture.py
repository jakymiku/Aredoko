import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description="Generate fictional benchmark metadata; never reads user files.")
parser.add_argument("--count", type=int, default=50000)
args = parser.parse_args()
if args.count < 1:
    parser.error("count must be positive")
root = Path(__file__).resolve().parents[1]
output = root / "fixtures" / "generated" / "catalog.jsonl"
output.parent.mkdir(parents=True, exist_ok=True)
kinds = ("book", "image", "video", "audio")
with output.open("w", encoding="utf-8") as stream:
    for i in range(args.count):
        row = {"id": f"fixture-{i:08d}", "title": f"架空サンプル {i:08d}",
               "kind": kinds[i % 4], "tags": [f"tag-{i % 20}"],
               "thumbnail": None, "source": "synthetic", "available": False}
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
print(f"Generated {args.count} fictional records: {output}")
