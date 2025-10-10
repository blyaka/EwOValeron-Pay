from django.db import models
from django.conf import settings
from django.utils import timezone
import secrets
from datetime import timedelta


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



class SellerProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="seller")
    order_prefix = models.CharField(max_length=3, unique=True, db_index=True)
    commission_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )

    def __str__(self):
        return f"{self.user.username} [{self.order_prefix}] {self.commission_pct}%"
    





class TelegramAccount(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tg')
    telegram_id = models.BigIntegerField(unique=True)
    username = models.CharField(max_length=64, blank=True)
    first_name = models.CharField(max_length=64, blank=True)
    linked_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ↔ TG:{self.telegram_id}"

class TelegramLinkToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tg_tokens')
    token = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    @classmethod
    def issue(cls, user, ttl_minutes=15):
        t = cls(
            user=user,
            token=secrets.token_urlsafe(32),
            expires_at=timezone.now() + timedelta(minutes=ttl_minutes)
        )
        t.save()
        return t

    def is_active(self):
        return (not self.used) and timezone.now() <= self.expires_at

    def mark_used(self):
        self.used = True
        self.save(update_fields=['used'])
