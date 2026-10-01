"""One-ruble owner-only sandbox checkout. No live billing or trial changes."""
import base64
import json
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.request import Request as URLRequest, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session, select

from .auth import require_user_id, _utc
from .config import Settings, get_settings
from .database import get_session
from .models import AuthIdentity, TestPayment, User, utc_now

router = APIRouter(prefix="/api/billing")
WEBHOOK_PATH = "/api/billing/yookassa/test/webhook"


def is_owner(session, settings, user_id):
    if not settings.owner_telegram_id:
        return False
    return session.exec(select(AuthIdentity.id).where(AuthIdentity.user_id == user_id,
        AuthIdentity.provider == "telegram", AuthIdentity.provider_subject == str(settings.owner_telegram_id))).first() is not None


def available(session, settings, user_id):
    return bool(settings.yookassa_test_shop_id and settings.yookassa_test_secret_key.startswith("test_")
                and is_owner(session, settings, user_id))


def provider_request(settings, method, path, payload=None, key=None):
    credentials = base64.b64encode(f"{settings.yookassa_test_shop_id}:{settings.yookassa_test_secret_key}".encode()).decode()
    headers = {"Authorization": "Basic " + credentials, "Content-Type": "application/json"}
    if key:
        headers["Idempotence-Key"] = key
    data = json.dumps(payload).encode() if payload is not None else None
    req = URLRequest("https://api.yookassa.ru/v3/" + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=20) as reply:
            result = json.loads(reply.read(128000))
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        raise HTTPException(503, "ЮKassa пока не ответила или отклонила запрос. Проверьте настройки тестового магазина и попробуйте снова.") from None


def apply_payment(session, order, data):
    try:
        valid = (data.get("test") is True and data["amount"]["currency"] == "RUB"
                 and Decimal(data["amount"]["value"]) == Decimal("1.00")
                 and data.get("metadata", {}).get("test_order") == order.id
                 and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", data["id"])
                 and (order.provider_id is None or order.provider_id == data["id"]))
    except (KeyError, TypeError, AttributeError, InvalidOperation):
        valid = False
    if not valid:
        raise HTTPException(502, "Ответ ЮKassa не соответствует тестовому заказу. Доступ не изменён.")
    state = data.get("status")
    if state not in {"pending", "waiting_for_capture", "succeeded", "canceled"}:
        raise HTTPException(502, "Неизвестное состояние тестового платежа")
    confirmation = data.get("confirmation") or {}
    if not isinstance(confirmation, dict):
        raise HTTPException(502, "Неверное подтверждение платежа ЮKassa")
    url = confirmation.get("confirmation_url")
    if url:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if parsed.scheme != "https" or parsed.username or parsed.password or not any(host == domain or host.endswith('.'+domain) for domain in ('yoomoney.ru', 'yookassa.ru')):
            raise HTTPException(502, "Неверный адрес оплаты ЮKassa")
        order.confirmation_url = url
    if order.status in {"succeeded", "canceled"} and state != order.status:
        raise HTTPException(502, "Состояние завершённого платежа не может быть изменено")
    if state == "succeeded" and data.get("paid") is not True:
        raise HTTPException(502, "Оплата не подтверждена")
    order.provider_id = data["id"]
    order.status = state
    if state == "succeeded" and not order.test_access_until:
        order.test_access_until = utc_now() + timedelta(days=30)
    session.add(order)
    session.commit()


def public_order(order):
    return {"id": order.id, "status": order.status, "confirmation_url": order.confirmation_url if order.status == "pending" else None,
            "test_access_until": order.test_access_until.isoformat() if order.test_access_until else None}


@router.get("/test")
def test_status(session: Session = Depends(get_session), settings: Settings = Depends(get_settings), user_id: int = Depends(require_user_id)):
    enabled = available(session, settings, user_id)
    order = session.exec(select(TestPayment).where(TestPayment.user_id == user_id).order_by(TestPayment.created_at.desc()).limit(1)).first() if enabled else None
    return {"owner": is_owner(session, settings, user_id), "available": enabled, "test": True, "amount": "1.00", "currency": "RUB", "payment": public_order(order) if order else None}


@router.post("/test/checkout")
def checkout(session: Session = Depends(get_session), settings: Settings = Depends(get_settings), user_id: int = Depends(require_user_id)):
    if not available(session, settings, user_id):
        raise HTTPException(404, "Тестовая оплата недоступна")
    session.exec(select(User).where(User.id == user_id).with_for_update()).one()
    orders = session.exec(select(TestPayment).where(TestPayment.user_id == user_id, TestPayment.created_at >= utc_now()-timedelta(hours=24)).order_by(TestPayment.created_at.desc())).all()
    order = next((item for item in orders if item.status == "pending"), None)
    if not order:
        if len(orders) >= 10:
            raise HTTPException(429, "Лимит тестовых платежей на сегодня исчерпан")
        order = TestPayment(id=str(uuid4()), user_id=user_id)
        session.add(order); session.commit()
    # Lock the persistent order across provider calls; retries use the same key.
    order = session.exec(select(TestPayment).where(TestPayment.id == order.id).with_for_update()).one()
    if order.provider_id:
        data = provider_request(settings, "GET", "payments/" + order.provider_id)
    else:
        data = provider_request(settings, "POST", "payments", {"amount": {"value": "1.00", "currency": "RUB"}, "capture": True,
            "confirmation": {"type": "redirect", "return_url": settings.public_origin + "/account?tab=subscription&test_payment=" + order.id},
            "description": "Hype Hunter: тестовая подписка, 1 рубль. Без реального списания.",
            "save_payment_method": False, "metadata": {"test_order": order.id}}, order.id)
    apply_payment(session, order, data)
    return public_order(order)


@router.post("/test/payments/{order_id}/refresh")
def refresh(order_id: str, session: Session = Depends(get_session), settings: Settings = Depends(get_settings), user_id: int = Depends(require_user_id)):
    if not available(session, settings, user_id):
        raise HTTPException(404, "Тестовая оплата недоступна")
    order = session.exec(select(TestPayment).where(TestPayment.id == order_id, TestPayment.user_id == user_id).with_for_update()).first()
    if not order or not order.provider_id:
        raise HTTPException(404, "Тестовый платёж не найден")
    apply_payment(session, order, provider_request(settings, "GET", "payments/" + order.provider_id))
    return public_order(order)


class Notice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str
    event: str
    object: dict


@router.post("/yookassa/test/webhook")
def notification(payload: Notice, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    if payload.type != "notification" or payload.event not in {"payment.succeeded", "payment.canceled"}:
        return {"received": True}
    payment_id = payload.object.get("id", "")
    if not isinstance(payment_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", payment_id):
        raise HTTPException(422, "Неверный идентификатор платежа")
    order = session.exec(select(TestPayment).where(TestPayment.provider_id == payment_id).with_for_update()).first()
    if order and available(session, settings, order.user_id):
        # Never trust callback state/amount; retrieve this order with our shop credentials.
        apply_payment(session, order, provider_request(settings, "GET", "payments/" + payment_id))
    return {"received": True}
