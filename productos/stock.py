"""
Stock por talle y por color.

Regla única para toda la app:
- Si la variante (talle) tiene registros VarianteColor activos, el stock real es el de cada
  color y el stock del talle es la suma de sus colores.
- Si no tiene registros de color, el stock es el de la variante.

Todas las ventas (online, presenciales, cambios) deben validar y mover stock con estas
funciones para que talle y colores no se desincronicen.
"""
from django.db.models import Sum

from .models import Variante, VarianteColor


def colores_con_stock(variante):
    """VarianteColor activos de la variante (queryset)."""
    return VarianteColor.objects.filter(variante=variante, activo=True).select_related('color')


def usa_stock_por_color(variante):
    return colores_con_stock(variante).exists()


def obtener_variante_color(variante, color_nombre):
    """VarianteColor activo de esa variante para el color indicado (por nombre), o None."""
    nombre = (color_nombre or '').strip()
    if not nombre:
        return None
    return colores_con_stock(variante).filter(color__nombre__iexact=nombre).first()


def stock_disponible(variante, color_nombre=None):
    """Unidades vendibles de un talle, o de un color de ese talle si usa stock por color."""
    variante_color = obtener_variante_color(variante, color_nombre)
    if variante_color:
        return variante_color.stock
    if color_nombre and usa_stock_por_color(variante):
        # El color pedido no existe (o está inactivo) para este talle
        return 0
    return variante.stock


def stock_total_variante(variante):
    """Stock del talle: suma de sus colores si usa stock por color, si no Variante.stock."""
    if usa_stock_por_color(variante):
        return colores_con_stock(variante).aggregate(total=Sum('stock'))['total'] or 0
    return variante.stock


def sincronizar_stock_variante(variante):
    """Deja Variante.stock igual a la suma de sus colores (si tiene) y actualiza el producto."""
    if usa_stock_por_color(variante):
        total = colores_con_stock(variante).aggregate(total=Sum('stock'))['total'] or 0
        # update() directo: la instancia en memoria puede tener un stock viejo
        Variante.objects.filter(pk=variante.pk).update(stock=total)
        variante.stock = total
    producto = variante.producto
    producto.stock = producto.stock_total
    producto.save(update_fields=['stock'])


def resolver_variante_color(variante, color_nombre=None):
    """VarianteColor a usar para una venta. Si el talle usa stock por color y no se indicó
    color, solo se acepta cuando tiene un único color. Lanza ValueError si no se puede resolver."""
    variante_color = obtener_variante_color(variante, color_nombre)
    if variante_color or not usa_stock_por_color(variante):
        return variante_color
    if color_nombre:
        raise ValueError(
            f'El color {color_nombre} no está disponible para {variante.producto.nombre} '
            f'(talle {variante.talle.nombre}).'
        )
    colores = list(colores_con_stock(variante)[:2])
    if len(colores) == 1:
        return colores[0]
    raise ValueError(
        f'Indicá el color de {variante.producto.nombre} (talle {variante.talle.nombre}).'
    )


def validar_stock(variante, cantidad, color_nombre=None):
    """Lanza ValueError si no hay stock suficiente para vender esa cantidad."""
    variante_color = resolver_variante_color(variante, color_nombre)
    disponible = variante_color.stock if variante_color else variante.stock
    if cantidad > disponible:
        detalle_color = f' color {variante_color.color.nombre}' if variante_color else ''
        raise ValueError(
            f'No hay stock suficiente para {variante.producto.nombre} '
            f'(talle {variante.talle.nombre}{detalle_color}). '
            f'Disponible: {disponible}, pedido: {cantidad}'
        )
    return variante_color


def descontar_stock(variante, cantidad, color_nombre=None):
    """Descuenta unidades vendidas del color (si corresponde) y del talle.
    Lanza ValueError si no hay stock suficiente."""
    variante_color = validar_stock(variante, cantidad, color_nombre)
    if variante_color:
        variante_color.stock -= cantidad
        variante_color.save(update_fields=['stock'])
    else:
        variante.stock -= cantidad
        variante.save(update_fields=['stock'])
    sincronizar_stock_variante(variante)


def reponer_stock(variante, cantidad, color_nombre=None):
    """Devuelve unidades al color (si corresponde) y al talle."""
    variante_color = obtener_variante_color(variante, color_nombre)
    if variante_color:
        variante_color.stock += cantidad
        variante_color.save(update_fields=['stock'])
    elif usa_stock_por_color(variante):
        # Sin color identificable: devolver al primer color activo para no perder unidades
        primero = colores_con_stock(variante).order_by('id').first()
        primero.stock += cantidad
        primero.save(update_fields=['stock'])
    else:
        variante.stock += cantidad
        variante.save(update_fields=['stock'])
    sincronizar_stock_variante(variante)


def repartir_stock_en_colores(stock, colores):
    """Reparte el stock de un talle entre sus colores en partes iguales (el resto va a los
    primeros). Devuelve {color_id: stock}. Se usa cuando un talle pasa a tener stock por color
    y no hay otro dato: así no se pierden unidades vendibles."""
    colores = list(colores)
    if not colores:
        return {}
    base, resto = divmod(max(stock, 0), len(colores))
    return {color.id: base + (1 if index < resto else 0) for index, color in enumerate(colores)}
