"""Validaciones de Checkout Pro y autenticación de notificaciones."""
import hashlib
import hmac
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from django.conf import settings


def base_url():
    url = settings.SITE_URL.rstrip('/')
    partes = urlsplit(url)
    if (partes.scheme not in ('http', 'https') or not partes.hostname or
            partes.username or partes.password or partes.query or partes.fragment or
            partes.path or (not settings.DEBUG and partes.scheme != 'https')):
        raise ValueError('SITE_URL debe ser un origen público HTTPS, sin ruta ni parámetros.')
    return url


def items_preferencia(items, total):
    """No enviar precios cero/negativos ni introducir diferencias por redondeo."""
    total = Decimal(str(total))
    if not total.is_finite() or total <= 0:
        raise ValueError('Mercado Pago requiere un total mayor a cero. Elegí otro medio de pago.')
    validos = bool(items)
    suma = Decimal('0')
    for item in items:
        try:
            precio = Decimal(str(item['unit_price']))
            cantidad = item['quantity']
            if not precio.is_finite() or precio <= 0 or type(cantidad) is not int or cantidad <= 0:
                validos = False
                break
            suma += precio * cantidad
        except (KeyError, TypeError, InvalidOperation):
            validos = False
            break
    if not validos or suma != total:
        return [{'title': 'Compra IndiraGold (productos y envío)', 'quantity': 1,
                 'currency_id': 'ARS', 'unit_price': float(total)}]
    return items


def firma_valida(request):
    secret = getattr(settings, 'MERCADO_PAGO_WEBHOOK_SECRET', '')
    resource_id = request.GET.get('data.id', '')
    request_id = request.headers.get('x-request-id', '')
    firma = request.headers.get('x-signature', '')
    try:
        partes = dict(parte.strip().split('=', 1) for parte in firma.split(','))
        ts, recibida = partes['ts'], partes['v1']
    except (ValueError, KeyError):
        return False
    if not secret or not resource_id or not request_id or not ts.isdigit():
        return False
    manifiesto = f'id:{resource_id.lower()};request-id:{request_id};ts:{ts};'
    esperada = hmac.new(secret.encode(), manifiesto.encode(), hashlib.sha256).hexdigest()
    # Un reintento legítimo puede llegar mucho después: idempotencia por pedido/pago.
    return hmac.compare_digest(esperada, recibida)
