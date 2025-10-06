import uuid, requests
from django import forms
from django.conf import settings
from django.utils import timezone
from .models import Payment
from .services import next_order_id_for

class CreateLinkForm(forms.Form):
    amount = forms.DecimalField(min_value=0.01, max_digits=12, decimal_places=2)
    email = forms.EmailField()
    method = forms.IntegerField(initial=36)
    comment = forms.CharField(max_length=140, required=False)
    tag = forms.CharField(max_length=64, required=False)

    def save(self, user) -> Payment:
        order_id, seq, prefix, day = next_order_id_for(user)
        idem = uuid.uuid4().hex
        payload = {
            "amount": float(self.cleaned_data["amount"]),
            "email": self.cleaned_data["email"],
            "ip": "0.0.0.0",
            "payment_method": int(self.cleaned_data["method"]),
            "description": self.cleaned_data.get("comment") or "",
            "payment_id": order_id,
        }
        r = requests.post(
            f"{settings.PAY_API_URL}/internal/create_link",
            json=payload,
            headers={"X-Internal-Token": settings.PAY_INTERNAL_TOKEN,
                     "X-Idempotency-Key": idem},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()  # {"public_url","token","payment_id","fk_url","expires_at"}

        p = Payment.objects.create(
            user=user,
            payment_id=data["payment_id"],
            token=data["token"],
            fk_url=data["fk_url"],
            amount=self.cleaned_data["amount"],
            email=self.cleaned_data["email"],
            method=self.cleaned_data["method"],
            comment=self.cleaned_data.get("comment",""),
            tag=self.cleaned_data.get("tag",""),
            status="pending",
            expires_at=timezone.now() + timezone.timedelta(hours=int(getattr(settings,"PAY_LINK_TTL_HOURS",24))),
            order_prefix=prefix,
            order_date=day,
            order_seq=seq,
            order_id=order_id,
        )
        return p