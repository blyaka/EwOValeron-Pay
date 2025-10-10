from django.urls import path
from .views import tg_connect_link

urlpatterns = [
    path('tg/connect-link/', tg_connect_link, name='tg_connect_link'),
]
