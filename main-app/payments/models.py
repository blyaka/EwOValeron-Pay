from django.db import models
from django.conf import settings

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

class Payment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    # Твой «витринный» номер
    order_id = models.CharField(max_length=32, db_index=True)
    order_prefix = models.CharField(max_length=3)
    order_date = models.DateField()
    order_seq = models.PositiveIntegerField()

    # Служебка
    payment_id = models.CharField(max_length=64, unique=True)  # = твой же order_id, прокидываем в FK
    token = models.CharField(max_length=64, unique=True)
    fk_url = models.URLField()              # прямая ссылка из FK (Location)
    public_url = models.URLField()          # твоя публичная, если есть (от pay-api)
    fk_intid = models.BigIntegerField(null=True, blank=True, db_index=True)  # из вебхука FK (intid)
    status = models.CharField(max_length=16, default="pending")
    paid_at = models.DateTimeField(null=True, blank=True)

    # Деньги и метки
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    email = models.EmailField()
    method = models.PositiveIntegerField(choices=METHOD_CHOICES, default=36)
    comment = models.CharField(max_length=140, blank=True)
    tag = models.CharField(max_length=64, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        unique_together = ("user","order_date","order_seq")

    @property
    def method_label(self):
        return dict(METHOD_CHOICES).get(self.method, str(self.method))
