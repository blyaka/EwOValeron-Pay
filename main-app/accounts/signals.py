
from allauth.account.signals import user_signed_up
from django.dispatch import receiver
from .utils import alloc_prefix_for

@receiver(user_signed_up)
def ensure_prefix(sender, request, user, **kwargs):
    if not hasattr(user, "seller"):
        try:
            alloc_prefix_for(user)
        except Exception:
            pass
