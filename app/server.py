"""Local-only UI prototype, using Python standard library only."""
import argparse
import json
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import time
from mimetypes import guess_type
from urllib.parse import parse_qs, urlparse
from catalog import Catalog

ROOT = Path(__file__).resolve().parents[1]


def handler_for(catalog, token, benchmark_dist=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, body, mime='application/json; charset=utf-8',extra_headers=None):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; connect-src 'self'")
            for name,value in (extra_headers or {}).items():self.send_header(name,value)
            self.end_headers()
            self.wfile.write(body)

        def reject_post(self, status, body):
            # Closing a Windows TCP socket with unread upload bytes can reset
            # it before the client receives our 403/413. Discard bounded bytes
            # without parsing or authorizing the rejected document. read1 plus
            # a total deadline prevents a slow/incomplete sender holding us.
            self.close_connection = True
            length = self.headers.get('Content-Length', '').strip()
            if length.isascii() and length.isdigit() and len(length) <= 8:
                remaining = min(int(length), 16 * 1024 * 1024)
                deadline = time.monotonic() + 1.0
                previous_timeout = self.connection.gettimeout()
                try:
                    while remaining and (left := deadline - time.monotonic()) > 0:
                        self.connection.settimeout(left)
                        chunk = self.rfile.read1(min(remaining, 64 * 1024))
                        if not chunk: break
                        remaining -= len(chunk)
                except (OSError, socket.timeout):
                    pass  # Still attempt the original rejection; no retry.
                finally:
                    self.connection.settimeout(previous_timeout)
            return self.send(status, body)

        def valid_host(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {'error': 'Invalid host'})
            url = urlparse(self.path)
            args = parse_qs(url.query)
            def param(key, default=''):
                return args.get(key, [default])[0]
            try:
                if url.path == '/api/session':
                    return self.send(200, {'token': token, 'mode': 'demo', 'stats': catalog.stats()})
                if url.path == '/api/items':
                    page = param('page', '0')
                    if not (page.isascii() and page.isdigit()) or len(page) > 9:
                        return self.send(400, {'error': 'Invalid paging'})
                    try:
                        return self.send(200, catalog.search(param('q'), param('kind'), param('view', 'all'), int(page)))
                    except ValueError as error:
                        # Search validation messages are fixed, user-facing
                        # strings (e.g. too many words); pass them through.
                        return self.send(400, {'error': str(error)})
                if url.path.startswith('/api/items/'):
                    return self.send(200, catalog.get(int(url.path.rsplit('/', 1)[1])))
                if benchmark_dist is not None and (url.path == '/bench/' or url.path.startswith('/bench/')):
                    # Optional, isolated React comparison fixture, served from the same origin as API.
                    relative = url.path.removeprefix('/bench/') or 'index.html'
                    base = Path(benchmark_dist).resolve()
                    asset = (base / relative).resolve()
                    if not asset.is_relative_to(base) or asset.suffix not in ('.html', '.css', '.js', '.svg'):
                        return self.send(404, {'error': 'Not found'})
                    if not asset.is_file():
                        return self.send(404, {'error': 'Benchmark frontend not built'})
                    mime = guess_type(asset)[0] or 'application/octet-stream'
                    return self.send(200, asset.read_bytes(), mime + '; charset=utf-8')
                assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                          '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                          '/style.css': ('style.css', 'text/css; charset=utf-8')}
                if url.path in assets:
                    filename, mime = assets[url.path]
                    return self.send(200, (ROOT / 'web' / filename).read_bytes(), mime)
                return self.send(404, {'error': 'Not found'})
            except (ValueError, TypeError):
                return self.send(400, {'error': 'Invalid request'})
            except KeyError:
                return self.send(404, {'error': 'Item not found'})

        def do_POST(self):
            origin = f'http://127.0.0.1:{self.server.server_port}'
            if not self.valid_host() or self.headers.get('Origin') != origin or self.headers.get('X-Aredoko-Token') != token:
                return self.reject_post(403, {'error': 'Invalid session'})
            if self.path != '/api/items/update':
                return self.send(404, {'error': 'Not found'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 32768:
                    return self.reject_post(413, {'error': 'Invalid body size'})
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('Expected an object')
                return self.send(200, catalog.update(body.get('ids'), body.get('changes')))
            except (ValueError, TypeError):
                return self.send(400, {'error': 'Invalid update'})
            except KeyError:
                return self.send(404, {'error': 'Item not found'})
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--benchmark-dist', type=Path, default=None,
                        help='Optional prebuilt React comparison UI; only exposed under /bench/')
    parser.add_argument('--db', type=Path, default=ROOT / 'data' / 'demo.sqlite',
                        help='SQLite path (dedicated temporary DB recommended for UI tests)')
    args = parser.parse_args()
    catalog = Catalog(args.db)
    catalog.seed()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(catalog, secrets.token_urlsafe(32), args.benchmark_dist))
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'Aredoko demo: {url}\nFictional data only. Ctrl+C to stop.', flush=True)
    if args.open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
