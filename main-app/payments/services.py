from django.utils import timezone
from django.db import transaction
from .models import SellerDayCounter

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