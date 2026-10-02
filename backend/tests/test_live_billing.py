from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import Settings
from app.models import User, Payment, utc_now, ImportJob, Competitor
from app.live_billing import (Checkout, checkout, refresh, apply_payment, active_package, status,
                             handle_notice, OFFER_VERSION, enabled, reconcile_once, receipts)
from app.trial import reserve_trial
from app.auth import _utc


@pytest.fixture
def db():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add_all([User(id=1), User(id=2)])
        s.commit()
    yield engine
    engine.dispose()


@pytest.fixture
def settings():
    return Settings(billing_enabled=True, yookassa_shop_id='shop', yookassa_secret_key='live-secret',
                    public_origin='https://hypehunter.ru', apify_token='fake', ai_provider='yandex',
                    yandex_ai_enabled=True, yandex_ai_api_key='fake', yandex_ai_folder_id='folder')


def payload(plan='start'):
    return Checkout(plan=plan, receipt_email='receipt@mail.ru', accept_offer=True, offer_version=OFFER_VERSION)


def response(order, state='succeeded'):
    return {'id':'provider-'+order.id,'test':False,'amount':{'value':order.amount,'currency':'RUB'},
            'status':state,'paid':state=='succeeded','recipient':{'account_id':'shop'},
            'metadata':{'order_id':order.id,'user_id':str(order.user_id)},
            'confirmation':{'confirmation_url':'https://yoomoney.ru/checkout/example'}}


def order(s, oid='first', plan='start'):
    p=Payment(id=oid,user_id=1,plan=plan,amount='1999.00' if plan=='start' else '3900.00',
              quota=40 if plan=='start' else 100,receipt_email='receipt@mail.ru',offer_version=OFFER_VERSION)
    s.add(p);s.commit()
    return p


def test_receipt_handoff_only_verified_success_unique_and_private(db,settings,monkeypatch):
    # Contract for a future fiscal adapter: payment success is not receipt
    # success. Until that adapter exists this is only the owner's handoff list.
    monkeypatch.setattr('app.billing.is_owner',lambda session,config,uid:uid==1)
    with Session(db) as s:
        pending=order(s,'receipt-pending')
        canceled=order(s,'receipt-canceled')
        apply_payment(s,canceled,response(canceled,'canceled'),settings)
        paid=order(s,'receipt-paid')
        paid.buyer_inn='772460063060'
        s.add(paid);s.commit()
        apply_payment(s,paid,response(paid),settings)
        apply_payment(s,paid,response(paid),settings)
        rows=receipts(s,settings,1)
        assert len(rows)==1 and rows[0]['id']==paid.id
        assert rows[0]['receipt_email']=='receipt@mail.ru'
        assert rows[0]['buyer_inn']=='772460063060'
        assert 'receipt_email' not in status(s,settings,1)['payments'][0]
        with pytest.raises(HTTPException) as forbidden:receipts(s,settings,2)
        assert forbidden.value.status_code==404
        data=response(paid);data['refunded_amount']={'value':'1999.00','currency':'RUB'}
        apply_payment(s,paid,data,settings)
        assert receipts(s,settings,1)[0]['refunded_amount']=='1999.00'


def test_checkout_frozen_server_prices_idempotency_and_no_card(db,settings,monkeypatch):
    calls=[]
    def provider(config,method,path,data=None,key=None):
        calls.append((method,path,data,key))
        with Session(db) as s:
            p=s.get(Payment,key) if method=='POST' else s.exec(select(Payment).where(Payment.provider_id==path.split('/')[1])).one()
            return response(p,'pending')
    monkeypatch.setattr('app.live_billing.provider_request',provider)
    with Session(db) as s:
        first=checkout(payload(),s,settings,1)
        again=checkout(payload(),s,settings,1)
        assert first['id']==again['id']
        assert len(s.exec(select(Payment)).all())==1
        assert calls[0][2]['amount']=={'value':'1999.00','currency':'RUB'}
        assert calls[0][2]['save_payment_method'] is False
        assert calls[0][3]==first['id']
        assert calls[1][0]=='GET'
        assert active_package(s,1) is None
        with pytest.raises(HTTPException):checkout(payload('pro'),s,settings,1)
        with pytest.raises(HTTPException):refresh(first['id'],s,settings,2)
        assert not s.get(User,1).preferences


@pytest.mark.parametrize('field,value',[('test',True),('paid',False),('status','unknown'),
    ('amount',{'value':'1.00','currency':'RUB'}),('recipient',{'account_id':'other'}),
    ('metadata',{'order_id':'other','user_id':'1'}),
    ('confirmation',{'confirmation_url':'https://yoomoney.ru.evil.test/x'})])
def test_invalid_provider_never_grants(db,settings,field,value):
    with Session(db) as s:
        p=order(s); data=response(p);data[field]=value
        with pytest.raises(HTTPException):apply_payment(s,p,data,settings)
        s.rollback();assert active_package(s,1) is None


def test_success_once_expiry_refund_and_owner_isolation(db,settings,monkeypatch):
    with Session(db) as s:
        p=order(s);apply_payment(s,p,response(p),settings)
        until=p.access_until
        apply_payment(s,p,response(p),settings)
        assert p.access_until==until and p.used==0
        assert (_utc(p.access_until)-_utc(p.access_from)).days==30
        assert reserve_trial(s,1,'threads')==20
        assert status(s,settings,2)['payments']==[]
        assert status(s,settings,1)['subscription']['quota']==40
        with pytest.raises(HTTPException):checkout(payload(),s,settings,1)
        refund=response(p);refund['refunded_amount']={'value':'1999.00','currency':'RUB'}
        apply_payment(s,p,refund,settings);assert active_package(s,1) is None
        apply_payment(s,p,response(p),settings);assert active_package(s,1) is None
        assert reserve_trial(s,1,'reels')==5
        with pytest.raises(HTTPException):receipts(s,settings,2)


def test_webhook_uses_remote_get_and_recovers_lost_id(db,settings,monkeypatch):
    with Session(db) as s:
        p=order(s);confirmed=response(p)
        calls=[]
        monkeypatch.setattr('app.live_billing.provider_request',lambda *args:(calls.append(args) or confirmed))
        notice=SimpleNamespace(type='notification',event='payment.succeeded',object={
            'id':confirmed['id'],'metadata':confirmed['metadata'],'paid':False})
        handle_notice(notice,s,settings);handle_notice(notice,s,settings)
        assert len(calls)==1 and all(c[1]=='GET' for c in calls)
        assert s.get(Payment,'first').access_until is not None
        assert len(s.exec(select(Payment)).all())==1


def test_reconcile_without_browser_return_and_safe_ambiguous_timeout(db,settings,monkeypatch):
    with Session(db) as s:
        p=order(s);p.provider_id='provider-first';s.add(p);s.commit();confirmed=response(p)
    monkeypatch.setattr('app.live_billing.provider_request',lambda *args:confirmed)
    reconcile_once(settings,lambda:Session(db))
    with Session(db) as s:
        assert active_package(s,1) is not None
        p=order(s,'unknown');p.created_at=utc_now()-timedelta(days=2);s.add(p);s.commit()
        with pytest.raises(HTTPException) as error:refresh(p.id,s,settings,1)
        assert error.value.status_code==409


def test_gate_consent_pro_quota_and_failed_calls_reuse_order(db,settings,monkeypatch):
    assert enabled(settings)
    settings.billing_enabled=False
    assert not enabled(settings)
    with Session(db) as s:
        with pytest.raises(HTTPException):checkout(payload(),s,settings,1)
        settings.billing_enabled=True
        bad=payload();bad.accept_offer=False
        with pytest.raises(HTTPException):checkout(bad,s,settings,1)
        def fail(*args):raise HTTPException(503,'timeout')
        monkeypatch.setattr('app.live_billing.provider_request',fail)
        for _ in range(2):
            with pytest.raises(HTTPException):checkout(payload('pro'),s,settings,1)
        p=s.exec(select(Payment)).one();assert p.quota==100 and p.amount=='3900.00'
        apply_payment(s,p,response(p),settings)
        p.used=100;s.add(p);s.commit()
        with pytest.raises(HTTPException):reserve_trial(s,1,'reels')
        p.access_until=utc_now()-timedelta(seconds=1);s.add(p);s.commit()
        assert reserve_trial(s,1,'reels')==5


def test_paid_import_consumes_only_new_materials_and_delete_preserves_usage(db,settings,monkeypatch):
    from test_trial import FakeSource, import_trial
    from app.api import create_competitor, delete_competitor
    from app.schemas import CompetitorCreate
    from fastapi import BackgroundTasks
    monkeypatch.setattr(FakeSource,'count',12)
    with Session(db) as s:
        p=order(s);apply_payment(s,p,response(p),settings)
        p.used=38;s.add(p);s.commit()
        competitor=create_competitor(CompetitorCreate(account='trial_test',requested_count=20),BackgroundTasks(),s,Settings(),1)
        job=s.exec(select(ImportJob).where(ImportJob.user_id==1)).one()
        assert job.payment_id==p.id and job.requested_count==2
        job.status='queued';s.add(job);s.commit();jid=job.id;cid=competitor.id
        with pytest.raises(HTTPException):reserve_trial(s,1,'threads')
    import_trial(db,jid,monkeypatch)
    with Session(db) as s:
        assert s.get(ImportJob,jid).status=='completed'
        assert s.get(Payment,'first').used==40
        assert s.get(User,1).trial_reels_used==0
        delete_competitor(cid,s,Settings(),1)
        assert s.get(Payment,'first').used==40
        with pytest.raises(HTTPException):reserve_trial(s,1,'threads')


def test_refund_before_import_prevents_paid_quota_consumption(db,settings,monkeypatch):
    from test_trial import FakeSource, import_trial
    from app.api import create_competitor
    from app.schemas import CompetitorCreate
    from fastapi import BackgroundTasks
    monkeypatch.setattr(FakeSource,'count',12)
    with Session(db) as s:
        p=order(s);apply_payment(s,p,response(p),settings)
        create_competitor(CompetitorCreate(account='trial_test',requested_count=3),BackgroundTasks(),s,Settings(),1)
        job=s.exec(select(ImportJob).where(ImportJob.user_id==1)).one()
        job.status='queued';s.add(job);s.commit();jid=job.id
        p.revoked_at=utc_now();s.add(p);s.commit()
    import_trial(db,jid,monkeypatch)
    with Session(db) as s:
        assert s.get(ImportJob,jid).status=='failed'
        assert s.get(Payment,'first').used==0
