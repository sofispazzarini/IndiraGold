"""Calcula la retención de los pagos de pedidos confirmados a mano antes de que se guardara.

Por defecto solo muestra lo que haría; con --aplicar escribe. Los porcentajes se pasan explícitos,
nunca se toman en silencio de la configuración actual. Solo toca los campos de retención de
PagoPedido (nunca total, monto_pagado, deuda ni stock) y solo filas con retención NULL, así que es
idempotente. Se deshace volviendo a NULL las filas con retencion_origen='recalculada'.

Las ventas del local (PagoVentaLocal sin medio, anteriores al 12/10/2026) solo se listan para
revisarlas con la clienta: no se modifican.
"""
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from pedidos.costos_cobro import redondear
from pedidos.models import PagoPedido, PagoVentaLocal, Pedido

INICIO_RETENCION_POR_COBRO = date(2026, 10, 12)


def _fecha(valor):
    try:
        return date.fromisoformat(valor)
    except ValueError as error:
        raise CommandError(f'Fecha inválida "{valor}": usá AAAA-MM-DD.') from error


def _porcentaje(valor):
    try:
        porcentaje = Decimal(valor)
    except (InvalidOperation, ValueError) as error:
        raise CommandError(f'Porcentaje inválido "{valor}".') from error
    if not porcentaje.is_finite() or not Decimal('0') <= porcentaje <= Decimal('100'):
        raise CommandError('Los porcentajes deben estar entre 0 y 100.')
    return redondear(porcentaje)


def _inicio(dia):
    return timezone.make_aware(datetime.combine(dia, time.min))


def _fin(dia):
    return timezone.make_aware(datetime.combine(dia, time.max))


class Command(BaseCommand):
    help = 'Calcula la retención de pagos de pedidos con tarjeta o Mercado Pago confirmados a mano sin retención guardada.'

    def add_arguments(self, parser):
        parser.add_argument('--porcentaje-tarjeta', required=True, help='Porcentaje de tarjeta (ej. 15).')
        parser.add_argument('--porcentaje-mp', required=True, help='Porcentaje de Mercado Pago (ej. 15).')
        parser.add_argument('--desde', help='Fecha del pago desde (AAAA-MM-DD).')
        parser.add_argument('--hasta', help='Fecha del pago hasta (AAAA-MM-DD).')
        parser.add_argument('--aplicar', action='store_true', help='Guarda los cambios (sin esto solo muestra).')

    def handle(self, *args, **options):
        porcentajes = {
            'tarjeta': _porcentaje(options['porcentaje_tarjeta']),
            'mercado_pago': _porcentaje(options['porcentaje_mp']),
        }
        pagos = PagoPedido.objects.filter(
            metodo_pago__in=porcentajes.keys(),
            retencion__isnull=True,
            pedido__estado__in=Pedido.ESTADOS_CON_STOCK_DESCONTADO,
        ).select_related('pedido').order_by('fecha', 'pk')
        ventas_local = PagoVentaLocal.objects.filter(
            metodo_pago__isnull=True, fecha__lt=_inicio(INICIO_RETENCION_POR_COBRO),
        ).select_related('venta').order_by('fecha', 'pk')
        if options['desde']:
            desde = _inicio(_fecha(options['desde']))
            pagos = pagos.filter(fecha__gte=desde)
            ventas_local = ventas_local.filter(fecha__gte=desde)
        if options['hasta']:
            hasta = _fin(_fecha(options['hasta']))
            pagos = pagos.filter(fecha__lte=hasta)
            ventas_local = ventas_local.filter(fecha__lte=hasta)

        aplicar = options['aplicar']
        total = Decimal('0.00')
        cantidad = 0
        with transaction.atomic():
            for pago in pagos.select_for_update(of=('self',)) if aplicar else pagos:
                porcentaje = porcentajes[pago.metodo_pago]
                retencion = redondear(pago.monto * porcentaje / Decimal('100'))
                total += retencion
                cantidad += 1
                self.stdout.write(
                    f'Pedido #{pago.pedido_id} · pago {pago.pk} · {pago.fecha:%d/%m/%Y} · '
                    f'{pago.get_metodo_pago_display()} ${pago.monto} → retención {porcentaje}% = ${retencion}'
                )
                if aplicar:
                    PagoPedido.objects.filter(pk=pago.pk, retencion__isnull=True).update(
                        retencion_porcentaje=porcentaje, retencion=retencion, retencion_origen='recalculada',
                    )

        accion = 'Guardadas' if aplicar else 'Se guardarían (usá --aplicar)'
        self.stdout.write(self.style.SUCCESS(f'{accion}: {cantidad} retenciones de pedidos por ${total}.'))

        filas_local = list(ventas_local)
        if filas_local:
            self.stdout.write(self.style.WARNING(
                f'\nVentas del local para revisar con la clienta (no se modifican): {len(filas_local)} cobros '
                f'sin medio de pago anteriores al {INICIO_RETENCION_POR_COBRO:%d/%m/%Y}.'
            ))
            for pago in filas_local:
                self.stdout.write(
                    f'Venta #{pago.venta_id} · cobro {pago.pk} · {pago.fecha:%d/%m/%Y} · ${pago.monto} · '
                    f'retención guardada en la venta: ${pago.venta.retencion or 0}'
                )
