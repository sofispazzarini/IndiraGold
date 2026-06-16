from django.contrib import admin
from .models import Pedido, PedidoItem, Pago, Gasto
from .models import VentaLocal, VentaLocalItem, ConfiguracionEnvio, ConfiguracionPago, PlanCuotasMercadoPago

admin.site.register(VentaLocal)
admin.site.register(VentaLocalItem)


@admin.register(ConfiguracionEnvio)
class ConfiguracionEnvioAdmin(admin.ModelAdmin):
    list_display = ('id', 'flex_activo', 'flex_gratis', 'precio_flex', 'zonas_disponibles')
    fields = ('flex_activo', 'flex_gratis', 'precio_flex', 'zonas_flex')

    def zonas_disponibles(self, obj):
        zonas = obj.zonas_flex_lista
        return ', '.join(zonas) if zonas else 'Sin zonas cargadas'

    zonas_disponibles.short_description = 'Zonas Flex'

    def has_add_permission(self, request):
        if ConfiguracionEnvio.objects.exists():
            return False
        return super().has_add_permission(request)


class PlanCuotasMercadoPagoInline(admin.TabularInline):
    model = PlanCuotasMercadoPago
    extra = 1


@admin.register(ConfiguracionPago)
class ConfiguracionPagoAdmin(admin.ModelAdmin):
    inlines = [PlanCuotasMercadoPagoInline]
    list_display = ('id', 'mercado_pago_activo', 'transferencia_activa', 'alias', 'cvu')

    def has_add_permission(self, request):
        if ConfiguracionPago.objects.exists():
            return False
        return super().has_add_permission(request)
@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ('id', 'cliente', 'total', 'tipo_venta', 'estado', 'created_at')
    list_filter = ('estado', 'tipo_venta', 'created_at')
    search_fields = ('id', 'cliente__dni', 'cliente__user__username', 'cliente__user__first_name')
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
