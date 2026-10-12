"""
Costos de cobro: lo que cuesta cobrar cada venta.

- Pagos online con Mercado Pago: se usan los importes que informa la API en cada pago
  (GET /v1/payments/{id}). Lo que la API no informa queda en None (desconocido), nunca en 0.
- Cobros en el local: no hay datos de la API; se estima con el porcentaje que carga la
  administradora para cada medio (Posnet para tarjeta, Mercado Pago en el local).

Sin dependencias de las vistas: lo usan las vistas de pago y el comando de diagnóstico.
"""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

METODOS_PAGO_PRESENCIAL = ('efectivo', 'mercado_pago', 'tarjeta')


def redondear(valor):
    return Decimal(valor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def importe_mercado_pago(valor):
    """Importe informado por la API con 2 decimales, o None si no viene o no es un número válido."""
    if valor is None or valor == '' or isinstance(valor, bool):
        return None
    try:
        importe = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None
    return redondear(importe) if importe.is_finite() else None


def desglose_pago_mercado_pago(detalle_pago):
    """Importes de un pago según la respuesta de GET /v1/payments/{id}, para cualquier medio (dinero en
    cuenta, débito, crédito en 1 pago o en cuotas):
    - bruto: transaction_amount (lo que cobra el comercio, sin los cargos que paga la clienta).
    - neto: transaction_details.net_received_amount (lo que acredita Mercado Pago).
    - costos_comercio: cargos de fee_details que paga el comercio (fee_payer "collector"): comisión y
      costo de ofrecer cuotas sin interés.
    - cargos_cliente: cargos de fee_details que paga la clienta (fee_payer "payer"), como el interés de
      cuotas con interés. No son costo del comercio.
    - otros_descuentos: bruto - costos_comercio - neto: retenciones impositivas u otros descuentos que
      la API solo refleja en el neto. Así ningún cargo se descuenta dos veces.
    Lo que la API no informa queda en None (desconocido), nunca en 0."""
    detalle = detalle_pago if isinstance(detalle_pago, dict) else {}
    transaccion = detalle.get('transaction_details')
    transaccion = transaccion if isinstance(transaccion, dict) else {}
    bruto = importe_mercado_pago(detalle.get('transaction_amount'))
    neto = importe_mercado_pago(transaccion.get('net_received_amount'))

    costos_comercio = cargos_cliente = None
    cargos = detalle.get('fee_details')
    if isinstance(cargos, list):
        costos_comercio = cargos_cliente = Decimal('0.00')
        for cargo in cargos:
            importe = importe_mercado_pago(cargo.get('amount')) if isinstance(cargo, dict) else None
            pagador = cargo.get('fee_payer') if isinstance(cargo, dict) else None
            if importe is None or pagador not in ('collector', 'payer'):
                # Un cargo sin importe o sin saber quién lo paga: el desglose queda desconocido
                costos_comercio = cargos_cliente = None
                break
            if pagador == 'collector':
                costos_comercio += importe
            else:
                cargos_cliente += importe

    otros_descuentos = None
    if bruto is not None and neto is not None:
        otros_descuentos = bruto - neto - (costos_comercio or Decimal('0.00'))

    return {
        'bruto': bruto,
        'neto': neto,
        'costos_comercio': costos_comercio,
        'cargos_cliente': cargos_cliente,
        'otros_descuentos': otros_descuentos,
    }


def campos_costos_pago(desglose):
    """Campos de Pago con los importes del desglose (None = no informado por la API)."""
    return {
        'retencion_mercado_pago': desglose['costos_comercio'],
        'neto_recibido': desglose['neto'],
        'cargos_cliente_mercado_pago': desglose['cargos_cliente'],
        'otros_descuentos_mercado_pago': desglose['otros_descuentos'],
    }


def retencion_cobro_presencial(monto, metodo_pago, configuracion=None):
    """Retención estimada de un cobro en el local con el porcentaje que carga la administradora:
    el de Posnet solo para tarjeta y el de Mercado Pago en el local para Mercado Pago. Efectivo no
    tiene. Es una estimación manual: en el local no hay datos de la API de Mercado Pago."""
    if not monto or monto <= 0:
        return Decimal('0.00')
    if metodo_pago not in ('tarjeta', 'mercado_pago', 'mercado_pago_qr'):
        return Decimal('0.00')
    if configuracion is None:
        from .models import ConfiguracionPago
        configuracion = ConfiguracionPago.actual()
    if metodo_pago == 'tarjeta':
        porcentaje = configuracion.retencion_tarjeta_porcentaje
    else:
        porcentaje = configuracion.retencion_mercado_pago_presencial_porcentaje
    return redondear(Decimal(monto) * (porcentaje or Decimal('0')) / Decimal('100'))
