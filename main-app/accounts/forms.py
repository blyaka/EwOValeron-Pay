# accounts/forms.py  (где лежит твой PromoSignupForm)
from django import forms
from django.db import transaction
from django.utils import timezone
from .models import PromoCode
from .utils import alloc_prefix_for

class PromoSignupForm(forms.Form):
    promo_code = forms.CharField(label='Промокод', max_length=32)

    def clean_promo_code(self):
        raw = self.cleaned_data['promo_code'].strip().upper()
        try:
            pc = PromoCode.objects.get(code=raw)
        except PromoCode.DoesNotExist:
            raise forms.ValidationError('Неверный промокод.')
        if pc.used:
            raise forms.ValidationError('Этот промокод уже использован.')
        if timezone.now() > pc.expires_at:
            raise forms.ValidationError('Срок действия промокода истёк.')
        return raw

    def signup(self, request, user):
        code = self.cleaned_data['promo_code'].strip().upper()
        with transaction.atomic():
            pc = PromoCode.objects.select_for_update().get(code=code)
            if pc.used or timezone.now() > pc.expires_at:
                raise forms.ValidationError('Промокод больше недействителен.')
            pc.used = True
            pc.used_by = user
            pc.used_at = timezone.now()
            pc.save(update_fields=['used','used_by','used_at'])

            if not hasattr(user, "seller"):
                alloc_prefix_for(user)
