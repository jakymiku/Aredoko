"""Score saved OCR output against a frozen synthetic fixture. Never runs OCR."""
import argparse
import json
from pathlib import Path
from ocr_quality import evaluate, read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,default=Path(__file__).resolve().parents[1]/'tests/fixtures/ocr-eval-v1.json')
    parser.add_argument('--predictions',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    report = evaluate(read_json(args.fixture),read_json(args.predictions))
    with args.output.open('x',encoding='utf-8') as stream: json.dump(report,stream,ensure_ascii=False,indent=2)
    print(json.dumps({'measurement_kind':report['measurement_kind'],'summary':report['summary']},ensure_ascii=False))


if __name__ == '__main__': main()
