from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.contrib.sitemaps.views import sitemap
from .sitemaps import StaticViewSitemap
from django.views.generic import TemplateView
from django.shortcuts import render


sitemaps = {
    "static": StaticViewSitemap,
}

handler404 = 'pages.views.Custom404'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('accounts/', include('accounts.urls')),
    path('', include('pages.urls')),
    path('payments/', include('payments.urls')),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)



from django.http import HttpResponse
from django.urls import path
def health(_): return HttpResponse("ok")
urlpatterns += [path("health/", health)]