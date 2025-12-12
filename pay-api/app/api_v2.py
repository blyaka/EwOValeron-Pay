# paymentlnk_v2.py
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
import asyncio
import redis.asyncio as redis
import re
from urllib.parse import quote

from datetime import datetime, timedelta

from fastapi import APIRouter, Request, HTTPException, Header
from fastapi.responses import PlainTextResponse, RedirectResponse
from pydantic import BaseModel

# ========= Конфиг =========

RABBIT_URL = os.getenv("RABBIT_URL", "amqp://user:pass@rabbit:5672/")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/1")
redis_cli = redis.from_url(REDIS_URL, decode_responses=True)

PAYMENTLNK_BASE_URL = "https://start.paymentlnk.com/api/"

PLNK_ACCOUNT = os.getenv("PLNK_ACCOUNT")       # 'account' из доки
PLNK_SECRET1 = os.getenv("PLNK_SECRET1")
PLNK_SECRET2 = os.getenv("PLNK_SECRET2")
PLNK_PAYSYS = os.getenv("PLNK_PAYSYS", "EXT")  # EXT / MBC и т.п.
PLNK_AMOUNTCURR = os.getenv("PLNK_AMOUNTCURR", "RUB")
PLNK_HASH_ALG = os.getenv("PLNK_HASH_ALG", "md5").lower()  # md5 | sha256

PAY_LINK_TTL_HOURS = int(os.getenv("PAY_LINK_TTL_HOURS", "24"))
IDEMP_TTL_SEC = int(os.getenv("IDEMP_TTL_SEC", "86400"))
INTERNAL_TOKEN = os.getenv("PAY_INTERNAL_TOKEN")
PLNK_BACKURL = os.getenv("PLNK_BACKURL")

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/v2", tags=["paymentlnk"])


from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")


# ========= Утилиты =========

def _eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.lower(), b.lower())


# --- идемпотентность (локальная память процесса) ---
_idem_lock = asyncio.Lock()
_idem_store: dict[str, dict] = {}


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


# --- Redis-хранилище прокладочных ссылок ---
async def plnk_link_get(token: str) -> Optional[Dict[str, Any]]:
    raw = await redis_cli.get(f"plnk:paylink:{token}")
    return json.loads(raw) if raw else None


async def plnk_link_set(token: str, plnk_url: str, ttl_seconds: int):
    exp = datetime.utcnow() + timedelta(seconds=ttl_seconds)
    rec = {
        "plnk_url": plnk_url,
        "expires_at": exp.isoformat() + "Z",
    }
    await redis_cli.setex(f"plnk:paylink:{token}", ttl_seconds, json.dumps(rec, ensure_ascii=False))


# --- Публикация событий в RabbitMQ ---
async def _publish_payment_event(event: dict):
    try:
        conn = await aio_pika.connect_robust(RABBIT_URL)
        ch = await conn.channel()
        q = await ch.declare_queue("payments.events", durable=True)
        await ch.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(event, ensure_ascii=False).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=q.name,
        )
        await conn.close()
    except Exception as e:
        logger.error("RabbitMQ error: %s", e)


# ========= Подписи =========
def _plnk_invoice_signature(
    *,
    amount: str,
    amountcurr: str,
    paysys: str,
    number: str,
    description: str,
    validity: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str],
    middle_name: Optional[str],
    cf1: Optional[str],
    cf2: Optional[str],
    cf3: Optional[str],
    email: Optional[str],
    notify_email: Optional[str],
    phone: Optional[str],
    notify_phone: Optional[str],
    backURL: Optional[str],
    account: str,
) -> str:
    def _n(s: Optional[str]) -> Optional[str]:
        if s is None:
            return None
        s = str(s).strip()
        return s if s else None

    validity = _n(validity)
    first_name = _n(first_name)
    last_name = _n(last_name)
    middle_name = _n(middle_name)

    cf1 = _n(cf1)
    cf2 = _n(cf2)
    cf3 = _n(cf3)

    email = _n(email)
    notify_email = _n(notify_email)
    phone = _n(phone)
    notify_phone = _n(notify_phone)

    backURL = _n(backURL)

    parts: list[str] = [
        amount,
        amountcurr,
        paysys,
        number,
        description,
        validity or "",
        first_name or "",
        last_name or "",
        middle_name or "",
    ]

    # ✅ cf-блок: если включили — ДОЛЖНЫ быть 3 слота, cf3 пустой строкой
    if any([cf1, cf2, cf3]):
        parts += [cf1 or "", cf2 or "", cf3 or ""]

    # email/notify_email — только если email есть
    if email:
        parts += [email, notify_email or ""]

    # phone/notify_phone — только если phone есть
    if phone:
        parts += [phone, notify_phone or ""]

    # backURL в ваших запросах всегда есть — включаем
    if backURL:
        parts.append(backURL)

    parts += [account, PLNK_SECRET1 or "", PLNK_SECRET2 or ""]

    base = ":".join(parts)

    print("\n" + "=" * 80)
    print("PLNK 4.12 SIGNATURE DEBUG")
    print("BASE:", base)
    print("=" * 80 + "\n")

    return hashlib.md5(base.encode("utf-8")).hexdigest()  # lowercase




def _plnk_start_signature(
    *,
    amount: str,
    amountcurr: str,
    currency: str,
    number: str,
    description: str,
    trtype: str,
    account: str,
    paytoken: Optional[str],
    backURL: Optional[str],
    cf1: Optional[str],
    cf2: Optional[str],
    cf3: Optional[str],
):
    """
    Подпись для 4.1.1 по доке:
    base = amount:amountcurr:currency:number:description:trtype:account[:paytoken][:backURL][:cf1][:cf2][:cf3]:secret1:secret2
    """

    parts = [
        amount,
        amountcurr,
        currency,
        number,
        description,
        trtype,
        account,
    ]

    if paytoken:
        parts.append(paytoken)

    if backURL:
        parts.append(backURL)

    if any([cf1, cf2, cf3]):
        parts.append(cf1 or "")
        parts.append(cf2 or "")
        parts.append(cf3 or "")

    parts.append(PLNK_SECRET1 or "")
    parts.append(PLNK_SECRET2 or "")

    base = ":".join(parts)
    logger.info("PLNK 4.1.1 base string for signature: %s", base)

    if PLNK_HASH_ALG == "sha256":
        key = ((PLNK_SECRET1 or "") + (PLNK_SECRET2 or "")).encode()
        return hmac.new(key, base.encode(), hashlib.sha256).hexdigest()

    return hashlib.md5(base.encode()).hexdigest()


# ========= Модели =========

class PlnkInvoiceCreate(BaseModel):
    amount: float
    email: Optional[str] = None
    phone: Optional[str] = None
    description: Optional[str] = None
    payment_id: Optional[str] = None
    cf1: Optional[str] = None
    first_name: Optional[str] = None
    validity_minutes: Optional[int] = None


class PlnkInternalCreateLink(BaseModel):
    amount: float
    email: Optional[str] = None
    phone: Optional[str] = None
    description: Optional[str] = None
    payment_id: Optional[str] = None
    ttl_minutes: Optional[int] = None
    cf1: Optional[str] = None
    first_name: Optional[str] = None


# ========= 1) Низкоуровневый invoice (4.12) =========
@router.post("/create_invoice")
async def plnk_create_invoice(
    body: PlnkInvoiceCreate,
    request: Request,
    x_internal_token: Optional[str] = Header(None),
    x_idempotency_key: Optional[str] = Header(None),
):
    if INTERNAL_TOKEN and x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not PLNK_ACCOUNT or not PLNK_SECRET1 or not PLNK_SECRET2:
        raise HTTPException(500, detail="PLNK_* secrets not configured")

    if x_idempotency_key:
        cached = await idem_get(x_idempotency_key)
        if cached:
            return cached

    number = body.payment_id or f"plnk-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
    amount_str = f"{body.amount:.2f}"
    amountcurr = PLNK_AMOUNTCURR.upper()
    paysys = PLNK_PAYSYS.upper()

    desc_raw = body.description or f"Order {number}"
    if len(desc_raw) < 6:
        desc_raw = (desc_raw + "      ")[:6]
    description = quote(desc_raw, safe="")  # URL-encoded

    now = datetime.now(MSK).replace(microsecond=0)
    dt = now + (timedelta(minutes=body.validity_minutes) if body.validity_minutes else timedelta(hours=24))
    validity_str = dt.isoformat()  # +03:00

    first_name = body.first_name or "Client"

    # ✅ КАК В ИХ ПРИМЕРЕ: cf1="userid", cf2="<id>", cf3=""
    user_id = uuid.uuid4().hex
    cf1 = "userid"
    cf2 = user_id
    cf3 = ""

    # ✅ email/phone не шлём вообще (чтобы не было их нормализаций)
    email = None
    phone = None
    notify_email = None
    notify_phone = None

    back_url = (PLNK_BACKURL or "https://evpayservice.com").strip().rstrip("/")

    sig = _plnk_invoice_signature(
        amount=amount_str,
        amountcurr=amountcurr,
        paysys=paysys,
        number=number,
        description=description,
        validity=validity_str,
        first_name=first_name,
        last_name=None,
        middle_name=None,
        cf1=cf1,
        cf2=cf2,
        cf3=cf3,
        email=email,
        notify_email=notify_email,
        phone=phone,
        notify_phone=notify_phone,
        backURL=back_url,
        account=PLNK_ACCOUNT,
    )

    payload: Dict[str, Any] = {
        "amount": amount_str,
        "amountcurr": amountcurr,
        "paysys": paysys,
        "number": number,
        "description": description,
        "account": PLNK_ACCOUNT,
        "signature": sig,
        "validity": validity_str,
        "first_name": first_name,
        "cf1": cf1,
        "cf2": cf2,
        "cf3": cf3,
        "backURL": back_url,
    }

    print("==== PLNK 4.12 PAYLOAD ====")
    print(json.dumps(payload, ensure_ascii=False))
    print("===========================")

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(PAYMENTLNK_BASE_URL + "payment/invoice", data=payload)
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="paymentlnk unreachable")

    try:
        data = r.json()
    except Exception:
        raise HTTPException(status_code=502, detail=f"paymentlnk invalid response: {r.text[:500]}")

    if str(data.get("status") or "").lower() != "wait":
        raise HTTPException(
            status_code=502,
            detail=f"paymentlnk error: {data.get('errorcode')} {data.get('errortext')}",
        )

    resp = {
        "pay_url": data.get("payURL"),
        "payment_id": number,
        "trans_id": str(data.get("transID") or ""),
        "provider": "paymentlnk",
    }

    if x_idempotency_key:
        await idem_set(x_idempotency_key, resp)

    return resp





# ========= 2) Прокладочная ссылка (аналог /internal/create_link) =========
@router.post("/internal/create_link")
async def plnk_internal_create_link(
    body: PlnkInternalCreateLink,
    request: Request,
    x_internal_token: Optional[str] = Header(None),
    x_idempotency_key: Optional[str] = Header(None),
):
    if INTERNAL_TOKEN and x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    ttl_min = body.ttl_minutes if body.ttl_minutes is not None else PAY_LINK_TTL_HOURS * 60
    ttl_min = max(1, min(ttl_min, 60 * 24 * 30))
    ttl_sec = ttl_min * 60
    exp_iso = (datetime.utcnow() + timedelta(seconds=ttl_sec)).isoformat() + "Z"

    # ❌ НИКАКИХ заглушек телефона: можно не передавать phone/email вообще
    phone = (body.phone or "").strip() or None
    email = (body.email or "").strip() or None

    if x_idempotency_key:
        cached = await idem_get(x_idempotency_key)
        if cached:
            plnk_url = cached.get("plnk_url") or cached.get("pay_url")
            if plnk_url:
                token = cached.get("token") or x_idempotency_key
                await plnk_link_set(token, plnk_url, ttl_sec)
                resp = {
                    "public_url": f"https://pay.evpayservice.com/v2/pay/{token}",
                    "token": token,
                    "payment_id": cached.get("payment_id"),
                    "fk_url": plnk_url,
                    "plnk_url": plnk_url,
                    "trans_id": cached.get("trans_id"),
                    "expires_at": exp_iso,
                    "provider": "paymentlnk",
                }
                await idem_set(x_idempotency_key, resp)
                return resp

    created = await plnk_create_invoice(
        body=PlnkInvoiceCreate(
            amount=body.amount,
            email=email,
            phone=phone,
            description=body.description,
            payment_id=body.payment_id,
            cf1=None,  # userid мы генерим внутри create_invoice
            first_name=body.first_name,
            validity_minutes=None,
        ),
        request=request,
        x_internal_token=x_internal_token,
        x_idempotency_key=x_idempotency_key,
    )

    plnk_url = created["pay_url"]
    token = x_idempotency_key or uuid.uuid4().hex
    public_url = f"https://pay.evpayservice.com/v2/pay/{token}"

    await plnk_link_set(token, plnk_url, ttl_sec)

    resp = {
        "public_url": public_url,
        "token": token,
        "payment_id": created["payment_id"],
        "fk_url": plnk_url,
        "plnk_url": plnk_url,
        "trans_id": created["trans_id"],
        "expires_at": exp_iso,
        "provider": "paymentlnk",
    }
    if x_idempotency_key:
        await idem_set(x_idempotency_key, resp)
    return resp




# ========= 3) Редирект по прокладочной ссылке =========

@router.get("/pay/{token}")
async def plnk_pay_redirect(token: str):
    rec = await plnk_link_get(token)
    if not rec:
        raise HTTPException(status_code=404, detail="Link not found or expired")
    return RedirectResponse(url=rec["plnk_url"], status_code=302)


# ========= 4) Callback от paymentlnk (statusURL) =========

@router.post("/status", response_class=PlainTextResponse)
async def plnk_status(request: Request):
    form = await request.form()
    payload = {k: v for k, v in form.items()}

    status_raw = str(payload.get("status") or "").lower()
    order_id = str(payload.get("number") or "")
    trans_id = str(payload.get("transID") or payload.get("transid") or "")

    if not order_id:
        logger.warning("PLNK status without number: %s", payload)
        return PlainTextResponse("NO", status_code=400)

    if PLNK_ACCOUNT and str(payload.get("account") or "") != str(PLNK_ACCOUNT):
        logger.warning("PLNK status wrong account: %s", payload)
        return PlainTextResponse("NO", status_code=400)

    if status_raw == "ok":
        norm_status = "success"
    elif status_raw == "error":
        norm_status = "failed"
    elif status_raw == "wait":
        norm_status = "wait"
    else:
        norm_status = status_raw or "unknown"

    event = {
        "provider": "paymentlnk",
        "schema": "invoice_status",
        "order_id": order_id,
        "amount": str(payload.get("amount") or ""),
        "currency": str(payload.get("amountcurr") or ""),
        "status": norm_status,
        "intid": trans_id,
        "raw": payload,
    }
    event["event_key"] = f"plnk:{trans_id or order_id}"

    logger.info("PLNK STATUS event: %s", event)
    await _publish_payment_event(event)
    return PlainTextResponse("OK")


# ========= 5) 4.1.1 (create_start_payment + прокладка) =========

class PlnkStartCreate(BaseModel):
    amount: float
    description: Optional[str] = None
    payment_id: Optional[str] = None
    cf1: Optional[str] = None


@router.post("/create_start_payment")
async def plnk_create_start_payment(
    body: PlnkStartCreate,
    request: Request,
    x_internal_token: Optional[str] = Header(None),
):
    if INTERNAL_TOKEN and x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not PLNK_ACCOUNT or not PLNK_SECRET1 or not PLNK_SECRET2:
        raise HTTPException(status_code=500, detail="PLNK_* secrets not configured")

    number = body.payment_id or f"plnk-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"
    amount = f"{body.amount:.2f}"
    amountcurr = PLNK_AMOUNTCURR.upper()
    currency = PLNK_PAYSYS.upper()
    trtype = "1"

    from urllib.parse import quote as _quote

    desc_raw = body.description or f"Payment {number} {amount} {amountcurr}"
    if len(desc_raw) < 6:
        desc_raw = (desc_raw + "      ")[:6]
    description = _quote(desc_raw, safe="")

    sig = _plnk_start_signature(
        amount=amount,
        amountcurr=amountcurr,
        currency=currency,
        number=number,
        description=description,
        trtype=trtype,
        account=PLNK_ACCOUNT,
        paytoken=None,
        backURL=None,
        cf1=body.cf1,
        cf2=None,
        cf3=None,
    )

    payload = {
        "account": PLNK_ACCOUNT,
        "amount": amount,
        "amountcurr": amountcurr,
        "currency": currency,
        "number": number,
        "description": description,
        "trtype": trtype,
        "signature": sig,
    }
    if body.cf1:
        payload["cf1"] = body.cf1

    headers = {
        "User-Agent": request.headers.get("user-agent", "Mozilla/5.0"),
        "True-Client-Ip": request.headers.get("x-real-ip", request.client.host if request.client else "127.0.0.1"),
        "Accept-Language": request.headers.get("accept-language", "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"),
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                PAYMENTLNK_BASE_URL + "payment/start",
                data=payload,
                headers=headers,
            )
    except httpx.RequestError as e:
        logger.error("PLNK start request error: %s", e)
        raise HTTPException(status_code=502, detail="paymentlnk unreachable")

    pay_url = r.headers.get("Location") or r.headers.get("location")

    if not pay_url:
        text = r.text or ""
        m = re.search(r"https://start\.paymentlnk\.com/[^\s\"']+", text)
        if m:
            pay_url = m.group(0)

    if not pay_url:
        logger.error("PLNK start no pay_url: code=%s body=%s", r.status_code, r.text[:500])
        raise HTTPException(status_code=502, detail="paymentlnk 4.1.1 response without pay_url")

    return {
        "pay_url": pay_url,
        "payment_id": number,
        "provider": "paymentlnk",
        "mode": "4.1.1",
    }


@router.post("/internal/create_start_link")
async def plnk_internal_create_start_link(
    body: PlnkInternalCreateLink,
    request: Request,
    x_internal_token: Optional[str] = Header(None),
):
    ttl_min = body.ttl_minutes if body.ttl_minutes else PAY_LINK_TTL_HOURS * 60
    ttl_sec = ttl_min * 60
    exp_iso = (datetime.utcnow() + timedelta(seconds=ttl_sec)).isoformat() + "Z"

    created = await plnk_create_start_payment(
        body=PlnkStartCreate(
            amount=body.amount,
            description=body.description,
            payment_id=body.payment_id,
            cf1=body.cf1,
        ),
        request=request,
        x_internal_token=x_internal_token,
    )

    pay_url = created["pay_url"]
    token = uuid.uuid4().hex

    await plnk_link_set(token, pay_url, ttl_sec)

    return {
        "public_url": f"https://pay.evpayservice.com/v2/pay/{token}",
        "token": token,
        "payment_id": created["payment_id"],
        "plnk_url": pay_url,
        "fk_url": pay_url,
        "expires_at": exp_iso,
        "provider": "paymentlnk",
        "mode": "4.1.1",
    }
