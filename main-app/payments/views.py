from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from .forms import CreateLinkForm
import logging
from .services import next_order_id_for, preview_next_order_id_for

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




@require_GET
@login_required
def preview_order_id(request):
    oid, seq, prefix, day = preview_next_order_id_for(request.user)
    return JsonResponse({
        "order_id": oid,
        "order_seq": seq,
        "order_prefix": prefix,
        "order_date": day.strftime("%Y-%m-%d")
    })