from django.contrib import admin
from .models import Category, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'order')
    list_editable = ('order',)
    list_filter = ('category',)
    search_fields = ('name', 'description')
    autocomplete_fields = ('category',)
    ordering = ('order', 'name')
    save_on_top = True

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('category')
