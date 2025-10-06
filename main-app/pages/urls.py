from django.urls import path
from .views import HomePage, CatalogPage


from .views import home_lk, payment_links, payment_status

urlpatterns = [
    path('', HomePage, name='home'),
    path('catalog/', CatalogPage, name='catalog'),

    path('home-lk/', home_lk, name='home-lk'),
    path('payment-links/', payment_links, name='payment-links'),
    path('payment-status/', payment_status, name='payment-status'),
]