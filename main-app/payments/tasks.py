# payments/tasks.py
import json, logging
from celery import shared_task
from django.utils import timezone
from payments.models import Payment
from payments.services import get_effective_commission_from_profile

logger = logging.getLogger(__name__)

@shared_task(bind=True, name="payments.handle_event")
def handle_payment_event(self, body):
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
        if not p.paid_at:
            p.paid_at = timezone.now()
        percent = get_effective_commission_from_profile(p.user, p.paid_at)
        p.apply_commission_snapshot(percent)
        if intid:
            p.fk_intid = intid
        p.save(update_fields=["status","paid_at","commission_percent","fee","payout","fk_intid"] if intid else
                           ["status","paid_at","commission_percent","fee","payout"])
    elif status in ("fail", "failed", "error", "cancel"):
        p.status = "failed"
        if intid:
            p.fk_intid = intid
            p.save(update_fields=["status","fk_intid"])
        else:
            p.save(update_fields=["status"])
    else:
        p.status = status or p.status
        if intid:
            p.fk_intid = intid
            p.save(update_fields=["status","fk_intid"])
        else:
            p.save(update_fields=["status"])

    logger.info("Payment %s => %s (intid=%s)", order_id, p.status, intid)
