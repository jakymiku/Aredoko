"""Bounded, ephemeral one-use search capabilities. No catalog/media writes."""
from contextlib import contextmanager
import re
import secrets
import threading
import time

class SearchRequestConflict(RuntimeError): pass

class SearchRequests:
    # Unclaimed reservations expire; running requests never expire/release ownership.
    def __init__(self, capacity=32, ttl=60, clock=time.monotonic):
        self._lock=threading.Lock();self._entries={};self._closed=False
        self._capacity=capacity;self._ttl=ttl;self._clock=clock

    @staticmethod
    def validate(request_id):
        if not isinstance(request_id,str) or re.fullmatch('[0-9a-f]{32}',request_id) is None:
            raise ValueError('Invalid search request ID')

    def prepare(self):
        with self._lock:
            if self._closed:raise SearchRequestConflict('Search service is closing')
            now=self._clock()
            self._entries={key:value for key,value in self._entries.items()
                           if value['running'] or value['expires']>now}
            if len(self._entries)>=self._capacity:raise SearchRequestConflict('Too many search reservations')
            request_id=secrets.token_hex(16)
            while request_id in self._entries:request_id=secrets.token_hex(16)
            self._entries[request_id]={'running':False,'expires':now+self._ttl,'cancelled':threading.Event()}
            return {'request_id':request_id,'expires_in_seconds':self._ttl}

    @contextmanager
    def claim(self,request_id):
        self.validate(request_id)
        with self._lock:
            entry=self._entries.get(request_id)
            if self._closed or entry is None or entry['running'] or entry['expires']<=self._clock():
                raise SearchRequestConflict('Search reservation unavailable')
            entry['running']=True
        try:yield entry['cancelled'].is_set
        finally:
            with self._lock:
                if self._entries.get(request_id) is entry:del self._entries[request_id]

    def cancel(self,request_id):
        self.validate(request_id)
        with self._lock:
            entry=self._entries.get(request_id)
            accepted=entry is not None and (entry['running'] or entry['expires']>self._clock()) and not self._closed
            if accepted:
                entry['cancelled'].set()
                # Cancel-before-start cannot later be resurrected by a delayed POST.
                if not entry['running']:del self._entries[request_id]
            return {'request_id':request_id,'cancel_requested':accepted}

    def close(self):
        with self._lock:
            self._closed=True
            for entry in self._entries.values():entry['cancelled'].set()
            self._entries.clear()
