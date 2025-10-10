from django.urls import path
from .views import generate_link, bot_create_link, preview_order_id, tags_list_create

urlpatterns = [
    path("generate-link/", generate_link, name="generate_link"),
    path('api/bot/create_link/', bot_create_link, name='bot_create_link'),
    path("preview-order-id/", preview_order_id, name="preview-order-id"),
    path("api/tags/", tags_list_create, name="tags_list_create"),
]