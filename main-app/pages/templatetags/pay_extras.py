from django import template
from django.utils import timezone

register = template.Library()

@register.filter
def ttl(value):
    if not value: return ""
    delta = value - timezone.now()
    sec = int(delta.total_seconds())
    if sec <= 0: return "истекла"
    d, rem = divmod(sec, 86400)
    h, rem = divmod(rem, 3600)
    m, _   = divmod(rem, 60)
    return f"{d}д {h}ч {m}м"
