import asyncio
import json
import aio_pika
from django.core.management.base import BaseCommand
from payments.tasks import handle_payment_event

class Command(BaseCommand):
    help = "Listen for payment events from RabbitMQ"

    async def listen(self):
        conn = await aio_pika.connect_robust("amqp://user:pass@rabbit:5672/")
        ch = await conn.channel()
        q = await ch.declare_queue("payments.events", durable=True)
        async with q.iterator() as queue_iter:
            async for msg in queue_iter:
                async with msg.process():
                    handle_payment_event.delay(msg.body.decode())

    def handle(self, *args, **options):
        asyncio.run(self.listen())
