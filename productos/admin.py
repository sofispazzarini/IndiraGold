from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import (
    Categoria, Proveedor, Producto,
    Talle, Color, Medida, Variante,
    CategoriaOrden, CategoriaOrdenProducto, VarianteColor
)

admin.site.register(Categoria)
admin.site.register(Proveedor)
admin.site.register(Producto)
admin.site.register(Talle)
admin.site.register(Color)
admin.site.register(Medida)
admin.site.register(Variante)
@admin.register(CategoriaOrden)
class CategoriaOrdenAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activo', 'created_at')
    list_filter = ('activo',)
    search_fields = ('nombre', 'descripcion')
    list_editable = ('activo',)


@admin.register(CategoriaOrdenProducto)
class CategoriaOrdenProductoAdmin(admin.ModelAdmin):
    list_display = ('categoria_orden', 'producto', 'created_at')
    list_filter = ('categoria_orden',)
    search_fields = ('producto__nombre', 'categoria_orden__nombre')
    raw_id_fields = ('producto',)


@admin.register(VarianteColor)
class VarianteColorAdmin(admin.ModelAdmin):
    list_display = ('producto_nombre', 'talle', 'color', 'qr_code_short', 'activo', 'ver_qr_link')
    list_filter = ('activo', 'color', 'variante__talle', 'variante__producto__categoria')
    search_fields = ('variante__producto__nombre', 'variante__producto__codigo', 'color__nombre', 'qr_code')
    raw_id_fields = ('variante', 'color')

    def producto_nombre(self, obj):
        return obj.variante.producto.nombre
    producto_nombre.short_description = 'Producto'

    def talle(self, obj):
        return obj.variante.talle.nombre
    talle.short_description = 'Talle'

    def qr_code_short(self, obj):
        return obj.qr_code[:12] + '...' if obj.qr_code else '-'
    qr_code_short.short_description = 'QR Code'

    def ver_qr_link(self, obj):
        url = reverse('productos:variante_color_qr', args=[obj.id])
        return format_html('<a href="{}" target="_blank">Ver QR</a>', url)
    ver_qr_link.short_description = 'QR'
from .models import Oferta

@admin.register(Oferta)
class OfertaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descuento', 'aplicar_a_todos', 'activa')
    filter_horizontal = ('productos',)