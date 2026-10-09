from django.conf import settings


def whatsapp_numero():
    """Número de WhatsApp de la tienda (solo dígitos), configurable con COMPROBANTE_WHATSAPP."""
    return ''.join(caracter for caracter in str(settings.COMPROBANTE_WHATSAPP or '') if caracter.isdigit())


def whatsapp_numero_visible():
    """Mismo número en formato legible, ej. 5492216375660 -> +54 9 221 637 5660."""
    numero = whatsapp_numero()
    if len(numero) == 13 and numero.startswith('549'):
        return f'+54 9 {numero[3:6]} {numero[6:9]} {numero[9:]}'
    return f'+{numero}' if numero else ''


def contacto_tienda(request):
    """Context processor: WhatsApp de la tienda para el footer de todas las páginas públicas."""
    return {'whatsapp_tienda': whatsapp_numero(), 'whatsapp_tienda_visible': whatsapp_numero_visible()}
