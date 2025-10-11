import uuid
from django.db import models, transaction
from django.utils import timezone
from django.db.models import Q
from decimal import Decimal

class MaintenanceBanner(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    text = models.CharField("Текст уведомления", max_length=255)
    is_active = models.BooleanField("Показывать", default=False)
    starts_at = models.DateTimeField("Начало", null=True, blank=True)
    ends_at = models.DateTimeField("Конец", null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Техническое уведомление"
        verbose_name_plural = "Технические уведомления"

    def __str__(self):
        return self.text

    @classmethod
    def get_active(cls):
        now = timezone.now()
        return cls.objects.filter(
            is_active=True
        ).filter(
            Q(starts_at__lte=now) | Q(starts_at__isnull=True),
            Q(ends_at__gte=now) | Q(ends_at__isnull=True)
        ).order_by("-updated_at").first()




class PaymentMethod(models.Model):
    id = models.PositiveIntegerField(primary_key=True)
    name = models.CharField(max_length=100)
    min_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    sort = models.PositiveSmallIntegerField(default=100)

    class Meta:
        ordering = ["sort", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"],
                condition=Q(is_default=True),
                name="only_one_default_payment_method",
            )
        ]
        verbose_name = "Платежный метод"
        verbose_name_plural = "Платежные методы"

    def __str__(self):
        return f"{self.id} — {self.name}"

    @classmethod
    def get_default_id(cls):
        m = cls.objects.filter(is_active=True, is_default=True).first()
        if not m:
            m = cls.objects.filter(is_active=True).order_by("sort", "id").first()
        return m.id if m else None

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.is_default:
                PaymentMethod.objects.exclude(pk=self.pk).filter(is_default=True).update(is_default=False)
            super().save(*args, **kwargs)