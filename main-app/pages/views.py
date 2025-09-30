from django.shortcuts import render
from catalog.models import Product


def HomePage(request):
    return render(request, 'pages/home.html')


def CatalogPage(request):
    products = Product.objects.all()
    return render(request, 'pages/catalog.html', {'products': products})


def Custom404(request, exception):
            return render(request, '404.html', status=404)