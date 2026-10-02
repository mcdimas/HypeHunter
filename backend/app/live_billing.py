"""One-off YooKassa packages. Provider-confirmed access; no saved cards."""
import base64
import json
import logging
import re
import threading
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator
from sqlmodel import Session, select

from .auth import require_user_id, _utc
from .config import Settings, get_settings
from .database import get_session
from .models import Payment, User, utc_now

router = APIRouter(prefix="/api/billing")
WEBHOOK_PATH = "/api/billing/yookassa/webhook"
OFFER_VERSION = "2026-10-02"
PLANS = {"start": {"name": "Старт", "amount": "1999.00", "quota": 40},
         "pro": {"name": "Про", "amount": "3900.00", "quota": 100}}
logger = logging.getLogger(__name__)


def configured(settings):
    return bool(settings.yookassa_shop_id and settings.yookassa_secret_key
                and not settings.yookassa_secret_key.startswith("test_")
                and settings.public_origin.startswith("https://"))


def enabled(settings):
    ai_ready = (settings.yandex_ai_enabled and settings.yandex_ai_api_key and settings.yandex_ai_folder_id
                if settings.ai_provider == "yandex" else settings.openai_enabled and settings.openai_api_key)
    return bool(settings.billing_enabled and configured(settings) and ai_ready and settings.apify_token)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def provider_request(settings, method, path, payload=None, key=None):
    if not configured(settings) or not re.fullmatch(r"(?:payments|refunds)(?:/[A-Za-z0-9_-]{1,80})?", path):
        raise HTTPException(503, "Оплата временно недоступна")
    auth = base64.b64encode(f"{settings.yookassa_shop_id}:{settings.yookassa_secret_key}".encode()).decode()
    headers = {"Authorization": "Basic " + auth, "Content-Type": "application/json"}
    if key:
        headers["Idempotence-Key"] = key
    request = Request("https://api.yookassa.ru/v3/" + path, headers=headers, method=method,
                      data=json.dumps(payload).encode() if payload is not None else None)
    try:
        with build_opener(NoRedirect()).open(request, timeout=20) as reply:
            data = json.loads(reply.read(128000))
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        raise HTTPException(503, "ЮKassa не подтвердила результат. Не создавайте новый платёж: проверьте этот платёж позже.") from None


def active_package(session, user_id):
    return session.exec(select(Payment).where(Payment.user_id == user_id,
        Payment.status == "succeeded", Payment.revoked_at.is_(None), Payment.access_from <= utc_now(), Payment.access_until > utc_now())
        .order_by(Payment.access_until.desc())).first()


def apply_payment(session, order, data, settings):
    """Caller must lock the user before the order; commit entitlement exactly once."""
    try:
        valid = (data.get("test") is False and data["amount"]["currency"] == "RUB"
                 and Decimal(data["amount"]["value"]) == Decimal(order.amount)
                 and data.get("recipient", {}).get("account_id") == settings.yookassa_shop_id
                 and data.get("metadata", {}).get("order_id") == order.id
                 and data.get("metadata", {}).get("user_id") == str(order.user_id)
                 and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", data["id"])
                 and (order.provider_id is None or data["id"] == order.provider_id))
        refunded = Decimal((data.get("refunded_amount") or {}).get("value", "0.00"))
        if data.get("refunded_amount"):
            valid = valid and data["refunded_amount"]["currency"] == "RUB"
        valid = valid and refunded.is_finite() and Decimal("0") <= refunded <= Decimal(order.amount)
    except (KeyError, TypeError, AttributeError, InvalidOperation):
        valid = False
    state = data.get("status")
    if not valid or state not in {"pending", "waiting_for_capture", "succeeded", "canceled"}:
        raise HTTPException(502, "Ответ ЮKassa не соответствует заказу. Доступ не изменён.")
    if order.status in {"succeeded", "canceled"} and state != order.status:
        raise HTTPException(502, "Завершённый платёж не может менять состояние")
    if state == "succeeded" and data.get("paid") is not True:
        raise HTTPException(502, "Оплата не подтверждена")
    confirmation = data.get("confirmation") or {}
    if not isinstance(confirmation, dict):
        raise HTTPException(502, "Неверное подтверждение ЮKassa")
    url = confirmation.get("confirmation_url")
    if url:
        try:
            parsed = urlparse(url)
            safe = isinstance(url, str) and parsed.scheme == "https" and not parsed.username and not parsed.password and parsed.port in {None, 443} and any(
                parsed.hostname == domain or (parsed.hostname or "").endswith("."+domain)
                for domain in ("yoomoney.ru", "yookassa.ru"))
        except (ValueError, TypeError, AttributeError):
            safe = False
        if not safe:
            raise HTTPException(502, "Неверный адрес оплаты")
        order.confirmation_url = url
    order.provider_id = data["id"]
    order.status = state
    order.checked_at = utc_now()
    order.refunded_amount = str(max(Decimal(order.refunded_amount), refunded))
    if refunded == Decimal(order.amount):
        order.revoked_at = order.revoked_at or utc_now()
    if state == "succeeded" and order.access_until is None and not order.revoked_at:
        # A second successful payment cannot erase an existing paid period.
        previous = session.exec(select(Payment).where(Payment.user_id == order.user_id,
            Payment.id != order.id, Payment.status == "succeeded", Payment.revoked_at.is_(None),
            Payment.access_until > utc_now()).order_by(Payment.access_until.desc())).first()
        start = max(utc_now(), _utc(previous.access_until)) if previous and previous.id != order.id else utc_now()
        order.access_from = start
        order.access_until = start + timedelta(days=30)
    session.add(order)
    session.commit()


def public_order(order):
    return {"id": order.id, "status": "refunded" if order.revoked_at else order.status,
            "plan": order.plan, "amount": order.amount, "quota": order.quota, "used": order.used,
            "confirmation_url": order.confirmation_url if order.status == "pending" else None,
            "created_at": order.created_at.isoformat(),
            "access_until": order.access_until.isoformat() if order.access_until else None}


def lock_order(session, order_id, user_id=None):
    order = session.get(Payment, order_id)
    if not order or (user_id is not None and order.user_id != user_id):
        raise HTTPException(404, "Платёж не найден")
    session.exec(select(User).where(User.id == order.user_id).with_for_update()).one()
    session.refresh(order, with_for_update=True)
    return order


def reconcile(session, order, settings):
    if order.provider_id:
        data = provider_request(settings, "GET", "payments/" + order.provider_id)
    elif _utc(order.created_at) < utc_now() - timedelta(hours=23):
        # YooKassa idempotency retention is 24 hours. Never recreate an uncertain order later.
        raise HTTPException(409, "Результат платежа требует проверки поддержкой. Укажите ID платежа.")
    else:
        data = provider_request(settings, "POST", "payments", {
            "amount": {"value": order.amount, "currency": "RUB"}, "capture": True,
            "confirmation": {"type": "redirect", "return_url": settings.public_origin + "/account?tab=subscription&payment=" + order.id},
            "description": "Hype Hunter: " + PLANS[order.plan]["name"] + ", доступ на 30 дней",
            "save_payment_method": False, "metadata": {"order_id": order.id, "user_id": str(order.user_id)}}, order.id)
    apply_payment(session, order, data, settings)
    return public_order(order)


class Checkout(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: str
    receipt_email: str
    buyer_inn: str = ""
    accept_offer: bool
    offer_version: str

    @field_validator("receipt_email")
    @classmethod
    def email(cls, value):
        value = value.strip().lower()
        if len(value) > 254 or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", value):
            raise ValueError("Укажите email для чека")
        return value

    @field_validator("buyer_inn")
    @classmethod
    def inn(cls, value):
        value = value.strip()
        if value and not re.fullmatch(r"(?:[0-9]{10}|[0-9]{12})", value):
            raise ValueError("ИНН должен содержать 10 или 12 цифр")
        return value


@router.get("/status")
def status(session: Session = Depends(get_session), settings: Settings = Depends(get_settings), user_id: int = Depends(require_user_id)):
    current = active_package(session, user_id)
    orders = session.exec(select(Payment).where(Payment.user_id == user_id).order_by(Payment.created_at.desc()).limit(10)).all()
    return {"available": enabled(settings), "offer_version": OFFER_VERSION, "plans": PLANS,
            "subscription": public_order(current) if current else None, "payments": [public_order(p) for p in orders],
            "auto_renew": False}


@router.get("/receipts")
def receipts(session: Session = Depends(get_session), settings: Settings = Depends(get_settings), user_id: int = Depends(require_user_id)):
    from .billing import is_owner
    if not is_owner(session, settings, user_id):
        raise HTTPException(404, "Раздел не найден")
    orders = session.exec(select(Payment).where(Payment.status == "succeeded").order_by(Payment.created_at.desc()).limit(100)).all()
    return [{**public_order(p), "receipt_email": p.receipt_email, "buyer_inn": p.buyer_inn,
             "refunded_amount": p.refunded_amount, "user_id": p.user_id} for p in orders]


@router.post("/checkout")
def checkout(payload: Checkout, session: Session = Depends(get_session), settings: Settings = Depends(get_settings), user_id: int = Depends(require_user_id)):
    if not enabled(settings):
        raise HTTPException(503, "Оплата временно недоступна")
    if payload.plan not in PLANS or payload.accept_offer is not True or payload.offer_version != OFFER_VERSION:
        raise HTTPException(422, "Выберите тариф и подтвердите актуальную оферту")
    session.exec(select(User).where(User.id == user_id).with_for_update()).one()
    orders = session.exec(select(Payment).where(Payment.user_id == user_id, Payment.status.in_(["pending", "waiting_for_capture"]))).all()
    if orders:
        order = orders[0]
        if order.plan != payload.plan:
            raise HTTPException(409, "Сначала завершите или отмените предыдущий платёж на странице ЮKassa")
        session.commit()
        return reconcile(session, lock_order(session, order.id, user_id), settings)
    if active_package(session, user_id):
        raise HTTPException(409, "Доступ уже оплачен. Новый пакет можно приобрести после окончания текущих 30 дней.")
    recent = session.exec(select(Payment.id).where(Payment.user_id == user_id, Payment.created_at > utc_now()-timedelta(days=1))).all()
    if len(recent) >= 10:
        raise HTTPException(429, "Слишком много попыток оплаты. Попробуйте завтра.")
    plan = PLANS[payload.plan]
    order = Payment(id=str(uuid4()), user_id=user_id, plan=payload.plan, amount=plan["amount"], quota=plan["quota"],
                    receipt_email=payload.receipt_email, buyer_inn=payload.buyer_inn, offer_version=OFFER_VERSION)
    session.add(order)
    session.commit()
    return reconcile(session, lock_order(session, order.id, user_id), settings)


@router.post("/payments/{order_id}/refresh")
def refresh(order_id: str, session: Session = Depends(get_session), settings: Settings = Depends(get_settings), user_id: int = Depends(require_user_id)):
    return reconcile(session, lock_order(session, order_id, user_id), settings)


class Notice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str
    event: str
    object: dict


def handle_notice(payload, session, settings):
    if payload.type != "notification" or payload.event not in {"payment.succeeded", "payment.canceled", "refund.succeeded"}:
        return {"received": True}
    # Only a hint to find the order. State, amount and ownership come from authenticated GET.
    pid = payload.object.get("payment_id") if payload.event == "refund.succeeded" else payload.object.get("id")
    if not isinstance(pid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", pid):
        raise HTTPException(422, "Неверный идентификатор платежа")
    order = session.exec(select(Payment).where(Payment.provider_id == pid)).first()
    if order is None and payload.event != "refund.succeeded":
        metadata = payload.object.get("metadata")
        oid = metadata.get("order_id") if isinstance(metadata, dict) else None
        order = session.get(Payment, oid) if isinstance(oid, str) else None
    if order and configured(settings):
        order = lock_order(session, order.id)
        if order.checked_at and _utc(order.checked_at) > utc_now()-timedelta(seconds=5):
            return {"received": True}
        apply_payment(session, order, provider_request(settings, "GET", "payments/" + pid), settings)
    return {"received": True}


@router.post("/yookassa/webhook")
def notification(payload: Notice, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    return handle_notice(payload, session, settings)


def reconcile_once(settings, session_factory):
    with session_factory() as session:
        # Oldest checked first prevents starvation. Also catches refunds without a callback.
        ids = session.exec(select(Payment.id).where(Payment.revoked_at.is_(None),
            Payment.status.in_(["pending", "waiting_for_capture", "succeeded"]))
            .order_by(Payment.checked_at.asc().nullsfirst()).limit(20)).all()
    for oid in ids:
        try:
            with session_factory() as session:
                order = lock_order(session, oid)
                # Persist attempt time even on errors so one stuck order cannot starve others.
                order.checked_at = utc_now()
                session.add(order)
                session.commit()
                reconcile(session, lock_order(session, oid), settings)
        except Exception:
            logger.warning("YooKassa reconciliation pending for order %s", oid)


def start_reconciliation(settings, engine):
    if not configured(settings):
        return None
    stop = threading.Event()
    def worker():
        while not stop.is_set():
            try:
                reconcile_once(settings, lambda: Session(engine))
            except Exception:
                logger.warning("YooKassa reconciliation temporarily unavailable")
            stop.wait(60)
    thread = threading.Thread(target=worker, name="billing-reconciliation", daemon=True)
    thread.start()
    return stop, thread
