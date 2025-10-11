from django.contrib import admin
from .models import MaintenanceBanner, PaymentMethod

@admin.register(MaintenanceBanner)
class MaintenanceBannerAdmin(admin.ModelAdmin):
    list_display = ("text", "is_active", "starts_at", "ends_at", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("text",)



@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "min_amount", "is_active", "is_default", "sort")
    list_editable = ("name", "min_amount", "is_active", "is_default", "sort")
    search_fields = ("name",)

    def save_model(self, request, obj, form, change):
        if form.cleaned_data.get("is_default"):
            PaymentMethod.objects.exclude(pk=obj.pk).filter(is_default=True).update(is_default=False)
        super().save_model(request, obj, form, change)
