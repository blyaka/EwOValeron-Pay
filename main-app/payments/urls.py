from django.urls import path
from .views import generate_link, preview_order_id, tags_list_create

urlpatterns = [
    path("generate-link/", generate_link, name="generate_link"),
    path("preview-order-id/", preview_order_id, name="preview-order-id"),
    path("api/tags/", tags_list_create, name="tags_list_create"),
]