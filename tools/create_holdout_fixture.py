"""Deterministic geometric PNG/CBZ pixels and explicitly metadata-only SVG/WAV."""
import struct,zlib
from pathlib import Path
from create_search_quality_fixture import create as legacy_create
COLORS={'white':(255,255,255),'orange':(240,125,20),'purple':(140,50,190),'black':(10,10,10),'cyan':(60,210,230),'red':(220,30,30),'blue':(20,60,220),'green':(20,170,60),'yellow':(240,200,20)}
def graphic(scene,width=180,height=240):
    rows=[]
    for y in range(height):
        line=bytearray()
        for x in range(width):
            color=COLORS[scene['background']]
            for item in scene['objects']:
                dx,dy=x-item['x'],y-item['y'];sx,sy=item['sx'],item['sy'];shape=item['shape']
                if shape=='circle':inside=(dx/sx)**2+(dy/sy)**2<=1
                elif shape in ('rectangle','square'):inside=abs(dx)<=sx and abs(dy)<=sy
                elif shape=='diamond':inside=abs(dx)/sx+abs(dy)/sy<=1
                elif shape=='cross':inside=(abs(dx)<=sx/3 and abs(dy)<=sy) or (abs(dx)<=sx and abs(dy)<=sy/3)
                elif shape=='triangle':inside=-sy<=dy<=sy and abs(dx)<=sx*(dy+sy)/(2*sy)
                else:raise ValueError('Unknown bounded fixture shape')
                if inside:color=COLORS[item['color']]
            line.extend(color)
        rows.append(b'\0'+line)
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')
def create(directory,items):
    import zipfile
    # Metadata-only formats retain v1's actual minimal gray SVG/silent WAV.
    legacy_create(directory,[item for item in items if item['kind'] not in ('image','book')])
    for item in items:
        if item['kind'] not in ('image','book'):continue
        if item['file']!=Path(item['file']).name:raise ValueError('Flat fictional filenames required')
        data=graphic(item['scene']);path=directory/item['file']
        if item['kind']=='image':path.write_bytes(data)
        else:
            with zipfile.ZipFile(path,'w') as archive:archive.writestr(zipfile.ZipInfo('page01.png',date_time=(2026,1,1,0,0,0)),data)
    return directory
