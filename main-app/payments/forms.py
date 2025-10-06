import uuid, requests
from decimal import Decimal
from datetime import datetime
from django import forms
from django.conf import settings
from django.utils import timezone
from .models import Payment, METHOD_CHOICES
from .services import next_order_id_for

MIN_BY_METHOD = {36: Decimal("50.00"), 35: Decimal("50.00"), 44: Decimal("10.00")}
BOT_EMAIL = "evopay_alert_bot@telegram.org"

class CreateLinkForm(forms.Form):
    amount = forms.DecimalField(min_value=Decimal("0.01"), max_digits=12, decimal_places=2)
    method = forms.ChoiceField(choices=METHOD_CHOICES, initial=44)
    comment = forms.CharField(max_length=140, required=False)
    tag = forms.CharField(max_length=64, required=False)

    def clean(self):
        c = super().clean()
        m = int(c.get("method") or 36)
        amt = c.get("amount") or Decimal("0")
        if amt < MIN_BY_METHOD.get(m, Decimal("50.00")):
            raise forms.ValidationError(f"Минимальная сумма для выбранного метода — {MIN_BY_METHOD[m]} ₽")
        return c

    def save(self, user) -> Payment:
        order_id, seq, prefix, day = next_order_id_for(user)
        idem = uuid.uuid4().hex

        payload = {
            "amount": float(self.cleaned_data["amount"]),
            "email": BOT_EMAIL,
            "ip": "0.0.0.0",
            "payment_method": int(self.cleaned_data["method"]),
            "description": self.cleaned_data.get("comment") or "",
            "payment_id": order_id,
        }

        r = requests.post(
            f"{settings.PAY_API_URL}/internal/create_link",
            json=payload,
            headers={
                "X-Internal-Token": settings.PAY_INTERNAL_TOKEN,
                "X-Idempotency-Key": idem,
            },
            timeout=10,
        )
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
                expires_at = timezone.now() + timezone.timedelta(
                    hours=int(getattr(settings, "PAY_LINK_TTL_HOURS", 24))
                )
        else:
            expires_at = timezone.now() + timezone.timedelta(
                hours=int(getattr(settings, "PAY_LINK_TTL_HOURS", 24))
            )

        p = Payment.objects.create(
            user=user,
            payment_id=data["payment_id"],
            token=data["token"],
            fk_url=data["fk_url"],
            public_url=data["public_url"],
            amount=self.cleaned_data["amount"],
            email=BOT_EMAIL,
            method=int(self.cleaned_data["method"]),
            comment=self.cleaned_data.get("comment", ""),
            tag=self.cleaned_data.get("tag", ""),
            status="pending",
            expires_at=expires_at,
            order_prefix=prefix,
            order_date=day,
            order_seq=seq,
            order_id=order_id,
        )
        return p
