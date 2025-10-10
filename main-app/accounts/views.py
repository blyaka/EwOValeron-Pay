from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.conf import settings
from .models import TelegramLinkToken, TelegramAccount

@login_required
def tg_connect_link(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST only')


    if hasattr(request.user, 'tg'):
        return JsonResponse({
            'status': 'already_linked',
            'telegram_id': request.user.tg.telegram_id,
            'username': request.user.tg.username
        })

    tok = TelegramLinkToken.issue(request.user, ttl_minutes=15)
    bot_name = getattr(settings, 'TELEGRAM_BOT_USERNAME', '')
    deep = f"https://t.me/{bot_name}?start={tok.token}"
    return JsonResponse({'status': 'ok', 'link': deep, 'expires_at': tok.expires_at.isoformat()})
