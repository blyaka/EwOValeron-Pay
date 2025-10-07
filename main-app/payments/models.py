from django.db import models
from django.conf import settings
from decimal import Decimal, ROUND_HALF_UP
from django.core.validators import MinValueValidator, MaxValueValidator

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
        unique_together = ("user", "day")


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


class Tag(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tags")
    name = models.CharField(max_length=64)
    slug = models.SlugField(max_length=80)
    color = models.CharField(max_length=7, default="#a855f7")

    class Meta:
        unique_together = (("user", "slug"),)
        indexes = [models.Index(fields=["user", "name"])]

    def __str__(self):
        return self.name


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

    amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))]
    )
    email = models.EmailField()
    method = models.PositiveIntegerField(choices=METHOD_CHOICES, default=36)
    comment = models.CharField(max_length=140, blank=True)

    tag_obj = models.ForeignKey(Tag, null=True, blank=True,
                                on_delete=models.SET_NULL, related_name='payments')
    tag = models.CharField(max_length=64, blank=True)

    commission_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))])
    fee = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    payout = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        unique_together = ("user", "order_date", "order_seq")
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["user", "status", "created_at"]),
        ]
        ordering = ["-created_at"]

    @property
    def method_label(self):
        return dict(METHOD_CHOICES).get(self.method, str(self.method))

    def _qround(self, value: Decimal) -> Decimal:
        return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def apply_commission_snapshot(self, percent: Decimal):
        pct = Decimal(percent or 0)
        self.commission_percent = self._qround(pct)
        self.fee = self._qround(self.amount * pct / Decimal("100"))
        self.payout = self._qround(self.amount - self.fee)

    @property
    def tag_name(self):
        return self.tag_obj.name if self.tag_obj_id else (self.tag or None)
    
    @property
    def display_fee(self):
        # для шаблонов: "150.00 (5.00%)" или "—"
        if self.fee is None:
            return "—"
        return f"{self.fee} ({self.commission_percent}%)"

    def __str__(self):
        return f"{self.order_id} ({self.status})"
