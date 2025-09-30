from django.db import models


class Product(models.Model):
    name = models.CharField('Название', max_length=100)
    description = models.CharField('Краткое описание', max_length=255)
    poster = models.ImageField('Постер', upload_to='catalog/posters')
    price = models.PositiveIntegerField('Цена')
    order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        ordering = ['order']
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'

    def __str__(self): return self.name