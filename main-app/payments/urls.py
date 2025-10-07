from django.urls import path
from .views import generate_link, allocate_order_id

urlpatterns = [
    path("generate-link/", generate_link, name="generate_link"),
    path("allocate-order-id/", allocate_order_id, name="allocate_order_id"),
]