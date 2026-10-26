"""Close accepted loopback connections before backend-owned resources exit."""
from http.server import ThreadingHTTPServer
import socket
import threading


class OwnedHTTPServer(ThreadingHTTPServer):
    def __init__(self, *args, **kwargs):
        self._connection_lock=threading.Lock()
        self._connections=set()
        self._closing_connections=False
        super().__init__(*args,**kwargs)

    def get_request(self):
        connection,address=super().get_request()
        with self._connection_lock:
            if self._closing_connections:
                connection.close()
                raise OSError('HTTP owner closed')
            self._connections.add(connection)
        return connection,address

    def shutdown_request(self, request):
        try:super().shutdown_request(request)
        finally:
            with self._connection_lock:self._connections.discard(request)

    def server_close(self):
        with self._connection_lock:
            self._closing_connections=True
            connections=tuple(self._connections);self._connections.clear()
        super().server_close()
        for connection in connections:
            try:connection.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            connection.close()
