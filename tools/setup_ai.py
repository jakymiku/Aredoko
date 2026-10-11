"""Project-local AI setup with a shared downstream bandwidth cap."""
import argparse
import contextlib
import os
import select
import socket
import socketserver
import subprocess
import threading
import time
from pathlib import Path

class RateGate:
    def __init__(self, rate):
        self.rate = rate
        self.next = time.monotonic()
        self.lock = threading.Lock()
        self.bytes = 0
    def wait(self, count):
        with self.lock:
            now = time.monotonic()
            self.next = max(now, self.next) + count / self.rate
            delay = self.next - now
            self.bytes += count
        if delay > 0:
            time.sleep(delay)

class ThrottledProxy(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    def __init__(self, rate):
        self.gate = RateGate(rate)
        super().__init__(('127.0.0.1', 0), Tunnel)

class Tunnel(socketserver.BaseRequestHandler):
    def handle(self):
        upstream = None
        try:
            header = b''
            self.request.settimeout(30)
            while b'\r\n\r\n' not in header:
                part = self.request.recv(1)
                if not part or len(header) >= 8192:
                    return
                header += part
            verb, target, _ = header.split(b'\r\n',1)[0].decode('ascii').split(' ',2)
            host, port = target.rsplit(':',1)
            host = host.lower()
            approved = ('pypi.org','pythonhosted.org','pytorch.org','huggingface.co','hf.co')
            if verb != 'CONNECT' or port != '443' or not any(host == x or host.endswith('.'+x) for x in approved):
                self.request.sendall(b'HTTP/1.1 403 Forbidden\r\n\r\n')
                return
            upstream = socket.create_connection((host,443),timeout=30)
            self.request.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            self.request.settimeout(60)
            upstream.settimeout(60)
            while True:
                ready,_,_ = select.select([self.request,upstream],[],[],60)
                if not ready:
                    return
                for source in ready:
                    packet = source.recv(32768)
                    if not packet:
                        return
                    if source is upstream:
                        self.server.gate.wait(len(packet))
                        self.request.sendall(packet)
                    else:
                        upstream.sendall(packet)
        except (OSError, ValueError, UnicodeError):
            pass
        finally:
            if upstream:
                upstream.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rate',type=int,default=6_000_000)
    args = parser.parse_args()
    if not 1_000_000 <= args.rate <= 6_000_000:
        parser.error('Rate must be 1 to 6 million bytes/s')
    repo = Path(__file__).resolve().parents[1]
    python = repo / '.venv-ai/Scripts/python.exe'
    if not python.is_file():
        subprocess.run(['py','-3.11','-m','venv',str(repo/'.venv-ai')],check=True)
    proxy = ThrottledProxy(args.rate)
    thread = threading.Thread(target=proxy.serve_forever,daemon=True)
    thread.start()
    env = os.environ.copy()
    address = f'http://127.0.0.1:{proxy.server_address[1]}'
    env.update(HTTPS_PROXY=address,HTTP_PROXY=address,ALL_PROXY=address,NO_PROXY='',
               HF_HUB_DISABLE_XET='1',HF_HUB_ENABLE_HF_TRANSFER='0',
               HF_HUB_DISABLE_TELEMETRY='1',PIP_DISABLE_PIP_VERSION_CHECK='1')
    started = time.monotonic()
    print(f'All AI package/model HTTPS downloads share cap {args.rate/1_000_000:.1f} MB/s',flush=True)
    try:
        subprocess.run([str(python),'-m','pip','install','torch==2.9.1','torchvision==0.24.1',
                        '--index-url','https://download.pytorch.org/whl/cu128'],env=env,check=True,cwd=repo)
        subprocess.run([str(python),'-m','pip','install','sentence-transformers==6.1.0',
                        'transformers==5.19.0','Pillow>=11,<13'],env=env,check=True,cwd=repo)
        subprocess.run([str(python),str(repo/'tools/download-ai-model.py')],env=env,check=True,cwd=repo)
        with (repo/'models/ai-environment.txt').open('w',encoding='utf-8') as output:
            subprocess.run([str(python),'-m','pip','freeze'],stdout=output,env=env,check=True)
    finally:
        proxy.shutdown()
        proxy.server_close()
        print(f'Throttled TLS bytes: {proxy.gate.bytes}; elapsed: {time.monotonic()-started:.1f}s',flush=True)

if __name__ == '__main__':
    main()

