from fastapi import FastAPI

import aio_pika
import asyncio
import os



RABBIT_URL = os.getenv("RABBIT_URL", "amqp://user:pass@rabbit:5672/")

app = FastAPI()

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
    connection = await aio_pika.connect_robust(RABBIT_URL)
    channel = await connection.channel()
    queue = await channel.declare_queue("test", durable=True)
    await channel.default_exchange.publish(
        aio_pika.Message(body=msg.encode()),
        routing_key=queue.name
    )
    await connection.close()
    return {"sent": msg}