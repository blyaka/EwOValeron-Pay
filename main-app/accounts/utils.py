import re, string
from django.db import transaction
from .models import SellerProfile

def alloc_prefix_for(user) -> str:
    base = re.sub(r"[^A-Za-z0-9]", "", user.username).upper()[:3] or "USR"
    base = (base + "XXX")[:3]
    candidates = [base] + [(base[:2] + d) for d in "123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
    with transaction.atomic():
        for cand in candidates:
            if not SellerProfile.objects.select_for_update().filter(order_prefix=cand).exists():
                SellerProfile.objects.create(user=user, order_prefix=cand)
                return cand
    for ch in string.ascii_uppercase:
        cand = base[:2] + ch
        if not SellerProfile.objects.filter(order_prefix=cand).exists():
            SellerProfile.objects.create(user=user, order_prefix=cand)
            return cand
    raise RuntimeError("Не удалось выдать уникальный префикс")
