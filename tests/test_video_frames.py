import unittest,shutil,subprocess,hashlib,struct,zlib,json,urllib.request,urllib.error,threading
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import test_video_previews as fixtures
from production_server import production_handler,DisabledAI
from previews import PreviewUnavailable,ReaderChanged,PreviewBusyError
from create_preview_fixture import png

class VideoFrameTests(unittest.TestCase):
    setUp=fixtures.VideoBoundaryTests.setUp
    scan=fixtures.VideoBoundaryTests.scan
    def test_strict_input_revision_root_and_busy(self):
        m=self.reader.video_manifest(self.item)
        for at,rev in [(True,m['revision']),(-1,m['revision']),(86400001,m['revision']),(0,'bad')]:
            with self.assertRaises(ValueError):self.reader.video_frame(self.item,at,rev)
        with self.assertRaises(ReaderChanged):self.reader.video_frame(self.item,0,'a'*64)
        self.reader.slots.acquire();self.reader.slots.acquire()
        try:
            with self.assertRaises(PreviewBusyError):self.reader.video_frame(self.item,0,m['revision'])
        finally:self.reader.slots.release();self.reader.slots.release()
        self.catalog.set_excludes(self.root,['*.mp4'])
        with self.assertRaises(PreviewUnavailable):self.reader.video_frame(self.item,0,m['revision'])
        self.catalog.set_excludes(self.root,[]);self.catalog.unregister_root(self.root)
        with self.assertRaises(PreviewUnavailable):self.reader.video_frame(self.item,0,m['revision'])
    def test_http_frame_auth_query_and_revision(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(self.catalog,'frame-token',ai=DisabledAI()));t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
        self.addCleanup(server.server_close);self.addCleanup(t.join,5);self.addCleanup(server.shutdown)
        m=self.reader.video_manifest(self.item);route=f'http://127.0.0.1:{server.server_port}/api/library/video/{self.item}/frame?revision='+m['revision']+'&at_ms=1000'
        def get(url,token='frame-token'):
            try:
                with urllib.request.urlopen(urllib.request.Request(url,headers={'X-Aredoko-Token':token})) as resp:return resp.status,resp.read(),resp.headers
            except urllib.error.HTTPError as ex:
                with ex:return ex.code,ex.read(),ex.headers
        self.assertEqual(get(route,'wrong')[0],403)
        with patch('video_previews.VideoThumbnailer.read',return_value=png()) as read:
            code,data,headers=get(route);self.assertEqual(code,200);self.assertEqual(data,png());self.assertEqual(headers['Content-Type'],'image/png');self.assertEqual(headers['Cache-Control'],'no-store');self.assertEqual(read.call_args.kwargs['at_ms'],1000)
        for suffix in ['-1','true','1000.0','0001','86400001']:
            self.assertEqual(get(route.rsplit('=',1)[0]+'='+suffix)[0],400)
        self.assertEqual(get(route+'&at_ms=1000')[0],400);self.assertEqual(get(route+'&path=else')[0],400);self.assertEqual(get(route.replace(m['revision'],'a'*64))[0],409)
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg tools unavailable')
    def test_native_red_then_blue_frame_cache_and_readonly(self):
        subprocess.run([shutil.which('ffmpeg'),'-nostdin','-v','error','-y','-f','lavfi','-i','color=c=red:s=320x180:d=1[r];color=c=blue:s=320x180:d=1[b];[r][b]concat=n=2:v=1:a=0','-threads','1','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(self.path)],check=True,timeout=15)
        self.scan();before=hashlib.sha256(self.path.read_bytes()).hexdigest(),self.path.stat().st_mtime_ns;m=self.reader.video_manifest(self.item)
        def pixel(data):
            packed=b'';pos=8
            while pos<len(data):
                length=struct.unpack_from('>I',data,pos)[0]
                if data[pos+4:pos+8]==b'IDAT':packed+=data[pos+8:pos+8+length]
                pos+=length+12
            return zlib.decompress(packed)[1:4]
        red=self.reader.video_frame(self.item,0,m['revision'])[0];blue=self.reader.video_frame(self.item,1000,m['revision'])[0]
        self.assertGreater(pixel(red)[0],240);self.assertGreater(pixel(blue)[2],240);self.assertLess(pixel(blue)[0],10)
        with patch('video_previews._run',side_effect=AssertionError('cached frame spawned a process')):
            self.assertEqual(self.reader.video_frame(self.item,1000,m['revision'])[0],blue)
        self.assertEqual(before,(hashlib.sha256(self.path.read_bytes()).hexdigest(),self.path.stat().st_mtime_ns))

if __name__=='__main__':unittest.main()
