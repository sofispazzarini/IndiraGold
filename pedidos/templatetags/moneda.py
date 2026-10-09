"""Formato de moneda argentino para todos los templates (registrado como builtin en settings).

    {{ 1062500|pesos }}      -> $1.062.500
    {{ 16149.99|pesos }}     -> $16.149,99
    {{ 1062500|pesos_numero }} -> 1.062.500   (cuando el "$" ya está en el markup)
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import template

register = template.Library()


@register.filter
def hex_color(color_nombre, codigo_hex=None):
    """Color CSS para el puntito de un color: el hex guardado o, si es el gris por defecto,
    el que corresponde al nombre ("Marrón" -> marrón)."""
    from productos.views import normalizar_hex_color
    return normalizar_hex_color(color_nombre, codigo_hex)


def formatear_numero(valor):
    try:
        monto = Decimal(str(valor if valor not in (None, '') else 0).replace(',', '.'))
    except (InvalidOperation, ValueError):
        return str(valor)
    if not monto.is_finite():
        return str(valor)
    monto = monto.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    signo = '-' if monto < 0 else ''
    entero, _, centavos = f'{abs(monto):.2f}'.partition('.')
    entero = f'{int(entero):,}'.replace(',', '.')
    if centavos == '00':
        return f'{signo}{entero}'
    return f'{signo}{entero},{centavos}'


@register.filter
def pesos(valor):
    numero = formatear_numero(valor)
    if numero.startswith('-'):
        return f'-${numero[1:]}'
    return f'${numero}'


@register.filter
def pesos_numero(valor):
    return formatear_numero(valor)
