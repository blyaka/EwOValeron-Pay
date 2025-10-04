# main.py
import hashlib
import hmac
import json
import os
from typing import Optional

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
import aio_pika

RABBIT_URL = os.getenv("RABBIT_URL", "amqp://user:pass@rabbit:5672/")
FREKASSA_BASE_URL = "https://api.fk.life/v1/"

app = FastAPI()

MERCHANT_ID = os.getenv("FREKASSA_MERCHANT_ID")
API_KEY = os.getenv("FREKASSA_API_KEY")
SECRET_KEY = os.getenv("FREKASSA_SECRET_KEY")

# --- утилиты ---
def fk_sign(order_id: str, amount: str, currency: str, secret: str) -> str:
    payload = f"{order_id}:{amount}:{currency}:{secret}".encode()
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

def cd(a: str, b: str) -> bool:
    return hmac.compare_digest(a.lower(), b.lower())

@app.get("/")
async def root():
    return {"status": "ok"}

@app.get("/health")
async def health():
    return {"health": "ok"}

@app.get("/ping")
async def ping():
    return {"pong": True}

@app.post("/send")
async def send(msg: str):
    conn = await aio_pika.connect_robust(RABBIT_URL)
    ch = await conn.channel()
    q = await ch.declare_queue("test", durable=True)
    await ch.default_exchange.publish(aio_pika.Message(body=msg.encode()), routing_key=q.name)
    await conn.close()
    return {"sent": msg}

# ============ 1) Создание заказа ============
from pydantic import BaseModel
import logging
logger = logging.getLogger("uvicorn.error")

class OrderCreate(BaseModel):
    amount: float
    email: str
    ip: str
    payment_method: int = 36  # 36 — карты РФ, 44 — QR СБП, 43 — SberPay
    description: Optional[str] = None

FREKASSA_BASE_URL = "https://api.fk.life/v1/"

@app.post("/create_order")
async def create_order(order: OrderCreate):
    if not MERCHANT_ID:
        raise HTTPException(status_code=500, detail="MERCHANT_ID not configured")
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API_KEY not configured")

    payload = {
        "shopId": int(MERCHANT_ID),            # ID кассы
        "amount": f"{order.amount:.2f}",       # строка "10.00"
        "currency": "RUB",
        "email": order.email,                  # реальный email или <tgid>@telegram.org
        "ip": order.ip,                        # реальный IP клиента (или сервера временно)
        "i": order.payment_method,             # способ оплаты (ТАК ТРЕБУЕТ FK)
    }
    if order.description:
        payload["description"] = order.description

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    logger.info(f"FK order req: {payload}")

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(FREKASSA_BASE_URL + "orders", json=payload, headers=headers)
    except httpx.RequestError as e:
        logger.error(f"FK request error: {e}")
        raise HTTPException(status_code=502, detail="FK unreachable")

    # Успех: 201 (или 200/202 у некоторых шлюзов)
    if r.status_code in (200, 201, 202):
        pay_url = r.headers.get("Location") or r.headers.get("location")
        if not pay_url:
            # на всякий случай попробуем тело
            try:
                data = r.json()
                pay_url = data.get("location") or data.get("Location")
            except Exception:
                pass
        if not pay_url:
            logger.error(f"FK no pay link: code={r.status_code} body={r.text[:500]}")
            raise HTTPException(status_code=500, detail="FK response without pay link")
        return {"pay_url": pay_url}

    # Ошибка от FK — вернём тело для дебага
    logger.error(f"FK error {r.status_code}: {r.text[:800]}")
    raise HTTPException(status_code=502, detail=f"FK error {r.status_code}: {r.text[:300]}")



# ============ 2) Вебхук ============
@app.post("/webhook", response_class=PlainTextResponse)
async def webhook(request: Request):
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        data = await request.json()
    else:
        form = await request.form()
        data = dict(form)

    try:
        order_id = str(data["orderId"])
        amount = str(data["amount"])
        currency = str(data["currency"])
        got_sign = str(data.get("sign") or data.get("signature"))
        status = str(data.get("status", ""))
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing field: {e}")

    must = fk_sign(order_id, amount, currency, SECRET_KEY)
    if not cd(got_sign, must):
        raise HTTPException(status_code=400, detail="Invalid signature")

    event = {
        "provider": "freekassa",
        "order_id": order_id,
        "amount": amount,
        "currency": currency,
        "status": status,
        "raw": data,
    }
    
    try:
        conn = await aio_pika.connect_robust(RABBIT_URL)
        ch = await conn.channel()
        await ch.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(event, ensure_ascii=False).encode(), 
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key="payments.events",
        )
        await conn.close()
    except Exception as e:
        logger.error(f"RabbitMQ error: {e}")

    return "OK"