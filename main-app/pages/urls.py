from django.urls import path
from .views import HomePage, CatalogPage


from .views import home_lk, payment_links, payment_status, brief_stats, withdraw, chargers_hidtory, report_generation, notification

urlpatterns = [
    path('', HomePage, name='home'),
    path('catalog/', CatalogPage, name='catalog'),

    path('home-lk/', home_lk, name='home-lk'),
    path('payment-links/', payment_links, name='payment-links'),
    path('payment-status/', payment_status, name='payment-status'),
    path('brief-stats/', brief_stats, name='brief-stats'),
    path('withdraw/', withdraw, name='withdraw'),
    path('chargers-hidtory/', chargers_hidtory, name='chargers-hidtory'),
    path('report-generation/', report_generation, name='report-generation'),
    path('notification/', notification, name='notification')
]