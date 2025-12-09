# payments/views_plnk_test.py
import logging
import httpx
from decimal import Decimal

from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from .models import Payment
from payments.services import next_order_id_for

logger = logging.getLogger(__name__)

PAY_SERVICE_URL = "http://pay-api:8000/v2/internal/create_link"
PLNK_41_URL     = "http://pay-api:8000/v2/internal/create_start_link"
INTERNAL_TOKEN  = getattr(settings, "PAY_INTERNAL_TOKEN", "")


@login_required
@require_POST
def create_plnk_test_link(request):
    if request.user.username != "jigor":
        return HttpResponseForbidden("only for owner")

    try:
        amount = Decimal(request.POST.get("amount", ""))
        email = request.POST.get("email") or request.user.email or "user@example.com"
    except Exception:
        return HttpResponseBadRequest("bad amount")

    order_id, seq, prefix, day = next_order_id_for(request.user)

    p = Payment.objects.create(
        user=request.user,
        order_id=order_id,
        order_seq=seq,
        order_prefix=prefix,
        order_date=day,
        payment_id=f"plnk-{order_id}",
        token="temp",
        fk_url="",
        public_url="",
        amount=amount,
        email=email,
        method=999,
        comment=request.POST.get("comment") or "PLNK TEST",
        expires_at=timezone.now() + timezone.timedelta(hours=24),
    )

    payload = {
        "amount": float(amount),
        "email": email,
        "phone": "",
        "cf1": f"userid:{request.user.id}",
        "description": f"Order {order_id}",
        "payment_id": p.payment_id,
        "ttl_minutes": int(request.POST.get("ttl_minutes") or 60),
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                PAY_SERVICE_URL,
                json=payload,
                headers={"X-Internal-Token": INTERNAL_TOKEN},
            )
    except Exception as e:
        logger.exception("PLNK create link error (httpx): %s", e)
        return JsonResponse({"ok": False, "error": "service unreachable"}, status=502)

    text = resp.text
    ctype = resp.headers.get("content-type", "")

    if resp.status_code != 200:
        logger.error("PLNK create_link non-200: %s %s", resp.status_code, text[:500])
        return JsonResponse(
            {"ok": False, "error": f"pay-api {resp.status_code}: {text[:200]}"},
            status=resp.status_code,
        )

    try:
        data = resp.json()
    except ValueError:
        logger.error(
            "PLNK create_link non-json: ct=%s body=%s",
            ctype,
            text[:500],
        )
        return JsonResponse(
            {"ok": False, "error": "pay-api returned non-json"},
            status=502,
        )

    p.token = data.get("token") or ""
    p.public_url = data.get("public_url") or ""
    p.fk_url = data.get("plnk_url") or data.get("fk_url") or ""
    p.save(update_fields=["token", "public_url", "fk_url"])

    return JsonResponse({
        "ok": True,
        "payment_id": p.payment_id,
        "order_id": p.order_id,
        "public_url": p.public_url,
        "fk_url": p.fk_url,
        "amount": str(p.amount),
        "comment": p.comment,
        "expires_at": p.expires_at.isoformat(),
    })


