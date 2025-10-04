# main.py (правки точечные)
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
FREKASSA_URL = "https://api.fk.life/v1/"

app = FastAPI()

MERCHANT_ID = os.getenv("FREKASSA_MERCHANT_ID")
API_KEY = os.getenv("FREKASSA_API_KEY")
SECRET_KEY = os.getenv("FREKASSA_SECRET_KEY")

# --- утилиты ---
def fk_sign(order_id: str, amount: str, currency: str, secret: str) -> str:
    # по их схеме: orderId:amount:currency:SECRET  → HMAC-SHA256 hex
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
@app.post("/create_order")
async def create_order(amount: float, email: str, ip: str, payment_method: int = 36, description: Optional[str] = None):
    payload = {
        "shopId": MERCHANT_ID,
        "amount": f"{amount:.2f}",     # строкой, с 2 знаками
        "currency": "RUB",
        "email": email,                # real email или <tgid>@telegram.org
        "ip": ip,                      # реальный IP клиента (или серверный временно)
        "i": payment_method,           # 36 карты, 44 QR СБП, 43 SberPay
    }
    if description:
        payload["description"] = description

    headers = {"Authorization": f"Bearer {API_KEY}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(FREKASSA_URL + "orders", json=payload, headers=headers)
        r.raise_for_status()

    data = r.json()
    # в ответе ссылка обычно в поле Location / location
    pay_url = data.get("location") or data.get("Location")
    if not pay_url:
        raise HTTPException(status_code=500, detail=f"FK response without location: {data}")
    return {"pay_url": pay_url}

# ============ 2) Вебхук ============
@app.post("/webhook", response_class=PlainTextResponse)
async def webhook(request: Request):
    # могут прислать JSON или form; пытаемся оба варианта
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        data = await request.json()
    else:
        form = await request.form()
        data = dict(form)

    # обязательные поля
    try:
        order_id = str(data["orderId"])
        amount = str(data["amount"])
        currency = str(data["currency"])
        got_sign = str(data.get("sign") or data.get("signature"))
        status = str(data.get("status", ""))   # success / failed / pending
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing field: {e}")

    must = fk_sign(order_id, amount, currency, SECRET_KEY)
    if not cd(got_sign, must):
        raise HTTPException(status_code=400, detail="Invalid signature")

    # публикуем событие в Rabbit (идемпотентность решай в консюмере/БД)
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
            aio_pika.Message(body=json.dumps(event, ensure_ascii=False).encode(), delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
            routing_key="payments.events",
        )
        await conn.close()
    except Exception:
        # не роняем вебхук из-за брокера; логируй при желании
        pass

    # FreeKassa ожидает текст "OK" (без JSON), чтобы не ретраить
    return "OK"
