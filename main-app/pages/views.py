from django.shortcuts import render


def HomePage(request):
    return render(request, 'pages/home.html')


def CatalogPage(request):
    return render(request, 'pages/catalog.html')


def Custom404(request, exception):
            return render(request, '404.html', status=404)