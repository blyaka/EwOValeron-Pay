from django.contrib import admin
from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'order')
    list_editable = ('order',)
    ordering = ('order',)
    search_fields = ('name', 'description')
