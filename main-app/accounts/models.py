from django.db import models
from django.conf import settings
from django.utils import timezone

class PromoCode(models.Model):
    code = models.CharField('Код', max_length=32, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
    used_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='used_promo_codes'
    )

    def is_active(self):
        return (not self.used) and timezone.now() <= self.expires_at

    def __str__(self):
        return f"{self.code} ({'OK' if self.is_active() else 'INVALID'})"
