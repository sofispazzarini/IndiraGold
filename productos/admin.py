from django.contrib import admin
from .models import (
    Categoria, Proveedor, Producto,
    Talle, Color, Medida, Variante,
    CategoriaOrden, CategoriaOrdenProducto
)

admin.site.register(Categoria)
admin.site.register(Proveedor)
admin.site.register(Producto)
admin.site.register(Talle)
admin.site.register(Color)
admin.site.register(Medida)
admin.site.register(Variante)
admin.site.register(CategoriaOrden)
admin.site.register(CategoriaOrdenProducto)
