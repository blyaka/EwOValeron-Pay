from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import F, DecimalField, ExpressionWrapper
from decimal import Decimal

from catalog.models import Product
from payments.models import Payment
from accounts.models import SellerProfile


def HomePage(request):
    return render(request, 'pages/home.html')


def CatalogPage(request):
    products = Product.objects.all()
    return render(request, 'pages/catalog.html', {'products': products})


def Custom404(request, exception):
    return render(request, '404.html', status=404)








METHOD_NAMES = {
    44: "СБП",
    36: "Карта",
    35: "СберПэй",  # если у тебя другое — поменяй
}


def home_lk(request):
    return render(request, 'seller/home_lk.html')

@login_required
def payment_links(request):
    qs = (Payment.objects
          .filter(user=request.user, status__in=["pending", "created"], expires_at__gt=timezone.now())
          .select_related("tag_obj")                     # ← вот это
          .order_by("-created_at"))
    return render(request, "seller/payment_links.html", {"payments": qs})








@login_required
def payment_status(request):
    # отдаём реальные объекты, чтобы шаблон мог читать
    # p.fee, p.payout, p.commission_percent, p.method_label, p.tag_obj и т.д.
    payments = (Payment.objects
                .filter(user=request.user)
                .select_related("tag_obj")
                .order_by("-created_at"))

    return render(request, "seller/payment_status.html", {
        "payments": payments,
        # если в шаблоне больше не нужен, можно убрать ключ 'commission'
        # оставлю для совместимости, но он теперь только для информации
        "commission": getattr(getattr(request.user, "seller", None), "commission_pct", Decimal("0")),
    })




def brief_stats(request):
    return render(request, 'seller/brief_stats.html')
