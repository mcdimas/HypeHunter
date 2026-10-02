"""Default tests must never spend provider credits, send email or issue receipts."""
import socket
import os
from urllib.parse import urlsplit
import pytest

# PostgreSQL tests create records and schemas: never accept a production URL.
for name in ['DATABASE_URL','AUTH_PG_TEST_URL']:
    value=os.getenv(name,'')
    if value.startswith('postgresql'):
        url=urlsplit(value)
        database=url.path.lstrip('/')
        if url.hostname not in {'127.0.0.1','localhost','::1'} or not (database.endswith('_test') or database.startswith('test_')):
            raise RuntimeError('Tests require a loopback PostgreSQL database explicitly named *_test or test_*')

@pytest.fixture(autouse=True)
def forbid_external_network(monkeypatch):
    connect=socket.socket.connect
    lookup=socket.getaddrinfo
    def safe_connect(sock,address):
        if isinstance(address,tuple) and address[0] not in {'127.0.0.1','::1','localhost'}:
            raise AssertionError('External network is forbidden in the default test suite')
        return connect(sock,address)
    monkeypatch.setattr(socket.socket,'connect',safe_connect)
    def safe_lookup(host,*args,**kwargs):
        if host not in {'127.0.0.1','::1','localhost',None}:
            raise AssertionError('External DNS is forbidden in the default test suite')
        return lookup(host,*args,**kwargs)
    monkeypatch.setattr(socket,'getaddrinfo',safe_lookup)
