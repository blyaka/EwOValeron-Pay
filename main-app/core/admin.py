from django.contrib import admin
from .models import MaintenanceBanner

@admin.register(MaintenanceBanner)
class MaintenanceBannerAdmin(admin.ModelAdmin):
    list_display = ("text", "is_active", "starts_at", "ends_at", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("text",)
