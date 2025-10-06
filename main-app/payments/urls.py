from django.urls import path
from .views import generate_link

urlpatterns = [
    path("generate-link/", generate_link, name="generate_link"),
]