import json
import logging
import httpx
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from decimal import Decimal

from .models import Payment
from payments.services import next_order_id_for

logger = logging.getLogger(__name__)

PAY_SERVICE_URL = "http://pay-api:8000/v2/internal/create_link"   # или как у тебя называется
INTERNAL_TOKEN = "changeme"  # лучше возьми из settings







@login_required
@require_POST
def create_plnk_test_link(request):
    """
    Тестовый роут для новой API PaymentLnk.
    Создаёт Payment + вызывает /v2/internal/create_link в микросервисе.
    """
    try:
        amount = Decimal(request.POST.get("amount", ""))
        email = request.POST.get("email") or request.user.email or "user@example.com"
    except Exception:
        return HttpResponseBadRequest("bad amount")

    # генерим следующий order_id как обычно
    order_id, seq, prefix, day = next_order_id_for(request.user)

    # создаём пустой payment
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
        method=999,  # специальный тестовый метод
        comment="PLNK TEST",
        expires_at=timezone.now() + timezone.timedelta(hours=24),
    )

    payload = {
        "amount": float(amount),
        "email": email,
        "phone": "",
        "cf1": f"userid:{request.user.id}",
        "description": f"Order {order_id}",
        "payment_id": p.payment_id,
        "ttl_minutes": 60,
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                PAY_SERVICE_URL,
                json=payload,
                headers={"X-Internal-Token": INTERNAL_TOKEN}
            )
    except Exception as e:
        logger.exception("PLNK create link error: %s", e)
        return JsonResponse({"ok": False, "error": "service unreachable"}, status=502)

    if resp.status_code != 200:
        return JsonResponse({"ok": False, "error": resp.text}, status=resp.status_code)

    data = resp.json()

    # обновляем Payment
    p.token = data.get("token")
    p.public_url = data.get("public_url")
    p.fk_url = data.get("plnk_url") or data.get("fk_url")
    p.save(update_fields=["token", "public_url", "fk_url"])

    return JsonResponse({
        "ok": True,
        "payment_id": p.payment_id,
        "order_id": p.order_id,
        "public_url": p.public_url,
        "fk_url": p.fk_url,
        "expires_at": p.expires_at.isoformat(),
    })







PLNK_41_URL = "http://main-app:8000/v2/internal/create_start_link"

@login_required
@require_POST
def create_plnk_start_test(request):
    """
    Тест для метода 4.1.1 (start).
    """
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
        payment_id=f"plnk-start-{order_id}",
        token="temp",
        fk_url="",
        public_url="",
        amount=amount,
        email=email,
        method=998,
        comment="PLNK START TEST",
        expires_at=timezone.now() + timezone.timedelta(hours=24),
    )

    payload = {
        "amount": float(amount),
        "email": email,
        "phone": "",
        "cf1": f"userid:{request.user.id}",
        "description": f"Order {order_id}",
        "payment_id": p.payment_id,
        "ttl_minutes": 60,
    }

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                PLNK_41_URL,
                json=payload,
                headers={"X-Internal-Token": INTERNAL_TOKEN}
            )
    except Exception as e:
        logger.exception("PLNK start error: %s", e)
        return JsonResponse({"ok": False, "error": "service unreachable"}, status=502)

    if resp.status_code != 200:
        return JsonResponse({"ok": False, "error": resp.text}, status=resp.status_code)

    data = resp.json()

    p.token = data.get("token")
    p.public_url = data.get("public_url")
    p.fk_url = data.get("plnk_url") or data.get("fk_url")
    p.save(update_fields=["token", "public_url", "fk_url"])

    return JsonResponse({
        "ok": True,
        "payment_id": p.payment_id,
        "order_id": p.order_id,
        "public_url": p.public_url,
        "fk_url": p.fk_url,
        "expires_at": p.expires_at.isoformat(),
        "mode": "4.1.1",
    })






