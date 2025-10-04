from django.urls import path
from .views import HomePage, CatalogPage, test_payapi


urlpatterns = [
    path('', HomePage, name='home'),
    path('catalog/', CatalogPage, name='catalog'),
    path('test-payapi/', test_payapi, name='test-payapi'),
]