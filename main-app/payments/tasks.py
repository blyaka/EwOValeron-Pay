import json
import logging
from celery import shared_task
from payments.models import Payment

logger = logging.getLogger(__name__)

@shared_task(bind=True, name="payments.handle_event")
def handle_payment_event(self, body):
    import json, logging
    from payments.models import Payment
    logger = logging.getLogger(__name__)
    data = json.loads(body) if isinstance(body, str) else body

    order_id = data.get("order_id")
    status = (data.get("status") or "").lower()
    intid = data.get("intid") or ""

    if not order_id:
        logger.warning("Event without order_id: %s", data); return

    try:
        p = Payment.objects.get(order_id=order_id)
    except Payment.DoesNotExist:
        logger.warning("Payment not found: %s", order_id); return

    if status in ("success", "paid", "completed"):
        p.status = "paid"
    elif status in ("fail", "failed", "error", "cancel"):
        p.status = "failed"
    else:
        p.status = status or p.status

    if hasattr(p, "fk_intid") and intid:
        p.fk_intid = intid
        p.save(update_fields=["status", "fk_intid"])
    else:
        p.save(update_fields=["status"])

    logger.info("Payment %s => %s (intid=%s)", order_id, p.status, intid)

