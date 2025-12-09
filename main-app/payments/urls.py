from django.urls import path
from .views import generate_link, bot_create_link, preview_order_id, tags_list_create

urlpatterns = [
    path("generate-link/", generate_link, name="generate_link"),
    path('api/bot/create_link/', bot_create_link, name='bot_create_link'),
    path("preview-order-id/", preview_order_id, name="preview-order-id"),
    path("api/tags/", tags_list_create, name="tags_list_create"),
]



from payments.views_plnk_test import create_plnk_test_link, create_plnk_start_test

urlpatterns += [
    path("plnk/test/", create_plnk_test_link, name="plnk_test_link"),
    path("plnk/start-test/", create_plnk_start_test, name="plnk_start_test"),
]
