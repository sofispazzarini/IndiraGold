from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from pedidos.costos_cobro import desglose_pago_mercado_pago
from pedidos.models import Pago


def texto(valor):
    return '?' if valor is None else f'{valor:.2f}'


class Command(BaseCommand):
    help = (
        'SOLO LECTURA: compara los costos y el neto guardados en cada pago de Mercado Pago con los que '
        'resultan de la respuesta de la API ya guardada (Pago.detalle_mercado_pago). No modifica nada. '
        'No muestra datos personales: solo ids e importes. "?" = la API no informó ese dato.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--desde', help='Fecha del pago desde (AAAA-MM-DD).')
        parser.add_argument('--hasta', help='Fecha del pago hasta (AAAA-MM-DD).')
        parser.add_argument('--solo-diferencias', action='store_true', help='Muestra solo los pagos con diferencias.')

    def fecha(self, valor, nombre):
        try:
            return datetime.strptime(valor, '%Y-%m-%d').date()
        except ValueError:
            raise CommandError(f'--{nombre} tiene que tener el formato AAAA-MM-DD.')

    def handle(self, *args, **options):
        # Los pagos sin respuesta guardada se saltean en Python (sin comparar JSON en la base: igual en PostgreSQL y MySQL)
        pagos = Pago.objects.order_by('id')
        if options['desde']:
            pagos = pagos.filter(fecha_pago__date__gte=self.fecha(options['desde'], 'desde'))
        if options['hasta']:
            pagos = pagos.filter(fecha_pago__date__lte=self.fecha(options['hasta'], 'hasta'))

        self.stdout.write(
            'pago;pedido;fecha;medio;cuotas;bruto;costos_guardados;costos_api;neto_guardado;neto_api;'
            'cargos_clienta;otros_descuentos;estado'
        )
        resumen = {'pagos': 0, 'con_diferencias': 0, 'sin_datos': 0, 'neto_api': Decimal('0.00'), 'neto_guardado': Decimal('0.00')}
        for pago in pagos.only(
            'id', 'pedido_id', 'fecha_pago', 'retencion_mercado_pago', 'neto_recibido', 'detalle_mercado_pago'
        ).iterator():
            detalle = pago.detalle_mercado_pago if isinstance(pago.detalle_mercado_pago, dict) else {}
            if not detalle:
                continue
            desglose = desglose_pago_mercado_pago(detalle)
            if desglose['costos_comercio'] is None and desglose['neto'] is None:
                estado = 'SIN DATOS EN LA API'
                resumen['sin_datos'] += 1
            elif (desglose['costos_comercio'], desglose['neto']) != (pago.retencion_mercado_pago, pago.neto_recibido):
                estado = 'DIFERENCIA'
                resumen['con_diferencias'] += 1
            else:
                estado = 'OK'
            if desglose['otros_descuentos'] is not None and desglose['otros_descuentos'] < 0:
                estado += ' (neto mayor que bruto - costos: revisar)'
            resumen['pagos'] += 1
            resumen['neto_api'] += desglose['neto'] or Decimal('0.00')
            resumen['neto_guardado'] += pago.neto_recibido or Decimal('0.00')
            if options['solo_diferencias'] and estado == 'OK':
                continue
            self.stdout.write(';'.join([
                str(pago.id),
                str(pago.pedido_id),
                pago.fecha_pago.strftime('%Y-%m-%d') if pago.fecha_pago else '',
                str(detalle.get('payment_type_id') or '?'),
                str(detalle.get('installments') or '?'),
                texto(desglose['bruto']),
                texto(pago.retencion_mercado_pago),
                texto(desglose['costos_comercio']),
                texto(pago.neto_recibido),
                texto(desglose['neto']),
                texto(desglose['cargos_cliente']),
                texto(desglose['otros_descuentos']),
                estado,
            ]))

        self.stdout.write(
            f"\nPagos revisados: {resumen['pagos']} | con diferencias: {resumen['con_diferencias']} | "
            f"sin datos en la API: {resumen['sin_datos']}\n"
            f"Neto guardado: {resumen['neto_guardado']:.2f} | neto según la API (solo los informados): {resumen['neto_api']:.2f}\n"
            'No se modificó ningún dato.'
        )
