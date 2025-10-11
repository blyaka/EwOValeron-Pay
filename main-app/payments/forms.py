from decimal import Decimal
from datetime import datetime
import uuid, requests, time, logging
from django import forms
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import Payment, Tag
from .services import next_order_id_for
from core.models import PaymentMethod

log = logging.getLogger(__name__)

def method_choices():
    return [(m.id, f"{m.id} — {m.name}") for m in PaymentMethod.objects.filter(is_active=True).order_by("sort","id")]

def min_by_method_map():
    return {m.id: m.min_amount for m in PaymentMethod.objects.all()}

class CreateLinkForm(forms.Form):
    amount = forms.DecimalField(min_value=Decimal("0.01"), max_digits=12, decimal_places=2)
    method = forms.ChoiceField(choices=method_choices, initial=44)
    comment = forms.CharField(max_length=140, required=False)
    ttl_minutes = forms.IntegerField(min_value=1, max_value=60*24*30, initial=60)
    tag_id = forms.IntegerField(required=False)
    email = forms.EmailField(required=True)

    def clean(self):
        c = super().clean()
        m = int(c.get("method") or 36)
        amt = c.get("amount") or Decimal("0")

        methods = min_by_method_map()
        min_amt = methods.get(m, Decimal("50.00"))
        if amt < min_amt:
            raise forms.ValidationError(f"Минимальная сумма для выбранного метода — {min_amt} ₽")

        tid = c.get("tag_id")
        if tid is not None:
            if tid == "":
                c["tag_id"] = None
            else:
                try:
                    c["tag_id"] = int(tid)
                except (TypeError, ValueError):
                    raise forms.ValidationError("Некорректный tag_id")
        return c

    def save(self, user) -> Payment:
        tag_obj = None
        tid = self.cleaned_data.get("tag_id")
        if tid:
            try:
                tag_obj = Tag.objects.get(user=user, id=tid)
            except Tag.DoesNotExist:
                tag_obj = None

        order_id, seq, prefix, day = next_order_id_for(user)
        idem = uuid.uuid4().hex

        amt = Decimal(self.cleaned_data["amount"]).quantize(Decimal("0.01"))
        payload = {
            "amount": float(amt),
            "email": self.cleaned_data["email"],
            "ip": "0.0.0.0",
            "payment_method": int(self.cleaned_data["method"]),
            "description": self.cleaned_data.get("comment") or "",
            "payment_id": order_id,
            "ttl_minutes": int(self.cleaned_data["ttl_minutes"]),
        }

        t0 = time.time()
        r = requests.post(
            f"{settings.PAY_API_URL}/internal/create_link",
            json=payload,
            headers={"X-Internal-Token": settings.PAY_INTERNAL_TOKEN, "X-Idempotency-Key": idem},
            timeout=(3, 25),
        )
        log.info("pay-api create_link %s in %.3fs -> %s %s",
                 order_id, time.time() - t0, r.status_code, (r.text or "")[:200])
        r.raise_for_status()
        data = r.json()
        exp = data.get("expires_at")
        if exp:
            try:
                dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                if timezone.is_naive(dt):
                    dt = timezone.make_aware(dt, timezone.utc)
                expires_at = dt
            except Exception:
                expires_at = timezone.now() + timezone.timedelta(minutes=int(self.cleaned_data["ttl_minutes"]))
        else:
            expires_at = timezone.now() + timezone.timedelta(minutes=int(self.cleaned_data["ttl_minutes"]))

        p = Payment.objects.create(
            user=user,
            payment_id=data["payment_id"],
            token=data["token"],
            fk_url=data["fk_url"],
            public_url=data["public_url"],
            amount=self.cleaned_data["amount"],
            email=self.cleaned_data["email"],
            method=int(self.cleaned_data["method"]),
            comment=self.cleaned_data.get("comment", ""),
            tag="",
            status="pending",
            expires_at=expires_at,
            order_prefix=prefix,
            order_date=day,
            order_seq=seq,
            order_id=order_id,
        )
        if tag_obj:
            p.tag_obj = tag_obj
            p.save(update_fields=["tag_obj"])
        return p
