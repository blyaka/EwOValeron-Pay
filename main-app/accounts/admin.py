from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.urls import path, reverse
from django.utils import timezone
from django.shortcuts import redirect, get_object_or_404
from datetime import timedelta
import secrets, string
from .models import PromoCode, SellerProfile
from .models import TelegramAccount, TelegramLinkToken 


from django.conf import settings
from django.utils.html import format_html

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





class HasTelegramFilter(admin.SimpleListFilter):
    title = "Привязка Telegram"
    parameter_name = "has_tg"

    def lookups(self, request, model_admin):
        return [("1", "Есть привязка"), ("0", "Нет привязки")]

    def queryset(self, request, qs):
        if self.value() == "1":
            return qs.filter(user__tg__isnull=False)
        if self.value() == "0":
            return qs.filter(user__tg__isnull=True)
        return qs

@admin.register(SellerProfile)
class SellerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "order_prefix", "commission_pct",
                    "tg_status", "tg_username", "tg_id", "tg_linked_at", "tg_actions")
    search_fields = ("user__username", "order_prefix", "user__tg__username")
    list_editable = ("commission_pct",)
    list_filter = (HasTelegramFilter,)
    ordering = ("user__username",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user").prefetch_related("user__tg")

    # ----- колонки TG -----
    def tg_status(self, obj):
        return "✅" if hasattr(obj.user, "tg") else "—"
    tg_status.short_description = "TG"

    def tg_username(self, obj):
        return getattr(getattr(obj.user, "tg", None), "username", "") or ""
    tg_username.short_description = "TG username"

    def tg_id(self, obj):
        return getattr(getattr(obj.user, "tg", None), "telegram_id", "") or ""
    tg_id.short_description = "TG ID"

    def tg_linked_at(self, obj):
        return getattr(getattr(obj.user, "tg", None), "linked_at", None)
    tg_linked_at.short_description = "Привязан"

    # Кнопки действий в строке
    def tg_actions(self, obj):
        link_url = reverse("admin:accounts_sellerprofile_tg_link", args=[obj.pk])
        unlink_url = reverse("admin:accounts_sellerprofile_tg_unlink", args=[obj.pk])
        btn_link = f'<a class="button" href="{link_url}">Deep-link</a>'
        btn_unlink = f'<a class="button" href="{unlink_url}">Отвязать</a>'
        return format_html(f"{btn_link}&nbsp;{btn_unlink}")
    tg_actions.short_description = "Действия"
    tg_actions.allow_tags = True

    # ----- кастомные urls -----
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path("<int:pk>/tg-link/", self.admin_site.admin_view(self.tg_link_view),
                 name="accounts_sellerprofile_tg_link"),
            path("<int:pk>/tg-unlink/", self.admin_site.admin_view(self.tg_unlink_view),
                 name="accounts_sellerprofile_tg_unlink"),
        ]
        return custom + urls

    def tg_link_view(self, request, pk):
        if not self.has_change_permission(request):
            raise PermissionDenied
        obj = get_object_or_404(SellerProfile, pk=pk)
        # если уже привязан — просто подсветим ник
        if hasattr(obj.user, "tg"):
            messages.info(request, f"Уже привязан: @{obj.user.tg.username or obj.user.tg.telegram_id}")
            return redirect(reverse("admin:accounts_sellerprofile_changelist"))

        tok = TelegramLinkToken.issue(obj.user, ttl_minutes=15)
        bot_name = getattr(settings, "TELEGRAM_BOT_USERNAME", "")
        deep = f"https://t.me/{bot_name}?start={tok.token}"
        messages.success(request, f"Deep-link на 15 мин: {deep}")
        return redirect(reverse("admin:accounts_sellerprofile_changelist"))

    def tg_unlink_view(self, request, pk):
        if not self.has_change_permission(request):
            raise PermissionDenied
        obj = get_object_or_404(SellerProfile, pk=pk)
        deleted, _ = TelegramAccount.objects.filter(user=obj.user).delete()
        if deleted:
            messages.success(request, "Привязка Telegram удалена.")
        else:
            messages.info(request, "Привязки не было.")
        return redirect(reverse("admin:accounts_sellerprofile_changelist"))
