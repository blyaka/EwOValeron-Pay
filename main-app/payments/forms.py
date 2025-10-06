import uuid, requests
from decimal import Decimal
from django import forms
from django.conf import settings
from django.utils import timezone
from .models import Payment, METHOD_CHOICES
from .services import next_order_id_for

MIN_BY_METHOD = {36: Decimal("50.00"), 35: Decimal("50.00"), 44: Decimal("10.00")}

class CreateLinkForm(forms.Form):
    amount = forms.DecimalField(min_value=Decimal("0.01"), max_digits=12, decimal_places=2)
    email = forms.EmailField()
    method = forms.ChoiceField(choices=METHOD_CHOICES, initial=36)
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

        # генерим ИДЕМПОТЕНТНЫЙ токен для этого вызова
        idem = uuid.uuid4().hex

        payload = {
            "amount": float(self.cleaned_data["amount"]),
            "email": self.cleaned_data["email"],
            "ip": "0.0.0.0",
            "payment_method": int(self.cleaned_data["method"]),
            "description": self.cleaned_data.get("comment") or "",
            "payment_id": order_id,           # наш ID пойдет в FK как paymentId
        }

        r = requests.post(
            f"{settings.PAY_API_URL}/create_order",
            json=payload,
            headers={
                "X-Internal-Token": settings.PAY_INTERNAL_TOKEN,
                "X-Idempotency-Key": idem,    # <-- ключ идемпотентности
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()  # {"pay_url": "...", "payment_id": "..."}

        p = Payment.objects.create(
            user=user,
            payment_id=data["payment_id"],     # = order_id
            token=idem,                        # сохраняем idem у себя
            fk_url=data["pay_url"],
            public_url=data["pay_url"],
            amount=self.cleaned_data["amount"],
            email=self.cleaned_data["email"],
            method=int(self.cleaned_data["method"]),
            comment=self.cleaned_data.get("comment",""),
            tag=self.cleaned_data.get("tag",""),
            status="pending",
            expires_at=timezone.now() + timezone.timedelta(
                hours=int(getattr(settings,"PAY_LINK_TTL_HOURS",24))
            ),
            order_prefix=prefix,
            order_date=day,
            order_seq=seq,
            order_id=order_id,
        )
        return p
