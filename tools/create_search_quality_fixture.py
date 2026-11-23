"""Small generated sources with neutral names; relevance lives only in the manifest."""
import io
import struct
import wave
import zipfile
import zlib

def graphic(visual,width=180,height=240):
    color_name,shape=visual.split('-')
    color={'red':(220,30,30),'blue':(20,60,220),'green':(20,170,60),'yellow':(240,200,20)}[color_name]
    rows=[]
    for y in range(height):
        line=bytearray()
        for x in range(width):
            dx,dy=x-width/2,y-height/2
            inside=(dx*dx+dy*dy<=50*50 if shape=='circle' else
                    abs(dx)<=48 and abs(dy)<=48 if shape=='square' else
                    -55<=dy<=50 and abs(dx)<=(dy+55)*0.52)
            line.extend(color if inside else (255,255,255))
        rows.append(b'\0'+line)
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')

def create(directory,items):
    directory.mkdir(parents=True,exist_ok=False)
    for item in items:
        path=directory/item['file']
        if path.name!=item['file'] or not item['key']:raise ValueError('Flat fictional filenames required')
        if item['kind']=='image':path.write_bytes(graphic(item['visual']))
        elif item['kind']=='book':
            with zipfile.ZipFile(path,'w') as archive:
                info=zipfile.ZipInfo('page01.png',date_time=(2026,1,1,0,0,0))
                archive.writestr(info,graphic(item['visual']))
        elif item['kind']=='audio':
            data=io.BytesIO()
            with wave.open(data,'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(8000);wav.writeframes(b'\0\0'*800)
            path.write_bytes(data.getvalue())
        elif item['kind']=='material':
            # Not a rendering of the assigned metadata; no SVG content embedding exists.
            path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="gray"/></svg>',encoding='utf-8')
        else:raise ValueError('Unknown fixture kind')
    return directory
