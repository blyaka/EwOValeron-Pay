from django.db import models
from django.conf import settings

class SellerDayCounter(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    day = models.DateField()
    last_seq = models.PositiveIntegerField(default=0)
    class Meta:
        unique_together = ("user","day")

class Payment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    order_id = models.CharField(max_length=32, db_index=True)
    order_prefix = models.CharField(max_length=3)
    order_date = models.DateField()
    order_seq = models.PositiveIntegerField()

    payment_id = models.CharField(max_length=64, unique=True)
    token = models.CharField(max_length=64, unique=True)
    fk_url = models.URLField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    email = models.EmailField()
    method = models.PositiveIntegerField(default=36)
    comment = models.CharField(max_length=140, blank=True)
    tag = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=16, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        unique_together = ("user","order_date","order_seq")
