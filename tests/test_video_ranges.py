import unittest,json,urllib.request,urllib.error,threading,os
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import test_video_previews as fixtures
from production_server import production_handler,DisabledAI
from previews import PreviewUnavailable,PreviewBusyError,ReaderChanged,VideoRangeUnsatisfiable,MAX_VIDEO_RANGE_BYTES

class VideoRangeTests(unittest.TestCase):
    setUp=fixtures.VideoBoundaryTests.setUp
    scan=fixtures.VideoBoundaryTests.scan
    def manifest(self):return self.reader.video_manifest(self.item)
    def test_large_sparse_source_tail_and_eof_readonly(self):
        with self.path.open('r+b') as f:f.truncate(70*1024*1024);f.seek(-3,2);f.write(b'end')
        self.scan();before=self.path.stat().st_size,self.path.stat().st_mtime_ns;m=self.manifest()
        self.assertEqual(m['size_bytes'],70*1024*1024)
        self.assertEqual(self.reader.video_range(self.item,m['size_bytes']-3,m['size_bytes']-1,m['revision']), (b'end','video/mp4',m['size_bytes']))
        with self.assertRaises(VideoRangeUnsatisfiable):self.reader.video_range(self.item,m['size_bytes'],m['size_bytes'],m['revision'])
        self.assertEqual(before,(self.path.stat().st_size,self.path.stat().st_mtime_ns))
        with self.assertRaises(PreviewUnavailable):self.reader.read_video(self.item)
    def test_bounded_input_and_busy_release(self):
        m=self.manifest()
        for start,end,revision in [(True,4,m['revision']),(-1,3,m['revision']),(3,2,m['revision']),(0,MAX_VIDEO_RANGE_BYTES,m['revision']),(0,3,'x'*64)]:
            with self.assertRaises(ValueError):self.reader.video_range(self.item,start,end,revision)
        self.reader.slots.acquire();self.reader.slots.acquire()
        try:
            with self.assertRaises(PreviewBusyError):self.manifest()
        finally:self.reader.slots.release();self.reader.slots.release()
        self.assertEqual(self.reader.video_range(self.item,0,2,m['revision'])[0],b'gen')
    def test_changed_revision_rescan_and_old_token_rejected(self):
        old=self.manifest();self.path.write_bytes(b'changed generated video')
        with self.assertRaises(ReaderChanged):self.reader.video_range(self.item,0,2,old['revision'])
        self.scan();new=self.manifest();self.assertNotEqual(old['revision'],new['revision'])
        with self.assertRaises(ReaderChanged):self.reader.video_range(self.item,0,2,old['revision'])
        self.assertEqual(self.reader.video_range(self.item,0,2,new['revision'])[0],b'cha')
    def test_playlist_excluded_unregistered_and_nonvideo(self):
        for body in [b'  #EXTM3U\nhttp://example.com',b'[playlist]\nFile1=example',b'<ASX>fiction',b' '*600]:
            self.path.write_bytes(body);self.scan()
            with self.assertRaises(PreviewUnavailable):self.manifest()
        self.path.write_bytes(b'generated source');self.scan();self.catalog.set_excludes(self.root,['*.mp4'])
        with self.assertRaises(PreviewUnavailable):self.manifest()
        self.catalog.set_excludes(self.root,[]);self.catalog.unregister_root(self.root)
        with self.assertRaises(PreviewUnavailable):self.manifest()
    def test_http_auth_ranges_headers_and_legacy(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(self.catalog,'range-token',ai=DisabledAI()));t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
        self.addCleanup(server.server_close);self.addCleanup(t.join,5);self.addCleanup(server.shutdown)
        base=f'http://127.0.0.1:{server.server_port}';prefix=f'/api/library/video/{self.item}'
        def request(route,span=None,token='range-token',host=None):
            headers={'X-Aredoko-Token':token}
            if span is not None:headers['Range']=span
            if host:headers['Host']=host
            try:
                with urllib.request.urlopen(urllib.request.Request(base+route,headers=headers)) as resp:return resp.status,resp.read(),dict(resp.headers)
            except urllib.error.HTTPError as ex:
                with ex:return ex.code,ex.read(),dict(ex.headers)
        self.assertEqual(request(prefix+'/manifest',token='wrong')[0],403);self.assertEqual(request(prefix+'/manifest',host='example.com')[0],403)
        m=json.loads(request(prefix+'/manifest')[1]);route=prefix+'/range?revision='+m['revision'];code,data,headers=request(route,'bytes=0-8')
        self.assertEqual((code,data),(206,b'generated'));self.assertEqual(headers['Content-Range'],f"bytes 0-8/{m['size_bytes']}");self.assertEqual(headers['ETag'],'"'+m['revision']+'"');self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(request(route,token='wrong',span='bytes=0-8')[0],403)
        for span in [None,'bytes=0-','bytes=-8','bytes=00-8','bytes=0-8,10-12','bytes=8-0','bytes=0-1048576']:
            self.assertEqual(request(route,span)[0],400,span)
        self.assertEqual(request(route,'bytes=999-1000')[0],416)
        self.assertEqual(request(route+'&revision='+m['revision'],'bytes=0-8')[0],400)
        self.assertEqual(request(prefix+'/manifest?path=x')[0],400)
        self.assertEqual(request(prefix)[0],200)
        self.assertEqual(request(prefix+'/range?revision='+'a'*64,'bytes=0-8')[0],409)

if __name__=='__main__':unittest.main()
