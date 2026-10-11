"""
Stock por talle y por color.

Regla única para toda la app:
- Si la variante (talle) tiene registros VarianteColor activos, el stock real es el de cada
  color y el stock del talle es la suma de sus colores.
- Si no tiene registros de color, el stock es el de la variante.

Todas las ventas (online, presenciales, cambios) deben validar y mover stock con estas
funciones para que talle y colores no se desincronicen.

Concurrencia: descontar y reponer bloquean (SELECT ... FOR UPDATE) las filas de los talles,
colores y productos involucrados antes de leer el stock, siempre en el mismo orden (talles,
colores y productos, cada uno por id). Así dos compras simultáneas de la última unidad se
ejecutan una detrás de la otra: la segunda ve el stock ya descontado y falla. En SQLite el
bloqueo no existe (se usa solo para desarrollo/QA).
"""
from django.db import transaction
from django.db.models import F, Sum

from .models import Producto, Variante, VarianteColor


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


def _agrupar_lineas(lineas):
    """Suma las cantidades de las líneas del mismo talle y color: {(variante_id, color): [variante, color_nombre, cantidad]}."""
    agrupadas = {}
    for variante, cantidad, color_nombre in lineas:
        if not cantidad:
            continue
        clave = (variante.pk, (color_nombre or '').strip().lower())
        if clave not in agrupadas:
            agrupadas[clave] = [variante, color_nombre, 0]
        agrupadas[clave][2] += cantidad
    return agrupadas


def _bloquear_stock(variante_ids):
    """Bloquea talles, colores y productos de esas variantes (en ese orden y por id, para que dos
    operaciones simultáneas no se traben entre sí) y devuelve {id: Variante} con el stock actual."""
    variantes = {
        variante.pk: variante
        for variante in Variante.objects.select_for_update(of=('self',))
        .select_related('producto', 'talle')
        .filter(pk__in=variante_ids)
        .order_by('pk')
    }
    list(VarianteColor.objects.select_for_update().filter(variante_id__in=variante_ids).order_by('pk'))
    producto_ids = {variante.producto_id for variante in variantes.values()}
    list(Producto.objects.select_for_update().filter(pk__in=producto_ids).order_by('pk'))
    return variantes


def descontar_stock_lineas(lineas):
    """Descuenta de una sola vez varias líneas (variante, cantidad, color_nombre).
    Atómico: valida todas las cantidades con las filas bloqueadas y, si alguna no alcanza, lanza
    ValueError sin descontar nada (no quedan descuentos parciales)."""
    agrupadas = _agrupar_lineas(lineas)
    if not agrupadas:
        return
    with transaction.atomic():
        variantes = _bloquear_stock({variante_id for variante_id, _ in agrupadas})
        errores = []
        a_descontar = []
        for (variante_id, _), (_, color_nombre, cantidad) in agrupadas.items():
            variante = variantes[variante_id]
            try:
                a_descontar.append((variante, validar_stock(variante, cantidad, color_nombre), cantidad))
            except ValueError as error:
                errores.append(str(error))
        if errores:
            raise ValueError(' '.join(errores))

        for variante, variante_color, cantidad in a_descontar:
            # Descuento condicional: aunque algo se saltee el bloqueo, nunca deja stock negativo
            if variante_color:
                actualizadas = VarianteColor.objects.filter(pk=variante_color.pk, stock__gte=cantidad).update(
                    stock=F('stock') - cantidad
                )
            else:
                actualizadas = Variante.objects.filter(pk=variante.pk, stock__gte=cantidad).update(
                    stock=F('stock') - cantidad
                )
            if not actualizadas:
                raise ValueError(f'No hay stock suficiente para {variante.producto.nombre} (talle {variante.talle.nombre}).')
        for variante in variantes.values():
            sincronizar_stock_variante(variante)


def reponer_stock_lineas(lineas):
    """Devuelve al stock varias líneas (variante, cantidad, color_nombre), con las filas bloqueadas."""
    agrupadas = _agrupar_lineas(lineas)
    if not agrupadas:
        return
    with transaction.atomic():
        variantes = _bloquear_stock({variante_id for variante_id, _ in agrupadas})
        for (variante_id, _), (_, color_nombre, cantidad) in agrupadas.items():
            variante = variantes[variante_id]
            variante_color = obtener_variante_color(variante, color_nombre)
            if not variante_color and usa_stock_por_color(variante):
                # Sin color identificable: devolver al primer color activo para no perder unidades
                variante_color = colores_con_stock(variante).order_by('id').first()
            if variante_color:
                VarianteColor.objects.filter(pk=variante_color.pk).update(stock=F('stock') + cantidad)
            else:
                Variante.objects.filter(pk=variante.pk).update(stock=F('stock') + cantidad)
        for variante in variantes.values():
            sincronizar_stock_variante(variante)


def descontar_stock(variante, cantidad, color_nombre=None):
    """Descuenta unidades vendidas del color (si corresponde) y del talle.
    Lanza ValueError si no hay stock suficiente."""
    descontar_stock_lineas([(variante, cantidad, color_nombre)])
    variante.refresh_from_db(fields=['stock'])


def reponer_stock(variante, cantidad, color_nombre=None):
    """Devuelve unidades al color (si corresponde) y al talle."""
    reponer_stock_lineas([(variante, cantidad, color_nombre)])
    variante.refresh_from_db(fields=['stock'])


def repartir_stock_en_colores(stock, colores):
    """Reparte el stock de un talle entre sus colores en partes iguales (el resto va a los
    primeros). Devuelve {color_id: stock}. Se usa cuando un talle pasa a tener stock por color
    y no hay otro dato: así no se pierden unidades vendibles."""
    colores = list(colores)
    if not colores:
        return {}
    base, resto = divmod(max(stock, 0), len(colores))
    return {color.id: base + (1 if index < resto else 0) for index, color in enumerate(colores)}
