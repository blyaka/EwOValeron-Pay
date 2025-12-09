from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import F, DecimalField, ExpressionWrapper
from decimal import Decimal
from django.core.paginator import Paginator
from django.utils.http import urlencode
from django.db.models import Q
from datetime import datetime

from catalog.models import Product
from payments.models import Payment
from accounts.models import SellerProfile
from accounts.models import TelegramAccount

def HomePage(request):
    return render(request, 'pages/home.html')


def CatalogPage(request):
    products = Product.objects.all()
    return render(request, 'pages/catalog.html', {'products': products})


def Custom404(request, exception):
    return render(request, '404.html', status=404)






def home_lk(request):
    tg = None
    if request.user.is_authenticated:
        tg = getattr(request.user, 'tg', None)
        if tg is not None and not isinstance(tg, TelegramAccount):
            tg = None
    return render(request, 'seller/home_lk.html', {"tg": tg})



@login_required
def payment_links(request):
    qs = (Payment.objects
          .filter(user=request.user,
                  status__in=["pending", "created"],
                  expires_at__gt=timezone.now())
          .select_related("tag_obj")
          .order_by("-created_at"))

    # --- GET фильтры (как на статусах) ---
    df       = (request.GET.get("date_from") or "").strip()
    dt       = (request.GET.get("date_to") or "").strip()
    amin     = (request.GET.get("amt_min") or "").strip()
    amax     = (request.GET.get("amt_max") or "").strip()
    tag_name = (request.GET.get("tag") or "").strip()
    order_id = (request.GET.get("order_id") or "").strip()
    comment  = (request.GET.get("comment") or "").strip()

    if df:
        try:
            qs = qs.filter(created_at__date__gte=datetime.strptime(df, "%Y-%m-%d").date())
        except ValueError:
            pass
    if dt:
        try:
            qs = qs.filter(created_at__date__lte=datetime.strptime(dt, "%Y-%m-%d").date())
        except ValueError:
            pass
    if amin:
        try:
            qs = qs.filter(amount__gte=Decimal(amin))
        except Exception:
            pass
    if amax:
        try:
            qs = qs.filter(amount__lte=Decimal(amax))
        except Exception:
            pass
    if tag_name:
        qs = qs.filter(Q(tag_obj__name__exact=tag_name) | Q(tag__exact=tag_name))
    if order_id:
        qs = qs.filter(order_id__icontains=order_id)
    if comment:
        qs = qs.filter(Q(comment__icontains=comment))

    # --- пагинация (как на статусах) ---
    page_number = int(request.GET.get("page", 1))
    per_page = int(request.GET.get("per_page", 15))
    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(page_number)

    base_qs = request.GET.copy()
    base_qs.pop("page", True)
    base = urlencode(base_qs, doseq=True)
    sep = "&" if base else ""
    def url_for(n:int) -> str: return f"?{base}{sep}page={n}"

    prev_url = url_for(page_obj.previous_page_number()) if page_obj.has_previous() else ""
    next_url = url_for(page_obj.next_page_number()) if page_obj.has_next() else ""

    total = paginator.num_pages
    want = {1, 2, 3, total, page_obj.number-1, page_obj.number, page_obj.number+1}
    want = {n for n in want if 1 <= n <= total}
    ordered = sorted(want)
    pages_compact = []
    last = None
    for n in ordered:
        if last is not None and n != last + 1:
            pages_compact.append({"label": "…", "url": "", "active": False, "disabled": True})
        pages_compact.append({"label": str(n), "url": url_for(n), "active": (n == page_obj.number), "disabled": False})
        last = n

    return render(request, "seller/payment_links.html", {
        "payments": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "prev_url": prev_url,
        "next_url": next_url,
        "pages": pages_compact,
    })






@login_required
def payment_status(request):
    qs = (Payment.objects
          .filter(user=request.user)
          .select_related("tag_obj")
          .order_by("-created_at"))

    df = (request.GET.get("date_from") or "").strip()
    dt = (request.GET.get("date_to") or "").strip()
    amin = (request.GET.get("amt_min") or "").strip()
    amax = (request.GET.get("amt_max") or "").strip()
    tag_name = (request.GET.get("tag") or "").strip()
    order_id = (request.GET.get("order_id") or "").strip()
    comment = (request.GET.get("comment") or "").strip()

    if df:
        try:
            qs = qs.filter(created_at__date__gte=datetime.strptime(df, "%Y-%m-%d").date())
        except ValueError:
            pass
    if dt:
        try:
            qs = qs.filter(created_at__date__lte=datetime.strptime(dt, "%Y-%m-%d").date())
        except ValueError:
            pass
    if amin:
        try:
            qs = qs.filter(amount__gte=Decimal(amin))
        except Exception:
            pass
    if amax:
        try:
            qs = qs.filter(amount__lte=Decimal(amax))
        except Exception:
            pass
    if tag_name:
        qs = qs.filter(Q(tag_obj__name__exact=tag_name) | Q(tag__exact=tag_name))
    if order_id:
        qs = qs.filter(order_id__icontains=order_id)
    if comment:
        qs = qs.filter(Q(comment__icontains=comment))

    page_number = int(request.GET.get("page", 1))
    per_page = int(request.GET.get("per_page", 15))
    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(page_number)

    base_qs = request.GET.copy()
    base_qs.pop("page", True)
    base = urlencode(base_qs, doseq=True)
    sep = "&" if base else ""
    def url_for(n:int) -> str: return f"?{base}{sep}page={n}"

    prev_url = url_for(page_obj.previous_page_number()) if page_obj.has_previous() else ""
    next_url = url_for(page_obj.next_page_number()) if page_obj.has_next() else ""

    total = paginator.num_pages
    want = {1, 2, 3, total, page_obj.number-1, page_obj.number, page_obj.number+1}
    want = {n for n in want if 1 <= n <= total}
    ordered = sorted(want)
    pages_compact = []
    last = None
    for n in ordered:
        if last is not None and n != last + 1:
            pages_compact.append({"label": "…", "url": "", "active": False, "disabled": True})
        pages_compact.append({"label": str(n), "url": url_for(n), "active": (n == page_obj.number), "disabled": False})
        last = n

    return render(request, "seller/payment_status.html", {
        "payments": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "prev_url": prev_url,
        "next_url": next_url,
        "pages": pages_compact,
        "commission": getattr(getattr(request.user, "seller", None), "commission_pct", Decimal("0")),
    })





def brief_stats(request):
    return render(request, 'seller/brief_stats.html')



def withdraw (request):
    return render(request, 'seller/withdraw.html')

def chargers_hidtory (request):
    return render(request, 'seller/chargers_history.html')

def report_generation (request):
    return render(request, 'seller/report_generation.html')

def notification (request):
    return render(request, 'seller/notification.html')

