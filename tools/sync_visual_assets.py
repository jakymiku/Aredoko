"""Deterministic sizing/copying of the approved v1 assets. No network or creative edits."""
import argparse,hashlib,io,json
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'design/visual-assets/v1'
DEST=ROOT/'src/Aredoko.WinUI/Assets'
SIZES={
 'Square150x150Logo.scale-200.png':('app_icon/aredoko_app_icon_512.png',(300,300)),
 'Square44x44Logo.scale-200.png':('app_icon/aredoko_app_icon_128.png',(88,88)),
 'Square44x44Logo.targetsize-24_altform-unplated.png':('app_icon/aredoko_app_icon_24.png',(24,24)),
 'Square44x44Logo.targetsize-48_altform-lightunplated.png':('app_icon/aredoko_app_icon_48.png',(48,48)),
 'StoreLogo.png':('msix_compatibility/StoreLogo.png',(50,50)),
 'Wide310x150Logo.scale-200.png':('msix_compatibility/Wide310x150Logo.png',(620,300)),
 'SplashScreen.scale-200.png':('msix_compatibility/SplashScreen_620x300.png',(1240,600)),
 'LockScreenLogo.scale-200.png':('app_icon/aredoko_app_icon_64.png',(48,48))}

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
 manifest=json.loads((SOURCE/'asset_manifest.json').read_text(encoding='utf-8'))
 for entry in manifest['files']:
  relative=Path(entry['path'])
  if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unsafe asset path')
  file=SOURCE/relative
  if str(relative) in ('PREVIEW.png','CODEX_PROMPT.txt') or relative.parts[0]=='reference':continue
  if not file.is_file():raise ValueError('Missing retained source: '+str(relative))
  if file.stat().st_size!=entry['bytes']:raise ValueError('Source asset changed: '+str(relative))
 outputs={'AppIcon.ico':(SOURCE/'app_icon/aredoko_app_icon.ico').read_bytes()}
 for name,(source,size) in SIZES.items():
  with Image.open(SOURCE/source) as image:
   output=io.BytesIO();image.convert('RGBA').resize(size,Image.Resampling.LANCZOS).save(output,format='PNG');outputs[name]=output.getvalue()
 for state in ('searching','no_results','indexing','completed','error'):
  name=f'aredoko_state_{state}_512.png';outputs['Visual/'+name]=(SOURCE/'status'/name).read_bytes()
 name='aredoko_mascot_greeting_512.png';outputs['Visual/'+name]=(SOURCE/'mascot'/name).read_bytes()
 for name,raw in outputs.items():
  path=DEST/name
  if args.check:
   if not path.is_file() or path.read_bytes()!=raw:raise ValueError('Output differs: '+name)
  else:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
 print(json.dumps({'outputs':len(outputs),'check_only':args.check,'source_version':manifest['version']}))
if __name__=='__main__':main()
