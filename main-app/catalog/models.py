# models.py
from django.db import models


class Category(models.Model):
    name = models.CharField('Категория', max_length=100, unique=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(
        Category,
        verbose_name='Категория',
        related_name='products',
        on_delete=models.PROTECT,
    )
    name = models.CharField('Название', max_length=100, db_index=True)
    description = models.CharField('Краткое описание', max_length=255, blank=True)
    poster = models.ImageField('Постер', upload_to='catalog/posters')
    price = models.PositiveIntegerField('Цена')
    order = models.PositiveIntegerField('Порядок', default=0, db_index=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'

    def __str__(self):
        return self.name
