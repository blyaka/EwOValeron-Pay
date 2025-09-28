from django.urls import path
from .views import HomePage, CatalogPage


urlpatterns = [
    path('', HomePage, name='home'),
    path('catalog/', CatalogPage, name='catalog'),
]