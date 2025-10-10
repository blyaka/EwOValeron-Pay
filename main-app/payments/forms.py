import uuid, requests
from decimal import Decimal
from datetime import datetime
from django import forms
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import Payment, METHOD_CHOICES, Tag
from .services import next_order_id_for

MIN_BY_METHOD = {36: Decimal("50.00"), 35: Decimal("50.00"), 44: Decimal("10.00")}
# BOT_EMAIL = "evopay_alert_bot@telegram.org"


class CreateLinkForm(forms.Form):
    amount = forms.DecimalField(min_value=Decimal("0.01"), max_digits=12, decimal_places=2)
    method = forms.ChoiceField(choices=METHOD_CHOICES, initial=44)
    comment = forms.CharField(max_length=140, required=False)
    ttl_minutes = forms.IntegerField(min_value=1, max_value=60*24*30, initial=60)
    tag_id = forms.IntegerField(required=False)
    email = forms.EmailField(required=True)

    def clean(self):
        c = super().clean()
        m = int(c.get("method") or 36)
        amt = c.get("amount") or Decimal("0")
        if amt < MIN_BY_METHOD.get(m, Decimal("50.00")):
            raise forms.ValidationError(f"Минимальная сумма для выбранного метода — {MIN_BY_METHOD[m]} ₽")
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

        payload = {
            "amount": float(self.cleaned_data["amount"]),
            "email": self.cleaned_data["email"],
            "ip": "0.0.0.0",
            "payment_method": int(self.cleaned_data["method"]),
            "description": self.cleaned_data.get("comment") or "",
            "payment_id": order_id,
            "ttl_minutes": int(self.cleaned_data["ttl_minutes"]),
        }

        r = requests.post(
            f"{settings.PAY_API_URL}/internal/create_link",
            json=payload,
            headers={"X-Internal-Token": settings.PAY_INTERNAL_TOKEN, "X-Idempotency-Key": idem},
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
