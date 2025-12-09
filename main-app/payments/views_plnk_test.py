# payments/views_plnk_test.py
import logging
import httpx
import uuid
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
    print("==== PLNK_TEST: ENTER VIEW ====")
    print("PATH:", request.path)
    print("METHOD:", request.method)
    print("USER:", request.user.id, request.user.username)
    print("CONTENT_TYPE:", request.META.get("CONTENT_TYPE"))
    print("POST RAW:", dict(request.POST))
    print("INTERNAL_TOKEN_EMPTY?:", not bool(INTERNAL_TOKEN))

    if request.user.username != "jigor":
        print("PLNK_TEST: forbidden user")
        return HttpResponseForbidden("only for owner")

    try:
        raw_amount = request.POST.get("amount", "")
        print("PLNK_TEST: raw_amount =", repr(raw_amount))

        amount = Decimal(raw_amount)
        email = request.POST.get("email") or request.user.email or "user@example.com"

        print("PLNK_TEST: parsed amount =", amount)
        print("PLNK_TEST: email =", email)

    except Exception as e:
        print("PLNK_TEST: BAD AMOUNT ERROR:", repr(e))
        return HttpResponseBadRequest("bad amount")

    order_id, seq, prefix, day = next_order_id_for(request.user)
    print(
        "PLNK_TEST: next_order_id_for ->",
        "order_id=", order_id,
        "seq=", seq,
        "prefix=", prefix,
        "day=", day,
    )

    # генерим уникальный токен, чтобы не ловить UNIQUE CONSTRAINT на token
    initial_token = f"plnk-{uuid.uuid4().hex}"

    p = Payment.objects.create(
        user=request.user,
        order_id=order_id,
        order_seq=seq,
        order_prefix=prefix,
        order_date=day,
        payment_id=f"plnk-{order_id}",
        token=initial_token,
        fk_url="",
        public_url="",
        amount=amount,
        email=email,
        method=999,
        comment=request.POST.get("comment") or "PLNK TEST",
        expires_at=timezone.now() + timezone.timedelta(hours=24),
    )
    print("PLNK_TEST: Payment created, id=", p.id, "payment_id=", p.payment_id, "token=", p.token)

    ttl_raw = request.POST.get("ttl_minutes")
    ttl_minutes = int(ttl_raw or 60)
    print("PLNK_TEST: ttl_raw =", repr(ttl_raw), " -> ttl_minutes =", ttl_minutes)

    payload = {
        "amount": float(amount),
        "email": email,
        "phone": "",
        "cf1": f"userid:{request.user.id}",
        "description": f"Order {order_id}",
        "payment_id": p.payment_id,
        "ttl_minutes": ttl_minutes,
    }

    print("PLNK_TEST: PAYLOAD TO PAY-API:", payload)
    print("PLNK_TEST: PAY_SERVICE_URL:", PAY_SERVICE_URL)

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                PAY_SERVICE_URL,
                json=payload,
                headers={"X-Internal-Token": INTERNAL_TOKEN},
            )
    except Exception as e:
        print("PLNK_TEST: httpx EXCEPTION:", repr(e))
        logger.exception("PLNK create link error (httpx): %s", e)
        return JsonResponse({"ok": False, "error": "service unreachable"}, status=502)

    print("PLNK_TEST: pay-api RESP STATUS:", resp.status_code)
    print("PLNK_TEST: pay-api RESP HEADERS:", dict(resp.headers))
    text = resp.text
    ctype = resp.headers.get("content-type", "")
    print("PLNK_TEST: pay-api RESP CONTENT-TYPE:", ctype)
    print("PLNK_TEST: pay-api RESP TEXT FIRST 500:", text[:500])

    if resp.status_code != 200:
        logger.error("PLNK create_link non-200: %s %s", resp.status_code, text[:500])
        return JsonResponse(
            {"ok": False, "error": f"pay-api {resp.status_code}: {text[:200]}"},
            status=resp.status_code,
        )

    try:
        data = resp.json()
        print("PLNK_TEST: pay-api RESP JSON:", data)
    except ValueError as e:
        print("PLNK_TEST: JSON DECODE ERROR:", repr(e))
        logger.error(
            "PLNK create_link non-json: ct=%s body=%s",
            ctype,
            text[:500],
        )
        return JsonResponse(
            {"ok": False, "error": "pay-api returned non-json"},
            status=502,
        )

    api_token = data.get("token")
    if api_token:
        # если pay-api вернул токен — сохраняем его
        p.token = api_token
    else:
        # если не вернул — оставляем сгенерированный initial_token
        print("PLNK_TEST: pay-api did not return token, keep initial_token:", initial_token)

    p.public_url = data.get("public_url") or ""
    p.fk_url = data.get("plnk_url") or data.get("fk_url") or ""
    p.save(update_fields=["token", "public_url", "fk_url"])

    print(
        "PLNK_TEST: Payment updated:",
        "token=", p.token,
        "public_url=", p.public_url,
        "fk_url=", p.fk_url,
    )

    resp_data = {
        "ok": True,
        "payment_id": p.payment_id,
        "order_id": p.order_id,
        "public_url": p.public_url,
        "fk_url": p.fk_url,
        "amount": str(p.amount),
        "comment": p.comment,
        "expires_at": p.expires_at.isoformat(),
    }
    print("PLNK_TEST: RESPONSE TO FRONT:", resp_data)

    return JsonResponse(resp_data)
