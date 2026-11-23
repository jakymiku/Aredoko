"""Generate fictional PNG/CBZ sources for tests; requires no imaging dependency."""
import argparse
import struct
import zlib
import zipfile
from pathlib import Path

def png(width=180, height=240, color=(88,111,190)):
    def chunk(kind, data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    rows=[]
    for y in range(height):
        pixels=bytearray()
        for x in range(width):
            tone=color if y < height*0.35 or x < width*0.18 else tuple(min(255,v+55) for v in color)
            if width*0.3<x<width*0.8 and height*0.58<y<height*0.78:
                tone=(238,235,222)
            pixels.extend(tone)
        rows.append(b'\0'+bytes(pixels))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')

def create(directory):
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=False)
    colors=[(88,111,190),(73,133,111),(176,98,86),(148,97,165),(78,137,156),(173,135,64)]
    for i,color in enumerate(colors):
        (directory/f'image-{i+1:02}.png').write_bytes(png(color=color))
        with zipfile.ZipFile(directory/f'book-{i+1:02}.cbz','w') as archive:
            archive.writestr('page10.png',png(color=(210,180,50)))
            archive.writestr('page2.png',png(color=color))
    (directory/'broken.cbz').write_bytes(b'not a zip')
    (directory/'broken.png').write_bytes(b'not a png')
    (directory/'unavailable.pdf').write_bytes(b'fictional pdf')
    return directory

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    create(parser.parse_args().output)
