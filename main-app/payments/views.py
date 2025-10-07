from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.contrib.auth.decorators import login_required
from .forms import CreateLinkForm
import logging
from .services import next_order_id_for, preview_next_order_id_for
from .models import Tag
logger = logging.getLogger(__name__)
import random
import json
from django.utils.text import slugify

@login_required
@require_POST
def generate_link(request):
    form = CreateLinkForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": form.errors}, status=400)

    try:
        payment = form.save(request.user)
        return JsonResponse({
            "ok": True,
            "order_id": payment.order_id,
            "public_url": payment.public_url,
            "fk_url": payment.fk_url,
            "amount": str(payment.amount),
            "method": payment.method,
            "comment": payment.comment,
            "tag_id": payment.tag_obj_id,
            "tag_name": payment.tag_obj.name if payment.tag_obj_id else None,
            "tag": payment.tag,
            "expires_at": payment.expires_at.isoformat(),
        })
    except Exception as e:
        logger.exception("Ошибка при генерации ссылки: %s", e)
        return JsonResponse({"ok": False, "error": str(e)}, status=500)





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





_PALETTE = ['#a855f7','#22d3ee','#8b5cf6','#06b6d4','#10b981','#f59e0b','#ef4444','#eab308']

@login_required
@require_http_methods(["GET", "POST"])
def tags_list_create(request):
    # GET /payments/api/tags/?q=...
    if request.method == "GET":
        q = (request.GET.get("q") or "").strip()
        qs = Tag.objects.filter(user=request.user)
        if q:
            qs = qs.filter(name__icontains=q)
        data = [{"id": t.id, "name": t.name, "color": t.color} for t in qs.order_by("name")]
        return JsonResponse({"tags": data})

    # POST /payments/api/tags/  body: {"name": "..."}
    try:
        payload = json.loads(request.body.decode("utf-8"))
        name = (payload.get("name") or "").strip()
    except Exception:
        return HttpResponseBadRequest("bad json")

    if len(name) < 2:
        return HttpResponseBadRequest("name too short")

    base_slug = slugify(name) or name.lower().replace(" ", "-")
    slug = base_slug
    i = 2
    # уникальность в пределах пользователя
    while Tag.objects.filter(user=request.user, slug=slug).exists():
        slug = f"{base_slug}-{i}"
        i += 1

    tag = Tag.objects.create(
        user=request.user,
        name=name,
        slug=slug,
        color=random.choice(_PALETTE),
    )
    return JsonResponse({"id": tag.id, "name": tag.name, "color": tag.color})