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
    payment_method: int = 36
    description: Optional[str] = None


@app.post("/create_order")
async def create_order(order: OrderCreate):
    # ДЕБАГ - логируем полученные переменные
    logger.info(f"FK Config: MERCHANT_ID={MERCHANT_ID}, API_KEY exists={bool(API_KEY)}")
    
    # Проверяем что переменные загружены
    if not MERCHANT_ID:
        raise HTTPException(status_code=500, detail="MERCHANT_ID not configured")
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API_KEY not configured")

    payload = {
        "shopId": int(MERCHANT_ID),  # Конвертируем в число
        "amount": order.amount,
        "currency": "RUB", 
        "paymentMethod": order.payment_method,
        "email": order.email,
        "ip": order.ip,
    }
    
    if order.description:
        payload["description"] = order.description

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    logger.info(f"Sending to FK: {payload}")  # ДЕБАГ

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                "https://api.fk.life/v1/orders", 
                json=payload, 
                headers=headers
            )
            
        logger.info(f"FK response: status={r.status_code}, body={r.text}")
            
    except httpx.RequestError as e:
        logger.error(f"FK request error: {e}")
        raise HTTPException(status_code=502, detail="FK unreachable")

    if r.status_code == 201:
        pay_url = r.headers.get("Location")
        if pay_url:
            return {"pay_url": pay_url}
        
        try:
            data = r.json()
            pay_url = data.get("location")
            if pay_url:
                return {"pay_url": pay_url}
        except Exception:
            pass
            
        raise HTTPException(status_code=500, detail="FK response without pay link")

    logger.error(f"FK error: code={r.status_code} body={r.text}")
    raise HTTPException(status_code=502, detail=f"FK error {r.status_code}")


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