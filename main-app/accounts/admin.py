from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.urls import path, reverse
from django.utils import timezone
from django.shortcuts import redirect
from datetime import timedelta
import secrets, string
from .models import PromoCode, SellerProfile

def _new_code(n=10):
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(n))

@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ('code','used','expires_at','used_by','used_at')
    list_filter = ('used',)
    search_fields = ('code',)
    change_list_template = "admin/accounts/promocode/change_list.html"

    actions = ['generate_codes', 'generate_one']

    def get_urls(self):
        urls = super().get_urls()
        app = self.model._meta.app_label
        model = self.model._meta.model_name
        custom = [
            path(
                "generate-one/",
                self.admin_site.admin_view(self.generate_one_view),
                name=f"{app}_{model}_generate_one",
            ),
            path(
                "generate-batch/",
                self.admin_site.admin_view(self.generate_batch_view),
                name=f"{app}_{model}_generate_batch",
            ),
        ]
        return custom + urls

    def _create_codes(self, count):
        now = timezone.now()
        items = [
            PromoCode(code=_new_code(10), expires_at=now + timedelta(hours=1))
            for _ in range(count)
        ]
        PromoCode.objects.bulk_create(items, ignore_conflicts=True)
        return items

    # Кнопка 1: создать один
    def generate_one_view(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied
        if request.method != "POST":
            return redirect(reverse(f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist"))
        obj = self._create_codes(1)[0]
        messages.success(request, f"Создан промокод: {obj.code}")
        return redirect(reverse(f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist"))

    # Кнопка 2: создать 20
    def generate_batch_view(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied
        if request.method != "POST":
            return redirect(reverse(f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist"))
        items = self._create_codes(20)
        messages.success(request, f"Сгенерировано {len(items)} промокодов на 1 час.")
        return redirect(reverse(f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist"))

    # старые экшены — по желанию
    def generate_codes(self, request, queryset):
        items = self._create_codes(20)
        self.message_user(request, f"Сгенерировано {len(items)} промокодов на 1 час.")
    generate_codes.short_description = "Сгенерировать 20 промокодов (1 час)"

    def generate_one(self, request, queryset):
        obj = self._create_codes(1)[0]
        self.message_user(request, f"Создан промокод: {obj.code}")
    generate_one.short_description = "Создать 1 промокод (1 час)"





@admin.register(SellerProfile)
class SellerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "order_prefix", "commission_pct")
    search_fields = ("user__username", "order_prefix")
    list_editable = ("commission_pct",)
    ordering = ("user__username",)