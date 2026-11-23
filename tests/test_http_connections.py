"""Persistent loopback framing, per-request guards and owned socket shutdown."""
import http.client
import json
import io
from pathlib import Path
import sys
import tempfile
import threading
import struct
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tools')]
from production import ProductionCatalog
from production_server import production_handler,DisabledAI
from owned_http_server import OwnedHTTPServer
from ai_settings import AIProfileSettings
from wd_tagger import DisabledTagger
from create_preview_fixture import png


class HTTPConnectionTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);base=Path(temporary.name)
        media=base/'media';media.mkdir();self.data=png(24,24);(media/'generated.png').write_bytes(self.data)
        self.cat=ProductionCatalog(base/'catalog.sqlite');self.addCleanup(self.cat.close)
        self.root=self.cat.add_root(str(media));self.cat.index.scan(self.root);self.cat.sync_index()
        self.item=self.cat.search()['items'][0]['id'];self.sid='a'*32
        profiles=AIProfileSettings(ROOT,base/'ai-settings.json',profile_directory=base/'profiles',ai_python=str(base/'missing-python'),models_root=base/'missing-models')
        self.handler=production_handler(self.cat,'fixture',ai=DisabledAI(),tagger=DisabledTagger(),profiles=profiles,runtime_preferences=base/'launch-settings.json')
        self.handler.log_message=lambda *args:None
        self.server=OwnedHTTPServer(('127.0.0.1',0),self.handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        def close():
            self.server.shutdown();self.server.server_close();self.thread.join(3)
            for resource in (self.handler.startup_scans,self.handler.thumbnails,self.handler.results,self.handler.animations,
                             self.handler.setup_jobs,self.handler.download_jobs,self.handler.backup_jobs,self.handler.restore_jobs):resource.close()
        self.addCleanup(close)
        self.headers={'Origin':f'http://127.0.0.1:{self.server.server_port}','X-Aredoko-Token':'fixture','Content-Type':'application/json'}
        self.info=f'/api/library/preview/{self.item}/info';self.original=f'/api/library/preview/{self.item}/original'

    def connection(self):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        self.addCleanup(connection.close);return connection

    def read(self,connection,path,body=None,headers=None):
        connection.request('GET' if body is None else 'POST',path,None if body is None else json.dumps(body),headers or self.headers)
        response=connection.getresponse()
        try:return response.status,response.getheader('Connection'),response.read()
        finally:response.close()

    def create(self,connection):
        status,policy,_=self.read(connection,'/api/library/results/create',{'session_id':self.sid,'conditions':{'mode':'literal'}})
        self.assertEqual((status,policy),(200,'close'))

    def test_image_reads_reuse_socket_and_recheck_authentication(self):
        connection=self.connection();status,policy,_=self.read(connection,self.info)
        self.assertEqual((status,policy),(200,'keep-alive'));socket=connection.sock
        status,policy,data=self.read(connection,self.original)
        self.assertEqual((status,policy,data),(200,'keep-alive',self.data));self.assertIs(connection.sock,socket)
        status,policy,data=self.read(connection,self.original,headers={**self.headers,'X-Aredoko-Token':'bad'})
        self.assertEqual((status,policy),(403,'close'));self.assertFalse(data.startswith(b'\x89PNG'))

    def test_kept_socket_does_not_cache_root_access(self):
        connection=self.connection();self.assertEqual(self.read(connection,self.info)[0],200)
        self.cat.unregister_root(self.root)
        status,policy,data=self.read(connection,self.original)
        self.assertIn(status,(404,409));self.assertEqual(policy,'close');self.assertFalse(data.startswith(b'\x89PNG'))

    def test_range_status_reuse_but_creation_and_close_keep_control_policy(self):
        connection=self.connection();self.create(connection)
        status,policy,_=self.read(connection,'/api/library/results/range',{'session_id':self.sid,'offset':0,'limit':1})
        self.assertEqual((status,policy),(200,'keep-alive'));socket=connection.sock
        status,policy,body=self.read(connection,'/api/library/results/status',{'session_id':self.sid})
        self.assertEqual((status,policy),(200,'keep-alive'));self.assertIs(connection.sock,socket)
        self.assertNotIn('items',json.loads(body))
        self.assertEqual(self.read(connection,'/api/library/results/close',{'session_id':self.sid})[:2],(200,'close'))

    def test_duplicate_length_transfer_encoding_and_client_close_do_not_reuse(self):
        connection=self.connection();self.create(connection)
        body=json.dumps({'session_id':self.sid}).encode()
        connection.putrequest('POST','/api/library/results/status')
        for name,value in self.headers.items():connection.putheader(name,value)
        connection.putheader('Content-Length',str(len(body)));connection.putheader('Content-Length',str(len(body)))
        connection.endheaders(body);response=connection.getresponse()
        try:self.assertEqual((response.status,response.getheader('Connection')),(200,'close'));response.read()
        finally:response.close()
        self.assertEqual(self.read(connection,self.info,headers={**self.headers,'Transfer-Encoding':'identity'})[:2],(200,'close'))
        self.assertEqual(self.read(connection,self.info,headers={**self.headers,'Connection':'close'})[:2],(200,'close'))

    def test_connection_request_budget_and_idle_timeout(self):
        self.handler.max_api_responses=2
        connection=self.connection();self.assertEqual(self.read(connection,self.info)[:2],(200,'keep-alive'))
        self.assertEqual(self.read(connection,self.info)[:2],(200,'close'))
        self.handler.max_connection_seconds=0
        self.assertEqual(self.read(self.connection(),self.info)[:2],(200,'close'))
        self.handler.max_connection_seconds=300
        self.handler.timeout=.1
        connection=self.connection();self.assertEqual(self.read(connection,self.info)[0],200)
        connection.sock.settimeout(2);self.assertEqual(connection.sock.recv(1),b'')

    def test_binary_animation_reuses_connection_and_revocation_still_closes_it(self):
        from PIL import Image
        frames=[Image.new('RGBA',(64,32),(50+i*50,100,160,255)) for i in range(3)]
        output=io.BytesIO()
        try:frames[0].save(output,format='PNG',save_all=True,append_images=frames[1:],duration=80,loop=1)
        finally:
            for frame in frames:frame.close()
        with self.cat.connect() as db:media=Path(db.execute('SELECT path FROM library_roots WHERE id=?',(self.root,)).fetchone()[0])
        (media/'animated.png').write_bytes(output.getvalue());self.cat.index.scan(self.root);self.cat.sync_index()
        item=self.cat.search('animated.png')['items'][0]['id'];connection=self.connection()
        info=json.loads(self.read(connection,f'/api/library/preview/{item}/info')[2]);socket=connection.sock
        status,policy,body=self.read(connection,'/api/library/animation/open-first',{'item_id':item,'revision':info['revision'],'session_id':'b'*32,'original_size':True})
        self.assertEqual((status,policy),(200,'keep-alive'));self.assertIs(connection.sock,socket)
        length=struct.unpack_from('<I',body)[0];header=json.loads(body[4:4+length]);self.assertEqual(header['frames'][0]['sequence'],0)
        status,policy,body=self.read(connection,'/api/library/animation/next',{'session_id':'b'*32,'count':1})
        self.assertEqual((status,policy),(200,'keep-alive'));self.assertIs(connection.sock,socket)
        self.cat.unregister_root(self.root)
        status,policy,body=self.read(connection,'/api/library/animation/next',{'session_id':'b'*32,'count':1})
        self.assertIn(status,(404,409));self.assertEqual(policy,'close');self.assertTrue(body.startswith(b'{'))

    def test_owner_close_disconnects_idle_clients_before_resources_close(self):
        connection=self.connection();self.assertEqual(self.read(connection,self.info)[1],'keep-alive')
        self.server.shutdown();self.server.server_close();self.thread.join(2)
        connection.sock.settimeout(2);self.assertEqual(connection.sock.recv(1),b'')
        self.assertFalse(self.thread.is_alive());self.assertEqual(self.server._connections,set())


if __name__=='__main__':unittest.main()
