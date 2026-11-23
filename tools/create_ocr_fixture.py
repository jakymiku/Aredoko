"""Render only original fixed test text with an already installed Japanese font."""
import argparse
import hashlib
import json
from pathlib import Path
from ocr_quality import control, digest, read_json, validate_fixture


def create(fixture, output, font_path):
    from PIL import Image, ImageDraw, ImageFont
    validate_fixture(fixture)
    # Verify installed font before creating any output; never download/fallback.
    font_path = Path(font_path)
    font_bytes = font_path.read_bytes()
    ImageFont.truetype(str(font_path),32)
    output = Path(output); output.mkdir(parents=True,exist_ok=False)
    images = []
    for page in fixture['pages']:
        image = Image.new('RGB',(1000,700),'white'); draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(str(font_path),page['font_size']); step = page['font_size']+14
        color = (page['contrast'],)*3
        if page['layout']=='vertical':
            for col,line in enumerate(page['text'].split('\n')):
                for row,char in enumerate(line):
                    x,y = 880-col*step, 48+row*step
                    if x<32 or y+step>700: raise ValueError('Text exceeds fixed page bounds')
                    draw.text((x,y),char,font=font,fill=color)
        else:
            for row,line in enumerate(page['text'].split('\n')):
                bounds = draw.textbbox((48,48+row*step),line,font=font)
                if bounds[2]>952 or bounds[3]>668: raise ValueError('Text exceeds fixed page bounds')
                draw.text((48,48+row*step),line,font=font,fill=color)
        file = output/(page['id']+'.png'); image.save(file,format='PNG')
        images.append({'page_id':page['id'],'file':file.name,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
    receipt = {'version':1,'fixture_sha256':digest(fixture),'font_file':font_path.name,'font_sha256':hashlib.sha256(font_bytes).hexdigest(),'images':images,'runtime':'generated text only; no OCR inference'}
    (output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    for kind in ('perfect','empty'):
        (output/(kind+'-control.json')).write_text(json.dumps(control(fixture,kind),ensure_ascii=False,indent=2),encoding='utf-8')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,default=Path(__file__).resolve().parents[1]/'tests/fixtures/ocr-eval-v1.json')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--font',type=Path,default=Path('C:/Windows/Fonts/meiryo.ttc'))
    args = parser.parse_args(); receipt = create(read_json(args.fixture),args.output,args.font)
    print(json.dumps({'fixture_sha256':receipt['fixture_sha256'],'pages':len(receipt['images']),'ocr_inference':False}))


if __name__ == '__main__': main()
