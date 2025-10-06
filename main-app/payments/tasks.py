import json
import logging
from celery import shared_task
from payments.models import Payment

logger = logging.getLogger(__name__)

@shared_task(bind=True, name="payments.handle_event")
def handle_payment_event(self, body):
    try:
        data = json.loads(body) if isinstance(body, str) else body
        order_id = data.get("order_id")
        status = data.get("status")

        if not order_id:
            logger.warning("Payment event without order_id: %s", data)
            return

        try:
            p = Payment.objects.get(order_id=order_id)
        except Payment.DoesNotExist:
            logger.warning("Payment not found for event: %s", order_id)
            return

        if status.lower() == "success":
            p.status = "paid"
        elif status.lower() == "failed":
            p.status = "failed"
        else:
            p.status = status.lower()
        p.save(update_fields=["status"])
        logger.info("Payment %s updated to %s", order_id, p.status)
    except Exception as e:
        logger.exception("Failed to handle event: %s", e)
