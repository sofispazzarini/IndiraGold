import json
import os
import base64
from dataclasses import dataclass
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.core.files.base import ContentFile


class ErrorEnvio(Exception):
    pass


PAQUETES_ENVIO = {
    'chico': {'weight': 300, 'height': 4, 'width': 20, 'length': 25},
    'mediano': {'weight': 700, 'height': 8, 'width': 25, 'length': 35},
    'grande': {'weight': 1200, 'height': 12, 'width': 35, 'length': 45},
}


@dataclass
class ConfigProveedor:
    nombre: str
    base_url: str
    token: str
    usuario: str
    password: str
    auth_endpoint: str
    cotizar_endpoint: str
    customer_id: str
    postal_code_origin: str
    crear_endpoint: str
    etiqueta_endpoint: str

    @property
    def configurado(self):
        tiene_token = bool(self.token)
        tiene_login = bool(self.usuario and self.password and self.auth_endpoint)
        return bool(self.base_url and (tiene_token or tiene_login) and self.crear_endpoint and self.etiqueta_endpoint)


def decimal_a_float(valor):
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


def paquete_producto(producto):
    return PAQUETES_ENVIO.get(getattr(producto, 'tamano_paquete', 'mediano'), PAQUETES_ENVIO['mediano'])


def calcular_paquete_envio(items):
    paquete = {
        'weight': 0,
        'height': 0,
        'width': PAQUETES_ENVIO['chico']['width'],
        'length': PAQUETES_ENVIO['chico']['length'],
    }

    for item in items:
        producto = item.variante.producto
        cantidad = int(getattr(item, 'cantidad', 1) or 1)
        dimensiones = paquete_producto(producto)

        paquete['weight'] += dimensiones['weight'] * cantidad
        paquete['height'] += dimensiones['height'] * cantidad
        paquete['width'] = max(paquete['width'], dimensiones['width'])
        paquete['length'] = max(paquete['length'], dimensiones['length'])

    if paquete['weight'] <= 0:
        return dict(PAQUETES_ENVIO['mediano'])

    paquete['weight'] = min(paquete['weight'], 25000)
    paquete['height'] = max(paquete['height'], 1)
    return paquete


def datos_direccion(pedido):
    direccion = pedido.direccion
    if not direccion:
        return {}

    return {
        'calle': direccion.calle,
        'numero': direccion.numero,
        'ciudad': direccion.ciudad,
        'provincia': direccion.provincia,
        'codigo_postal': direccion.codigo_postal,
        'referencia': direccion.referencia or '',
    }


def payload_envio(envio):
    pedido = envio.pedido
    cliente = pedido.cliente
    user = cliente.user
    items = pedido.items.select_related('variante__producto')

    return {
        'pedido_id': pedido.id,
        'proveedor': envio.proveedor,
        'tipo_entrega': envio.tipo_entrega,
        'sucursal': envio.sucursal or '',
        'costo_envio': decimal_a_float(envio.costo),
        'paquete': calcular_paquete_envio(items),
        'cliente': {
            'nombre': f'{user.first_name} {user.last_name}'.strip() or user.username,
            'email': user.email,
            'telefono': cliente.telefono,
            'dni': cliente.dni,
        },
        'destino': datos_direccion(pedido),
        'items': [
            {
                'sku': item.variante.producto.codigo,
                'nombre': item.variante.producto.nombre,
                'cantidad': item.cantidad,
                'precio': decimal_a_float(item.precio_unitario),
            }
            for item in items
        ],
    }


def config_proveedor(proveedor):
    prefijo = 'CORREO_ARGENTINO'
    return ConfigProveedor(
        nombre=proveedor,
        base_url=(os.getenv(f'{prefijo}_API_BASE_URL') or '').rstrip('/'),
        token=os.getenv(f'{prefijo}_API_TOKEN') or '',
        usuario=os.getenv(f'{prefijo}_API_USER') or '',
        password=os.getenv(f'{prefijo}_API_PASSWORD') or '',
        auth_endpoint=os.getenv(f'{prefijo}_AUTH_ENDPOINT') or '',
        cotizar_endpoint=os.getenv(f'{prefijo}_COTIZAR_ENDPOINT') or '',
        customer_id=os.getenv(f'{prefijo}_CUSTOMER_ID') or '',
        postal_code_origin=os.getenv(f'{prefijo}_POSTAL_CODE_ORIGIN') or '',
        crear_endpoint=os.getenv(f'{prefijo}_CREAR_ENVIO_ENDPOINT') or '',
        etiqueta_endpoint=os.getenv(f'{prefijo}_ETIQUETA_ENDPOINT') or '',
    )


def request_json(method, url, token, data=None):
    body = json.dumps(data or {}).encode('utf-8') if data is not None else None
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    if token:
        headers['Authorization'] = f'Bearer {token}'

    request = Request(
        url,
        data=body,
        method=method,
        headers=headers,
    )

    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            if not raw:
                return {}
            return json.loads(raw.decode('utf-8'))
    except HTTPError as error:
        detalle = error.read().decode('utf-8', errors='ignore')
        raise ErrorEnvio(f'La API respondio {error.code}: {detalle or error.reason}')
    except URLError as error:
        raise ErrorEnvio(f'No se pudo conectar con la API: {error.reason}')
    except json.JSONDecodeError:
        raise ErrorEnvio('La API no devolvio JSON valido.')


def request_basic_json(method, url, usuario, password):
    credenciales = base64.b64encode(f'{usuario}:{password}'.encode('utf-8')).decode('ascii')
    request = Request(
        url,
        method=method,
        headers={
            'Authorization': f'Basic {credenciales}',
            'Accept': 'application/json',
        },
    )

    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            if not raw:
                return {}
            return json.loads(raw.decode('utf-8'))
    except HTTPError as error:
        detalle = error.read().decode('utf-8', errors='ignore')
        raise ErrorEnvio(f'La API respondio {error.code}: {detalle or error.reason}')
    except URLError as error:
        raise ErrorEnvio(f'No se pudo conectar con la API: {error.reason}')
    except json.JSONDecodeError:
        raise ErrorEnvio('La API no devolvio JSON valido.')


def obtener_token(config):
    if config.token:
        return config.token

    auth_url = f'{config.base_url}{config.auth_endpoint}'
    respuesta = request_basic_json('POST', auth_url, config.usuario, config.password)
    token = (
        respuesta.get('token')
        or respuesta.get('access_token')
        or respuesta.get('bearer')
        or respuesta.get('jwt')
    )
    if not token:
        raise ErrorEnvio('La API autentico, pero no devolvio token reconocible.')
    return token


def request_bytes(url, token):
    request = Request(
        url,
        method='GET',
        headers={
            'Authorization': f'Bearer {token}',
            'Accept': 'application/pdf',
        },
    )

    try:
        with urlopen(request, timeout=30) as response:
            return response.read()
    except HTTPError as error:
        detalle = error.read().decode('utf-8', errors='ignore')
        raise ErrorEnvio(f'La API respondio {error.code}: {detalle or error.reason}')
    except URLError as error:
        raise ErrorEnvio(f'No se pudo descargar la etiqueta: {error.reason}')


def completar_endpoint(endpoint, envio, tracking=''):
    return (
        endpoint
        .replace('{pedido_id}', str(envio.pedido_id))
        .replace('{tracking}', str(tracking or envio.tracking or ''))
    )


def extraer_importe_cotizacion(respuesta):
    # Verificar si rates está vacío
    if isinstance(respuesta, dict) and respuesta.get('rates') == []:
        raise ErrorEnvio('Correo Argentino no tiene tarifas para esta ruta. Verifica que tu cuenta tenga cotizacion habilitada.')

    candidatos = [
        respuesta,
        respuesta.get('rate') if isinstance(respuesta, dict) else None,
        respuesta.get('rates', [{}])[0] if isinstance(respuesta, dict) and respuesta.get('rates') else None,
        respuesta.get('data') if isinstance(respuesta, dict) else None,
    ]

    for item in candidatos:
        if not isinstance(item, dict):
            continue
        for clave in ['total', 'amount', 'price', 'precio', 'importe', 'valor', 'shipping_cost']:
            valor = item.get(clave)
            if valor not in [None, '']:
                return Decimal(str(valor)).quantize(Decimal('0.01'))

    raise ErrorEnvio('La API cotizo, pero no devolvio un importe reconocible.')


def cotizar_correo_argentino(codigo_postal, tipo_entrega='domicilio', items=None):
    config = config_proveedor('correo_argentino')
    if not (config.base_url and config.cotizar_endpoint and config.customer_id and config.postal_code_origin and (config.token or (config.usuario and config.password and config.auth_endpoint))):
        raise ErrorEnvio('Falta configurar la cotizacion de Correo Argentino MiCorreo.')

    token = obtener_token(config)
    url = f'{config.base_url}{config.cotizar_endpoint}'
    delivered_type = 'S' if tipo_entrega == 'sucursal' else 'D'
    dimensiones = calcular_paquete_envio(items or [])
    payload = {
        'customerId': config.customer_id,
        'postalCodeOrigin': config.postal_code_origin,
        'postalCodeDestination': codigo_postal,
        'deliveredType': delivered_type,
        'dimensions': dimensiones,
    }
    respuesta = request_json('POST', url, token, payload)
    return extraer_importe_cotizacion(respuesta), respuesta


def generar_etiqueta(envio):
    if envio.proveedor == 'flex':
        raise ErrorEnvio('Envio Flex no genera etiqueta de Correo Argentino.')
    if envio.proveedor == 'correo_argentino':
        raise ErrorEnvio('Correo Argentino MiCorreo solo cotiza/importa; la etiqueta se emite desde el portal MiCorreo.')

    config = config_proveedor(envio.proveedor)
    if not config.configurado:
        raise ErrorEnvio(
            'Faltan credenciales/endpoints del proveedor. Configura '
            f'API_BASE_URL, API_TOKEN o API_USER/API_PASSWORD/AUTH_ENDPOINT, '
            f'CREAR_ENVIO_ENDPOINT y ETIQUETA_ENDPOINT para {config.nombre}.'
        )

    token = obtener_token(config)
    crear_url = f'{config.base_url}{completar_endpoint(config.crear_endpoint, envio)}'
    respuesta = request_json('POST', crear_url, token, payload_envio(envio))
    tracking = (
        respuesta.get('tracking')
        or respuesta.get('numero_seguimiento')
        or respuesta.get('numeroEnvio')
        or respuesta.get('id')
    )

    if not tracking:
        raise ErrorEnvio('La API creo el envio pero no devolvio tracking/numero de envio.')

    etiqueta_url = f'{config.base_url}{completar_endpoint(config.etiqueta_endpoint, envio, tracking)}'
    etiqueta_pdf = request_bytes(etiqueta_url, token)

    envio.tracking = tracking
    envio.respuesta_api = respuesta
    envio.estado = 'etiqueta_generada'
    envio.error = ''
    envio.etiqueta.save(
        f'etiqueta_pedido_{envio.pedido_id}_{tracking}.pdf',
        ContentFile(etiqueta_pdf),
        save=False,
    )
    envio.save(update_fields=['tracking', 'respuesta_api', 'estado', 'error', 'etiqueta', 'updated_at'])
    return envio
