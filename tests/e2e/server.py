"""Loopback-only disposable real API. This file is NEVER imported by production.

No real env, keys, email, scraper, AI, payment or receipt service is used.
"""
import os
import sys
import socket
import uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['PUBLIC_ORIGIN'] = 'https://127.0.0.1:4174'
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import ipaddress

scratch = ROOT / 'work' / 'e2e'
scratch.mkdir(parents=True, exist_ok=True)
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
    .serial_number(x509.random_serial_number()).not_valid_before(datetime.now(timezone.utc)-timedelta(minutes=1))
    .not_valid_after(datetime.now(timezone.utc)+timedelta(days=1))
    .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),False)
    .sign(key,hashes.SHA256()))
(scratch/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
(scratch/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))

from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy import event
from sqlalchemy.orm.attributes import set_committed_value
from app.config import Settings, get_settings
from app import main, auth, api, email_auth, live_billing, translation
from app.database import get_session
from app.models import Reel
from app.apify_import import run_apify_import

engine = create_engine('sqlite:///'+str(scratch / (uuid.uuid4().hex+'.db')),connect_args={'check_same_thread':False})
SQLModel.metadata.create_all(engine)
# PostgreSQL returns timezone-aware UTC datetimes; SQLite drops the timezone.
# Restore it in this disposable harness so browser scheduling has production semantics.
def utc_fields(target,*args):
    for field,value in list(target.__dict__.items()):
        if isinstance(value,datetime) and value.tzinfo is None:
            set_committed_value(target,field,value.replace(tzinfo=timezone.utc))
for mapper in SQLModel._sa_registry.mappers:
    event.listen(mapper.class_,'load',utc_fields)
    event.listen(mapper.class_,'refresh',utc_fields)
settings = Settings(_env_file=None,database_url='sqlite://',media_root=scratch/'media',
    public_origin='https://127.0.0.1:4174',auth_code_secret='e2e-only-secret-never-used-in-production-123',
    telegram_bot_token='fake-token',telegram_bot_username='e2e_fake_bot',telegram_webhook_secret='e2e-fake-webhook',
    unisender_go_api_key='fake',email_from_address='noreply@example.test',
    apify_token='fake',openai_enabled=True,openai_api_key='fake',billing_enabled=True,
    yookassa_shop_id='e2e-shop',yookassa_secret_key='fake')
main.settings = settings
main.engine = auth.engine = engine
main.start_reconciliation = main.start_telegram_polling = lambda *args: None
def sessions():
    with Session(engine) as session: yield session
main.app.dependency_overrides[get_settings] = lambda: settings
main.app.dependency_overrides[get_session] = sessions
auth.get_settings = lambda: settings
mailbox = {}
email_auth.send_code = lambda config,email,code,challenge: mailbox.update({email:code})

class Source:
    def __init__(self, token): pass
    def actor(self, name): return self
    def start(self, **kwargs): return {'id':'fake-run'}
    def run(self, ident): return self
    def wait_for_finish(self, **kwargs): return {'status':'SUCCEEDED','defaultDatasetId':'fake-dataset'}
    def dataset(self, ident): return self
    def list_items(self, limit):
        return SimpleNamespace(items=[{'id':f'fixture-{i}','ownerUsername':'e2e_creator',
            'caption':f'Original hook {i}','transcript':f'Original script {i}. Subscribe.',
            'timestamp':'2026-09-25T12:00:00Z','videoPlayCount':i*1000} for i in range(12)])
def fake_translation(**kwargs):
    # Browser tests test persistence/rendering, not model quality. API contracts
    # and source/draft preservation are covered by test_translation.py.
    with Session(engine) as session:
        for ident in kwargs['only_ids']:
            reel=session.get(Reel,ident)
            reel.translated_hook='Переведённый хук'
            reel.translated_script='Переведённый сценарий'
            reel.translated_cta='Подпишитесь'
            reel.translation_status='completed'
            session.add(reel)
        session.commit()
translation.run_translation_backfill = fake_translation
api.run_apify_import = lambda job_id, **kwargs: run_apify_import(job_id,settings_override=settings,
    session_factory=lambda:Session(engine),client_factory=Source,
    profile_fetcher=lambda *args:(None,{}),avatar_cache=lambda *args:None,thumbnail_cache=lambda *args:None)
remote = {}
def provider(config,method,path,payload=None,key=None):
    if method=='POST':
        assert payload['save_payment_method'] is False
        ident='e2e-'+key
        remote[ident]={'id':ident,'test':False,'paid':False,'status':'pending','amount':payload['amount'],
            'metadata':payload['metadata'],'recipient':{'account_id':'e2e-shop'},
            'confirmation':{'confirmation_url':'https://yoomoney.ru/checkout/e2e'}}
        return remote[ident]
    return remote[path.split('/')[-1]]
live_billing.provider_request=provider

@main.app.get('/_test/mailbox')
def code(email:str): return {'code':mailbox[email]}
@main.app.post('/_test/settle/{ident}')
def settle(ident:str):
    remote[ident].update(status='succeeded',paid=True)
    return {'ok':True}

# Deny all provider network traffic even if a fake is accidentally forgotten.
original_connect=socket.socket.connect
def local_connect(self,address):
    if isinstance(address,tuple) and address[0] not in {'127.0.0.1','::1','localhost'}:
        raise RuntimeError('External network forbidden in E2E')
    return original_connect(self,address)
socket.socket.connect=local_connect
if __name__=='__main__':
    import uvicorn
    uvicorn.run(main.app,host='127.0.0.1',port=8001,log_level='warning')
