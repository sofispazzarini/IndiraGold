from django.contrib import admin
from .models import Pedido, PedidoItem, Pago, Gasto


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ('id', 'cliente', 'total', 'tipo_venta', 'estado', 'created_at')
    list_filter = ('estado', 'tipo_venta', 'created_at')
    search_fields = ('cliente__nombre', 'id')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)


@admin.register(PedidoItem)
class PedidoItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'pedido', 'variante', 'cantidad', 'precio_total')
    list_filter = ('pedido__estado',)
    search_fields = ('pedido__id', 'variante__producto__nombre')


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ('id', 'pedido', 'metodo', 'monto', 'fecha_pago')
    list_filter = ('metodo', 'fecha_pago')
    search_fields = ('pedido__id',)
    readonly_fields = ('fecha_pago',)


@admin.register(Gasto)
class GastoAdmin(admin.ModelAdmin):
    list_display = ('id', 'descripcion', 'monto', 'fecha')
    list_filter = ('fecha', 'created_at')
    search_fields = ('descripcion',)
    readonly_fields = ('created_at',)
