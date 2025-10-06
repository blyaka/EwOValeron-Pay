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
          .order_by("-created_at"))
    return render(request, "seller/payment_links.html", {"payments": qs})








@login_required
def payment_status(request):
    try:
        seller = request.user.seller
        commission_pct = seller.commission_pct or Decimal("0")
    except SellerProfile.DoesNotExist:
        commission_pct = Decimal("0")

    qs = Payment.objects.filter(user=request.user).order_by("-created_at")

    rows = []
    for p in qs:
        fee = (p.amount * commission_pct / Decimal("100")).quantize(Decimal("0.01"))
        payout = (p.amount - fee).quantize(Decimal("0.01"))

        rows.append({
            "created_at": p.created_at,
            "order_id": p.order_id,
            "comment": p.comment or "",
            "amount": p.amount,
            "fee": fee,
            "payout": payout,
            "method": METHOD_NAMES.get(p.method, str(p.method)),
            "status": p.status,
            "intid": getattr(p, "fk_intid", "") or "—",
            "tag": p.tag or "нет",
            "seller": request.user.username,
        })

    return render(request, "seller/payment_status.html", {
        "payments": rows,
        "commission": commission_pct,
    })