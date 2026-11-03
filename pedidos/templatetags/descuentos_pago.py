from django import template
from pedidos.descuentos import calcular_totales, porcentaje_pago
from pedidos.models import ConfiguracionPago

register = template.Library()


@register.inclusion_tag('pedidos/_descuentos_producto.html', takes_context=True)
def descuentos_producto(context, producto, presentacion='tarjeta'):
    request = context.get('request')
    configuracion = getattr(request, '_config_descuentos_pago', None)
    if configuracion is None:
        configuracion = ConfiguracionPago.objects.filter(pk=1).first() or ConfiguracionPago()
        if request is not None:
            request._config_descuentos_pago = configuracion
    ofertas = []
    for metodo, nombre in [('transferencia', 'transferencia'), ('efectivo', 'efectivo')]:
        porcentaje = porcentaje_pago(configuracion, metodo)
        if porcentaje > 0:
            totales = calcular_totales(producto.precio_final, porcentaje=porcentaje)
            ofertas.append({'porcentaje': porcentaje, 'nombre': nombre, 'precio': totales['total']})
    return {'ofertas_pago': ofertas, 'detalle_promociones': presentacion == 'detalle'}
