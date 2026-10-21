"""Header routing, authenticated probes and unchanged media guards; no GPU/UI."""
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from image_animations import image_mime, AnimationUnavailable
from previews import PreviewReader, PreviewUnavailable, ReaderChanged
from production import ProductionCatalog
from production_server import production_handler, DisabledAI
from PIL import Image


def animation(kind):
    output=io.BytesIO()
    Image.new('RGBA',(24,16),'red').save(output,format=kind,save_all=True,
        append_images=[Image.new('RGBA',(24,16),'blue')],duration=[80,120],loop=0)
    return output.getvalue()


class ImageFormatTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.media=self.base/'media';self.media.mkdir()
        self.catalog=ProductionCatalog(self.base/'catalog.sqlite')
        self.root=self.catalog.add_root(str(self.media));self.reader=PreviewReader(self.catalog)

    def tearDown(self):
        self.catalog.close();self.temp.cleanup()

    def add(self,name,data):
        source=self.media/name;source.write_bytes(data)
        self.catalog.index.scan(self.root);self.catalog.sync_index()
        item=next(r['id'] for r in self.catalog.search()['items'] if r['title']==name)
        return source,item

    def test_renamed_webp_routes_as_webp_without_frame_enumeration(self):
        source,item=self.add('renamed.gif',animation('WEBP'))
        before=(source.read_bytes(),source.stat().st_mtime_ns)
        # Cheap probe must not force Pillow or enumerate/decode frames.
        with patch('PIL.Image.open',side_effect=AssertionError('Unexpected decode')):
            info=self.reader.image_info(item)
        self.assertEqual(info['mime'],'image/webp');self.assertTrue(info['animation_candidate'])
        self.assertEqual(self.reader.read_original(item),(before[0],'image/webp'))
        manifest=self.reader.image_manifest(item)
        self.assertEqual(manifest['mime'],'image/webp');self.assertEqual(manifest['frame_count'],2)
        for frame,channel in ((0,0),(1,2)):
            data,mime=self.reader.image_frame(item,frame,manifest['revision'])
            self.assertEqual(mime,'image/png')
            with Image.open(io.BytesIO(data)) as image:self.assertGreater(image.getpixel((10,10))[channel],200)
        self.assertEqual(before,(source.read_bytes(),source.stat().st_mtime_ns))

    def test_renamed_gif_and_static_png_have_actual_mime(self):
        _,gif=self.add('renamed.png',animation('GIF'))
        self.assertEqual(self.reader.image_info(gif)['mime'],'image/gif')
        self.assertTrue(self.reader.image_info(gif)['animation_candidate'])
        output=io.BytesIO();Image.new('RGB',(8,8),'green').save(output,format='PNG')
        _,png=self.add('static.gif',output.getvalue())
        self.assertEqual(self.reader.image_info(png)['mime'],'image/png')
        self.assertFalse(self.reader.image_info(png)['animation_candidate'])
        self.assertEqual(self.reader.read(png)[1],'image/png')

    def test_probe_is_not_permission_or_freshness_cache(self):
        source,item=self.add('sample.gif',animation('WEBP'))
        self.reader.image_info(item)
        self.catalog.set_excludes(self.root,['*.gif'])
        with self.assertRaises(PreviewUnavailable):self.reader.image_info(item)
        self.catalog.set_excludes(self.root,[])
        source.write_bytes(source.read_bytes()+b'changed')
        with self.assertRaises(ReaderChanged):self.reader.image_info(item)

    def test_unregistered_root_after_probe_is_rejected(self):
        _,item=self.add('sample.gif',animation('WEBP'))
        self.reader.image_info(item)
        self.catalog.unregister_root(self.root)
        with self.assertRaises(PreviewUnavailable):self.reader.image_info(item)

    def test_signatures_and_invalid_container(self):
        for data,mime in ((b'GIF89a','image/gif'),(b'\x89PNG\r\n\x1a\n','image/png'),
                          (b'RIFF\x00\x00\x00\x00WEBP','image/webp'),
                          (b'\xff\xd8\xff\xe0','image/jpeg'),(b'BM','image/bmp')):
            self.assertEqual(image_mime(data),mime)
        for invalid in (b'',b'GIF89',b'RIFF1234WAVE',b'<html>'):
            with self.assertRaises(AnimationUnavailable):image_mime(invalid)
        _,item=self.add('corrupt.gif',b'<html>not an image')
        with self.assertRaises(PreviewUnavailable):self.reader.image_info(item)

    def test_info_route_auth_query_and_unregistered_root(self):
        _,item=self.add('sample.gif',animation('WEBP'))
        handler=production_handler(self.catalog,'fixture',ai=DisabledAI())
        handler.log_message=lambda *args:None
        server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        thread=threading.Thread(target=server.serve_forever);thread.start()
        def get(route,token='fixture'):
            return urllib.request.urlopen(urllib.request.Request(
                f'http://127.0.0.1:{server.server_port}'+route,headers={'X-Aredoko-Token':token}),timeout=5)
        route=f'/api/library/preview/{item}/info'
        try:
            with get(route) as response:self.assertEqual(json.load(response)['mime'],'image/webp')
            for suffix,token,expected in (('', 'wrong',403),('?revision=x','fixture',400)):
                with self.assertRaises(urllib.error.HTTPError) as error:get(route+suffix,token)
                self.assertEqual(error.exception.code,expected);error.exception.close()
            self.catalog.unregister_root(self.root)
            with self.assertRaises(urllib.error.HTTPError) as error:get(route)
            self.assertEqual(error.exception.code,404);error.exception.close()
        finally:
            server.shutdown();server.server_close();thread.join(5);handler.setup_jobs.close()


if __name__=='__main__':unittest.main()
