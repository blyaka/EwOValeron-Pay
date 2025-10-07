import uuid
from django.db import models
from django.utils import timezone
from django.db.models import Q

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
