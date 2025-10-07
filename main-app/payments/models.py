from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP

METHOD_CHOICES = (
    (36, "Карты (VISA/MasterCard/МИР)"),
    (35, "QIWI"),
    (44, "СБП"),
)

class SellerDayCounter(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    day = models.DateField()
    last_seq = models.PositiveIntegerField(default=0)
    class Meta:
        unique_together = ("user","day")

class SellerCommission(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="commission_history")
    percent = models.DecimalField(max_digits=5, decimal_places=2)
    effective_from = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "effective_from"])]
        ordering = ["-effective_from"]

    def __str__(self):
        return f"{self.user} {self.percent}% с {self.effective_from}"

class Payment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    order_id = models.CharField(max_length=32, db_index=True)
    order_prefix = models.CharField(max_length=3)
    order_date = models.DateField()
    order_seq = models.PositiveIntegerField()

    payment_id = models.CharField(max_length=64, unique=True)
    token = models.CharField(max_length=64, unique=True)
    fk_url = models.URLField()
    public_url = models.URLField()
    fk_intid = models.BigIntegerField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=16, default="pending")
    paid_at = models.DateTimeField(null=True, blank=True)

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    email = models.EmailField()
    method = models.PositiveIntegerField(choices=METHOD_CHOICES, default=36)
    comment = models.CharField(max_length=140, blank=True)
    tag = models.CharField(max_length=64, blank=True)


    commission_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fee = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    payout = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        unique_together = ("user","order_date","order_seq")

    @property
    def method_label(self):
        return dict(METHOD_CHOICES).get(self.method, str(self.method))

    def _qround(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def apply_commission_snapshot(self, percent: Decimal):
        self.commission_percent = self._qround(Decimal(percent))
        self.fee = self._qround(self.amount * self.commission_percent / Decimal("100"))
        self.payout = self._qround(self.amount - self.fee)
