"""Cálculo único de descuentos de pago; los cupones conservan su base de productos."""
from decimal import Decimal, ROUND_HALF_UP

CENTAVO = Decimal('0.01')
CERO = Decimal('0.00')


def dinero(valor):
    return Decimal(str(valor)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def porcentaje_pago(configuracion, metodo):
    if metodo == 'transferencia' and configuracion.transferencia_activa:
        return configuracion.descuento_transferencia_porcentaje
    if metodo == 'efectivo':
        return configuracion.descuento_efectivo_porcentaje
    return CERO


def calcular_totales(subtotal, envio=0, porcentaje=0, descuento_cupon=0):
    """Redondea una sola vez el descuento sobre productos netos + envío.

    El porcentaje se pasa explícitamente para reutilizar el valor histórico del pedido.
    Nunca se suman porcentajes de medios diferentes.
    """
    subtotal, envio = dinero(subtotal), dinero(envio)
    porcentaje = Decimal(str(porcentaje))
    if not porcentaje.is_finite() or not CERO <= porcentaje <= 100:
        raise ValueError('El porcentaje debe estar entre 0 y 100.')
    cupon = min(max(dinero(descuento_cupon), CERO), subtotal)
    base = max(subtotal - cupon, CERO) + envio
    descuento = dinero(base * porcentaje / Decimal('100'))
    return {'porcentaje': porcentaje, 'descuento': descuento, 'total': base - descuento}
