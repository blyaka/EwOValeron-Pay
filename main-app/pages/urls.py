from django.urls import path
from .views import HomePage, CatalogPage, test_payapi


from .views import home_lk, payment_links, payment_status

urlpatterns = [
    path('', HomePage, name='home'),
    path('catalog/', CatalogPage, name='catalog'),
    path('test-payapi/', test_payapi, name='test-payapi'),

    path('home-lk/', home_lk, name='home-lk'),
    path('payment-links/', payment_links, name='payment-links'),
    path('payment-status/', payment_status, name='payment-status'),
]