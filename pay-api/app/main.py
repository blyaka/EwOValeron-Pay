# main.py
import os
import time
import json
import uuid
import hmac
import hashlib
import logging
from typing import Optional, Dict, Any

import httpx
import aio_pika
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from urllib.parse import urlencode, quote

import asyncio
from datetime import datetime, timedelta

# --- конфиг из окружения ---
RABBIT_URL = os.getenv("RABBIT_URL", "amqp://user:pass@rabbit:5672/")
FREKASSA_BASE_URL = "https://api.fk.life/v1/"

MERCHANT_ID = os.getenv("FREKASSA_MERCHANT_ID")
API_KEY     = os.getenv("FREKASSA_API_KEY")
SECRET_KEY  = os.getenv("FREKASSA_SECRET_KEY")
SECRET1     = os.getenv("FREKASSA_SECRET_KEY")
SECRET2     = os.getenv("FREKASSA_SECRET2")

app = FastAPI()
logger = logging.getLogger("uvicorn.error")


class _DropHealth(logging.Filter):
    def filter(self, record):
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record)
        return "/health" not in msg

logging.getLogger("uvicorn.access").addFilter(_DropHealth())



# --- утилиты подписи ---
def _eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.lower(), b.lower())

def fk_hmac_signature(data: Dict[str, Any], api_key: str) -> str:
    items = dict(sorted(data.items(), key=lambda x: x[0]))
    msg = "|".join(str(v) for v in items.values())
    return hmac.new(api_key.encode(), msg.encode(), hashlib.sha256).hexdigest()

def api_v1_webhook_sign(order_id: str, amount: str, currency: str, secret: str) -> str:
    payload = f"{order_id}:{amount}:{currency}:{secret}".encode()
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

def sci_sign_md5(merchant_id: str, amount: str, secret2: str, order_id: str) -> str:
    return hashlib.md5(f"{merchant_id}:{amount}:{secret2}:{order_id}".encode()).hexdigest()


# --- ping/health ---
@app.get("/")
async def root():
    return {"status": "ok"}

@app.get("/health")
def health():
    return PlainTextResponse("ok")

@app.get("/ping")
async def ping():
    return {"pong": True}




# ============ Идемпотентность ============


IDEMP_TTL_SEC = int(os.getenv("IDEMP_TTL_SEC", "86400"))  # 24h
INTERNAL_TOKEN = os.getenv("PAY_INTERNAL_TOKEN")

_idem_lock = asyncio.Lock()
_idem_store: dict[str, dict] = {}  # key -> {"expires": dt, "payload": {...}}

async def idem_get(key: str) -> Optional[Dict[str, Any]]:
    now = datetime.utcnow()
    async with _idem_lock:
        rec = _idem_store.get(key)
        if not rec:
            return None
        if rec["expires"] < now:
            _idem_store.pop(key, None)
            return None
        return rec["payload"]

async def idem_set(key: str, payload: Dict[str, Any]) -> None:
    expire_at = datetime.utcnow() + timedelta(seconds=IDEMP_TTL_SEC)
    async with _idem_lock:
        # ленивый GC
        for k, v in list(_idem_store.items()):
            if v["expires"] < datetime.utcnow():
                _idem_store.pop(k, None)
        _idem_store[key] = {"expires": expire_at, "payload": payload}




# ============ 1) Создание заказа ============
class OrderCreate(BaseModel):
    amount: float
    email: str
    ip: str
    payment_method: int = 36
    description: Optional[str] = None
    payment_id: Optional[str] = None

@app.post("/create_order")
async def create_order(
    order: OrderCreate,
    request: Request,
    x_internal_token: Optional[str] = Header(None, convert_underscores=False),
    x_idempotency_key: Optional[str] = Header(None, convert_underscores=False),
):
    # внутренняя авторизация
    if INTERNAL_TOKEN and x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # если пришел идемпотентный ключ — пробуем отдать сохраненный ответ
    if x_idempotency_key:
        cached = await idem_get(x_idempotency_key)
        if cached:
            logger.info("Idempotent HIT key=%s payment_id=%s", x_idempotency_key, cached.get("payment_id"))
            return cached

    if not MERCHANT_ID:
        raise HTTPException(status_code=500, detail="MERCHANT_ID not configured")
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API_KEY not configured")

    payment_id = order.payment_id or f"ord-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
    nonce = int(time.time() * 1000)

    base_payload = {
        "shopId": int(MERCHANT_ID),
        "nonce": nonce,
        "paymentId": payment_id,
        "i": order.payment_method,
        "email": order.email,
        "ip": order.ip,
        "amount": f"{order.amount:.2f}",
        "currency": "RUB",
    }
    if order.description:
        base_payload["description"] = order.description

    signature = fk_hmac_signature(base_payload, API_KEY)
    payload = {**base_payload, "signature": signature}

    logger.info("FK create: payment_id=%s amount=%s", payment_id, base_payload["amount"])

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(FREKASSA_BASE_URL + "orders/create", json=payload)
    except httpx.RequestError as e:
        logger.error("FK request error: %s", e)
        raise HTTPException(status_code=502, detail="FK unreachable")

    if r.status_code in (200, 201, 202):
        pay_url = r.headers.get("Location") or r.headers.get("location")
        try:
            data = r.json()
            pay_url = pay_url or data.get("location") or data.get("Location")
        except Exception:
            pass
        if not pay_url:
            logger.error("FK no pay link: code=%s body=%s", r.status_code, r.text[:500])
            raise HTTPException(status_code=500, detail="FK response without pay link")

        resp = {"pay_url": pay_url, "payment_id": payment_id}
        # сохраняем ответ по idem-ключу
        if x_idempotency_key:
            await idem_set(x_idempotency_key, resp)
        return resp

    logger.error("FK error %s: %s", r.status_code, r.text[:800])
    raise HTTPException(status_code=502, detail=f"FK error {r.status_code}: {r.text[:300]}")




# ============ 1.1) Создание универсальной ссылки (SCI) ============

def generate_sci_link(
    merchant_id: str,
    amount: float,
    order_id: Optional[str],
    currency: str,
    secret1: str,
    description: Optional[str] = None,
    us_tag: Optional[str] = None,
    us_comment: Optional[str] = None,
    return_url: Optional[str] = None
) -> Dict[str, str]:

    if not merchant_id or not secret1:
        raise ValueError("merchant_id и secret1 обязательны")

    currency = currency.upper()
    if currency == "RUB" and amount < 50:
        raise ValueError("Минимальная сумма SCI — 50 RUB")

    order_id = order_id or f"sci-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
    amount_str = f"{amount:.2f}"

    parts = [merchant_id, amount_str, secret1]
    if currency:
        parts.append(currency)
    parts.append(order_id)
    sign = hashlib.md5(":".join(parts).encode()).hexdigest()

    params = {
        "m": merchant_id,
        "oa": amount_str,
        "o": order_id,
        "s": sign,
        "currency": currency,
    }
    if description: params["us_desc"] = description
    if us_tag:      params["us_tag"] = us_tag
    if us_comment:  params["us_comment"] = us_comment
    if return_url:  params["return_url"] = return_url

    query = urlencode(params, safe="/:?#[]@!$&()*+,;=")
    pay_url = f"https://pay.freekassa.ru/?{query}"

    return {"pay_url": pay_url, "order_id": order_id, "sign": sign}


class SCILinkRequest(BaseModel):
    amount: float
    order_id: Optional[str] = None
    currency: str = "RUB"
    description: Optional[str] = None
    us_tag: Optional[str] = None
    us_comment: Optional[str] = None
    return_url: Optional[str] = None

@app.post("/create_sci_link")
async def create_sci_link(req: SCILinkRequest):
    if not MERCHANT_ID:
        raise HTTPException(500, "MERCHANT_ID not configured")
    if not os.getenv("FREKASSA_SECRET_KEY"):
        raise HTTPException(500, "FREKASSA_SECRET_KEY not configured")

    try:
        link = generate_sci_link(
            merchant_id=str(MERCHANT_ID),
            amount=req.amount,
            order_id=req.order_id,
            currency=req.currency,
            secret1=os.getenv("FREKASSA_SECRET_KEY"),
            description=req.description,
            us_tag=req.us_tag,
            us_comment=req.us_comment,
            return_url=req.return_url
        )
        logger.info("SCI link created: order_id=%s amount=%s", link["order_id"], req.amount)
        return link
    except ValueError as e:
        raise HTTPException(400, str(e))






# ============ 2) Вебхук  ============
async def _publish_payment_event(event: dict):
    try:
        conn = await aio_pika.connect_robust(RABBIT_URL)
        ch = await conn.channel()
        q = await ch.declare_queue("payments.events", durable=True)
        await ch.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(event, ensure_ascii=False).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=q.name
        )
        await conn.close()
    except Exception as e:
        logger.error("RabbitMQ error: %s", e)



@app.post("/webhook/", response_class=PlainTextResponse)
async def webhook(request: Request):
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        data = await request.json()
        if not isinstance(data, dict):
            raise HTTPException(400, "Invalid JSON")
    else:
        form = await request.form()
        data = dict(form)

    if ("MERCHANT_ID" in data) and ("MERCHANT_ORDER_ID" in data) and ("SIGN" in data):
        if not SECRET2:
            raise HTTPException(500, "SECRET2 not configured")
        merchant_id = str(data["MERCHANT_ID"])
        amount      = str(data["AMOUNT"])
        order_id    = str(data["MERCHANT_ORDER_ID"])
        got_sign    = str(data["SIGN"])

        must = sci_sign_md5(merchant_id, amount, SECRET2, order_id)
        if not _eq(got_sign, must):
            raise HTTPException(400, "Invalid SIGN (SCI)")

        event = {
            "provider": "freekassa",
            "schema":   "sci",
            "order_id": order_id,
            "amount":   amount,
            "currency": data.get("currency") or data.get("CUR") or data.get("CUR_ID"),
            "status":   "success",
            "raw":      data,
        }
        await _publish_payment_event(event)
        return PlainTextResponse("YES")

    try:
        order_id = str(data["orderId"])
        amount   = str(data["amount"])
        currency = str(data["currency"])
        got_sign = str(data.get("sign") or data.get("signature"))
        status   = str(data.get("status", "")) or "success"
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing field: {e}")

    if not SECRET_KEY:
        raise HTTPException(500, "API secret not configured")

    must = api_v1_webhook_sign(order_id, amount, currency, SECRET_KEY)
    if not _eq(got_sign, must):
        raise HTTPException(status_code=400, detail="Invalid signature (API v1)")

    event = {
        "provider": "freekassa",
        "schema":   "api_v1",
        "order_id": order_id,
        "amount":   amount,
        "currency": currency,
        "status":   status,
        "raw":      data,
    }
    await _publish_payment_event(event)
    return PlainTextResponse("OK")
