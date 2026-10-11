"""Production-only loopback endpoint. No demo data or source-media writes."""
import argparse
import json
import secrets
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse
from production import ProductionCatalog
from server import handler_for

def production_handler(catalog,token):
    base=handler_for(catalog,token)
    class Handler(base):
        def do_GET(self):
            if not self.valid_host(): return self.send(403,{'error':'Invalid host'})
            path=urlparse(self.path).path
            if path=='/api/session':
                return self.send(200,{'mode':'production','token':token,'stats':catalog.stats()})
            # Native client supplies the session token for library-specific reads.
            if path.startswith('/api/library'):
                if self.headers.get('X-Aredoko-Token')!=token:
                    return self.send(403,{'error':'Invalid session'})
                if path=='/api/library/roots': return self.send(200,{'items':catalog.index.roots()})
                if path=='/api/library/scan': return self.send(200,catalog.scan_state())
                return self.send(404,{'error':'Not found'})
            return super().do_GET()

        def do_POST(self):
            if not self.path.startswith('/api/library/'):
                return super().do_POST()
            origin=f'http://127.0.0.1:{self.server.server_port}'
            if not self.valid_host() or self.headers.get('Origin')!=origin or self.headers.get('X-Aredoko-Token')!=token:
                return self.send(403,{'error':'Invalid session'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=32768: return self.send(413,{'error':'Invalid body size'})
                body=json.loads(self.rfile.read(length))
                if not isinstance(body,dict): raise ValueError('Expected an object')
                if self.path=='/api/library/roots':
                    if body.get('consent') is not True: raise ValueError('Explicit folder consent required')
                    return self.send(200,{'root_id':catalog.add_root(body.get('path'),body.get('excludes'))})
                if self.path=='/api/library/excludes':
                    # Avoid racing the index transaction while scanning.
                    if catalog._worker and catalog._worker.is_alive(): raise ValueError('Wait for the scan to finish')
                    return self.send(200,{'excludes':catalog.index.set_excludes(body.get('root_id'),body.get('patterns'))})
                if self.path=='/api/library/scan': return self.send(200,catalog.start_scan(body.get('root_id')))
                if self.path=='/api/library/cancel': return self.send(200,catalog.cancel_scan())
                return self.send(404,{'error':'Not found'})
            except (ValueError,TypeError): return self.send(400,{'error':'Invalid request: check folder, exclusions or scan state'})
            except KeyError: return self.send(404,{'error':'Root not found'})
            except OSError: return self.send(409,{'error':'Folder unavailable; records preserved'})
    return Handler

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8769)
    args=parser.parse_args()
    catalog=ProductionCatalog(args.db)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),production_handler(catalog,secrets.token_urlsafe(32)))
    print(f'Aredoko production: http://127.0.0.1:{server.server_port}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: catalog.close(); server.server_close()

if __name__=='__main__': main()
