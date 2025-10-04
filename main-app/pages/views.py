from django.shortcuts import render
from catalog.models import Product


def HomePage(request):
    return render(request, 'pages/home.html')


def CatalogPage(request):
    products = Product.objects.all()
    return render(request, 'pages/catalog.html', {'products': products})


def Custom404(request, exception):
            return render(request, '404.html', status=404)

import requests
from django.http import JsonResponse
from django.conf import settings

def test_payapi(request):
    resp = requests.get(settings.PAY_API_URL + "/ping")
    return JsonResponse(resp.json())