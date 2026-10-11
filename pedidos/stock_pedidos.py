"""
Stock de los pedidos online: reserva, venta, devolución y vencimiento.

- Las unidades de un pedido se descuentan al crearlo (es la reserva mientras se espera el pago):
  transferencia, QR y efectivo al confirmar el checkout; Mercado Pago al ir a pagar.
- Aceptar el pago no vuelve a descontar. Cancelar, rechazar o vencer devuelve las unidades.
- Pedido.stock_descontado indica si las unidades están descontadas. Se lee y se cambia con la fila
  del pedido bloqueada, así una operación repetida (dos clics, dos pestañas, un retorno repetido de
  Mercado Pago) no descuenta ni devuelve dos veces.
- Un pendiente que no se paga vence solo y libera sus unidades (ver vencer_reservas).
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from productos.stock import descontar_stock_lineas, reponer_stock_lineas
from .models import Cambio, Pedido

logger = logging.getLogger(__name__)

# Margen para un pago de Mercado Pago que empezó justo antes de que venciera el link
MARGEN_RESERVA_MERCADO_PAGO = timedelta(minutes=15)
# Cada cuánto, como mucho, se revisan las reservas vencidas en los requests
INTERVALO_REVISION_RESERVAS = 300


def plazo_pendiente():
    """Tiempo que un pedido pendiente (transferencia, QR, efectivo) retiene sus unidades."""
    return timedelta(hours=settings.PEDIDO_PENDIENTE_VENCE_HORAS)


def plazo_reserva_mercado_pago():
    """Tiempo para pagar en Mercado Pago (el link de pago vence a la misma hora)."""
    return timedelta(minutes=settings.MP_RESERVA_MINUTOS)


def unidades_cambiadas(pedido_item):
    """Unidades de un ítem que ya se cambiaron por otro producto."""
    return Cambio.objects.filter(
        pedido=pedido_item.pedido,
        variante_devuelta=pedido_item.variante,
    ).filter(
        Q(color_devuelto=(pedido_item.color_nombre or '')) | Q(color_devuelto='')
    ).count()


def unidades_devolvibles(pedido_item):
    """Unidades de un ítem que el cliente todavía tiene: lo comprado menos lo devuelto con notas
    de crédito (no anuladas) y lo ya cambiado. Es el máximo para una nueva NC o un nuevo cambio."""
    devueltas = pedido_item.devoluciones.exclude(nota_credito__estado='anulada').aggregate(
        total=Sum('cantidad')
    )['total'] or 0
    return max(pedido_item.cantidad - devueltas - unidades_cambiadas(pedido_item), 0)


def descontar_stock_pedido(pedido):
    """Descuenta (reserva) las unidades del pedido una sola vez. Atómico: entran todas o ninguna.
    Devuelve True si descontó, False si ya estaban descontadas. Lanza ValueError si no alcanza."""
    with transaction.atomic():
        bloqueado = Pedido.objects.select_for_update().get(pk=pedido.pk)
        if bloqueado.stock_descontado:
            pedido.stock_descontado = True
            return False
        items = list(bloqueado.items.select_related('variante__producto', 'variante__talle'))
        descontar_stock_lineas((item.variante, item.cantidad, item.color_nombre) for item in items)
        Pedido.objects.filter(pk=pedido.pk).update(stock_descontado=True)
    pedido.stock_descontado = True
    return True


def reponer_stock_pedido(pedido):
    """Devuelve al stock lo que el cliente todavía tiene del pedido, una sola vez. Las unidades ya
    devueltas con nota de crédito o cambiadas ya volvieron al stock en su momento; en cambio, lo
    que se entregó en un cambio sí vuelve ahora. Devuelve True si repuso, False si no había nada
    descontado."""
    with transaction.atomic():
        bloqueado = Pedido.objects.select_for_update().get(pk=pedido.pk)
        if not bloqueado.stock_descontado:
            pedido.stock_descontado = False
            return False
        lineas = []
        for item in bloqueado.items.select_related('variante__producto', 'variante__talle'):
            pendientes = unidades_devolvibles(item)
            if pendientes:
                lineas.append((item.variante, pendientes, item.color_nombre))
        for cambio in bloqueado.cambios.select_related('variante_entregada__producto', 'variante_entregada__talle'):
            if cambio.variante_entregada:
                lineas.append((cambio.variante_entregada, cambio.cantidad_entregada or 1, cambio.color_entregado or None))
        reponer_stock_lineas(lineas)
        Pedido.objects.filter(pk=pedido.pk).update(stock_descontado=False)
    pedido.stock_descontado = False
    return True


def reservas_vencidas(ahora=None):
    """Pedidos pendientes que retienen unidades y ya pasaron su plazo de pago."""
    ahora = ahora or timezone.now()
    limite_mercado_pago = ahora - plazo_reserva_mercado_pago() - MARGEN_RESERVA_MERCADO_PAGO
    return Pedido.objects.filter(estado='pendiente', stock_descontado=True).filter(
        Q(metodo_pago='mercado_pago', created_at__lt=limite_mercado_pago)
        | (~Q(metodo_pago='mercado_pago') & Q(created_at__lt=ahora - plazo_pendiente()))
    )


def vencer_reservas(ahora=None):
    """Pasa a Vencido los pendientes cuyo plazo terminó y devuelve sus unidades. Cada pedido se
    procesa con su fila bloqueada: si otro proceso lo está tocando (o ya lo venció) se saltea.
    Devuelve la cantidad de pedidos vencidos."""
    vencidos = 0
    for pedido_id in list(reservas_vencidas(ahora).values_list('pk', flat=True)):
        with transaction.atomic():
            pedido = (
                Pedido.objects.select_for_update(skip_locked=True)
                .filter(pk=pedido_id, estado='pendiente')
                .first()
            )
            # Mercado Pago: si el pago ya se registró, no se vence
            if not pedido or (pedido.metodo_pago == 'mercado_pago' and hasattr(pedido, 'pago')):
                continue
            reponer_stock_pedido(pedido)
            pedido.estado = 'vencido'
            pedido.deuda = 0
            pedido.save(update_fields=['estado', 'deuda', 'stock_descontado'])
            vencidos += 1
    if vencidos:
        logger.info('Pedidos pendientes vencidos por falta de pago: %s', vencidos)
    return vencidos


def vencer_reservas_si_corresponde():
    """Igual que vencer_reservas pero, como mucho, una vez cada INTERVALO_REVISION_RESERVAS por
    proceso. Pensado para llamarse en cada request sin costo. Nunca corta el request."""
    if not cache.add('pedidos_revision_reservas', 1, timeout=INTERVALO_REVISION_RESERVAS):
        return 0
    try:
        return vencer_reservas()
    except Exception:
        logger.exception('No se pudieron vencer las reservas de stock pendientes')
        return 0


def liberar_reservas_mercado_pago(cliente):
    """Un nuevo checkout reemplaza al intento anterior de pagar con Mercado Pago que quedó sin pagar
    (la clienta volvió sin pagar y prueba de nuevo): ese pedido vence y sus unidades vuelven al
    stock, así no se bloquea con su propia reserva. Si después igual paga aquel link, pago_exitoso
    lo reactiva si todavía hay stock."""
    pendientes = Pedido.objects.filter(
        cliente=cliente, estado='pendiente', metodo_pago='mercado_pago', pago__isnull=True
    ).values_list('pk', flat=True)
    for pedido_id in list(pendientes):
        with transaction.atomic():
            pedido = Pedido.objects.select_for_update().filter(pk=pedido_id, estado='pendiente').first()
            if not pedido:
                continue
            reponer_stock_pedido(pedido)
            pedido.estado = 'vencido'
            pedido.deuda = 0
            pedido.save(update_fields=['estado', 'deuda', 'stock_descontado'])
