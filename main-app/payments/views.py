from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from .forms import CreateLinkForm
import logging

logger = logging.getLogger(__name__)

@login_required
@require_POST
def generate_link(request):
    form = CreateLinkForm(request.POST)

    if not form.is_valid():
        return JsonResponse({
            "ok": False,
            "errors": form.errors
        }, status=400)

    try:
        payment = form.save(request.user)
        return JsonResponse({
            "ok": True,
            "order_id": payment.order_id,
            "public_url": payment.public_url,
            "fk_url": payment.fk_url,
            "amount": f"{payment.amount:.2f}",
            "method": payment.method,
            "comment": payment.comment,
            "tag": payment.tag,
            "expires_at": payment.expires_at.isoformat(),
        })

    except Exception as e:
        logger.exception("Ошибка при генерации ссылки: %s", e)
        return JsonResponse({
            "ok": False,
            "error": str(e)
        }, status=500)
