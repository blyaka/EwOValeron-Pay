import os, json, logging, decimal, requests
from celery import shared_task
from django.utils import timezone
from django.db import transaction

from payments.models import Payment
from payments.services import get_effective_commission_from_profile
from accounts.models import TelegramAccount  # привязка TG тут

logger = logging.getLogger(__name__)

TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_API = os.getenv("TELEGRAM_BOT_API_URL", "https://api.telegram.org")


def _fmt_rub(amount: decimal.Decimal | float | int) -> str:
    try:
        v = decimal.Decimal(amount).quantize(decimal.Decimal("1"))
    except Exception:
        v = decimal.Decimal(0)
    return f"{v:,.0f}".replace(",", " ")


@shared_task(bind=True, name="notifications.send_tg_message", max_retries=3, default_retry_delay=5)
def send_tg_message(self, telegram_id: int, text: str):
    if not TG_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN is missing; skip message")
        return
    try:
        r = requests.post(
            f"{TG_API}/bot{TG_TOKEN}/sendMessage",
            json={
                "chat_id": telegram_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=10
        )
        if r.status_code != 200:
            raise RuntimeError(f"TG sendMessage {r.status_code}: {r.text}")
    except Exception as e:
        logger.exception("Failed to send tg message: %s", e)
        raise self.retry(exc=e)


@shared_task(bind=True, name="notifications.payment_paid")
def notify_payment_paid(self, payment_id: int):
    try:
        p = Payment.objects.select_related("user").get(id=payment_id)
    except Payment.DoesNotExist:
        return

    tg: TelegramAccount | None = getattr(p.user, "tg", None)
    if not tg:
        logger.info("User %s has no Telegram linked; skip", p.user_id)
        return

    email = p.email or "—"
    txt = (
        f"Заказ <b>{p.order_id}</b> оплачен!\n"
        f"Сумма: <b>{_fmt_rub(p.amount)} рублей</b>\n"
        f"Почта: <b>{email}</b>"
    )
    send_tg_message.delay(tg.telegram_id, txt)


@shared_task(bind=True, name="payments.handle_event")
def handle_payment_event(self, body):
    data = json.loads(body) if isinstance(body, str) else body
    order_id = data.get("order_id")
    status = (data.get("status") or "").lower()
    intid = data.get("intid") or ""

    if not order_id:
        logger.warning("Event without order_id: %s", data)
        return

    try:
        p = Payment.objects.get(order_id=order_id)
    except Payment.DoesNotExist:
        logger.warning("Payment not found: %s", order_id)
        return

    was_paid = bool(p.paid_at)

    if status in ("success", "paid", "completed"):
        p.status = "paid"
        if not p.paid_at:
            p.paid_at = timezone.now()

        percent = get_effective_commission_from_profile(p.user, p.paid_at)
        p.apply_commission_snapshot(percent)

        if intid:
            p.fk_intid = intid

        update_fields = ["status", "paid_at", "commission_percent", "fee", "payout"]
        if intid:
            update_fields.append("fk_intid")

        with transaction.atomic():
            p.save(update_fields=update_fields)
            if not was_paid:
                notify_payment_paid.delay(p.id)

    elif status in ("fail", "failed", "error", "cancel"):
        p.status = "failed"
        if intid:
            p.fk_intid = intid
            p.save(update_fields=["status", "fk_intid"])
        else:
            p.save(update_fields=["status"])
    else:
        p.status = status or p.status
        if intid:
            p.fk_intid = intid
            p.save(update_fields=["status", "fk_intid"])
        else:
            p.save(update_fields=["status"])

    logger.info("Payment %s => %s (intid=%s)", order_id, p.status, intid)
