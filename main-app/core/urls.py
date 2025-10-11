from django.urls import path
from .views import payment_methods_api

urlpatterns = [
    path("api/payment_methods/", payment_methods_api, name="payment_methods_api"),
]
