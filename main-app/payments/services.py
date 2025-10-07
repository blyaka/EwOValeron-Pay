from django.utils import timezone
from django.db import transaction
from .models import SellerDayCounter, SellerCommission
from decimal import Decimal
from django.conf import settings

def next_order_id_for(user):
    today = timezone.now().date()
    with transaction.atomic():
        row, _ = SellerDayCounter.objects.select_for_update().get_or_create(
            user=user, day=today, defaults={"last_seq":0}
        )
        row.last_seq += 1
        row.save(update_fields=["last_seq"])
        prefix = user.seller.order_prefix
        order_id = f"{prefix}-{today.strftime('%Y%m%d')}-{row.last_seq:02d}"
        return order_id, row.last_seq, prefix, today
    


def preview_next_order_id_for(user):
    today = timezone.now().date()
    row, _ = SellerDayCounter.objects.get_or_create(
        user=user, day=today, defaults={"last_seq": 0}
    )
    prefix = user.seller.order_prefix
    next_seq = row.last_seq + 1
    order_id = f"{prefix}-{today.strftime('%Y%m%d')}-{next_seq:02d}"
    return order_id, next_seq, prefix, today



def get_effective_commission_from_profile(user, when=None) -> Decimal:
    sp = getattr(user, "seller", None)
    return Decimal(getattr(sp, "commission_pct", 0) or 0)