from django.http import JsonResponse
from .models import PaymentMethod

def payment_methods_api(request):
    rows = (PaymentMethod.objects
            .filter(is_active=True)
            .order_by('sort','id')
            .values('id','name','min_amount','is_default'))
    return JsonResponse({"ok": True, "methods": list(rows)})