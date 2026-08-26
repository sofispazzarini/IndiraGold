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


CODIGOS_PROVINCIA = {
    'salta': 'A', 'buenos aires': 'B', 'caba': 'C', 'ciudad autonoma de buenos aires': 'C',
    'san luis': 'D', 'entre rios': 'E', 'la rioja': 'F', 'santiago del estero': 'G',
    'chaco': 'H', 'san juan': 'J', 'catamarca': 'K', 'la pampa': 'L', 'mendoza': 'M',
    'misiones': 'N', 'formosa': 'P', 'neuquen': 'Q', 'rio negro': 'R', 'santa fe': 'S',
    'tucuman': 'T', 'chubut': 'U', 'tierra del fuego': 'V', 'corrientes': 'W',
    'cordoba': 'X', 'jujuy': 'Y', 'santa cruz': 'Z',
}


def normalizar_provincia(provincia):
    if not provincia:
        return 'B'
    provincia_lower = provincia.lower().strip()
    provincia_lower = provincia_lower.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')
    return CODIGOS_PROVINCIA.get(provincia_lower, 'B')


def request_paqar(method, url, api_key, agreement, data=None):
    body = json.dumps(data).encode('utf-8') if data is not None else None
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Apikey {api_key}',
        'agreement': str(agreement),
    }

    request = Request(url, data=body, method=method, headers=headers)

    try:
        with urlopen(request, timeout=60) as response:
            raw = response.read()
            if not raw:
                return {}
            return json.loads(raw.decode('utf-8'))
    except HTTPError as error:
        detalle = error.read().decode('utf-8', errors='ignore')
        raise ErrorEnvio(f'PAQ.AR respondio {error.code}: {detalle or error.reason}')
    except URLError as error:
        raise ErrorEnvio(f'No se pudo conectar con PAQ.AR: {error.reason}')
    except json.JSONDecodeError:
        raise ErrorEnvio('PAQ.AR no devolvio JSON valido.')


def config_paqar():
    return {
        'base_url': (os.getenv('PAQAR_API_BASE_URL') or '').rstrip('/'),
        'api_key': os.getenv('PAQAR_API_KEY') or '',
        'agreement': os.getenv('PAQAR_AGREEMENT') or '',
    }


def paqar_configurado():
    cfg = config_paqar()
    return bool(cfg['base_url'] and cfg['api_key'] and cfg['agreement'])


def crear_envio_paqar(envio):
    cfg = config_paqar()
    if not paqar_configurado():
        raise ErrorEnvio('Falta configurar PAQ.AR 2.0 (PAQAR_API_BASE_URL, PAQAR_API_KEY, PAQAR_AGREEMENT).')

    pedido = envio.pedido
    cliente = pedido.cliente
    user = cliente.user
    items = pedido.items.select_related('variante__producto')
    direccion = pedido.direccion
    paquete = calcular_paquete_envio(items)

    from datetime import datetime
    fecha_venta = datetime.now().strftime('%Y-%m-%dT%H:%M:%S-03:00')

    nombre_cliente = f'{user.first_name} {user.last_name}'.strip() or user.username
    email_cliente = user.email or ''
    telefono_cliente = cliente.telefono or ''

    provincia_destino = normalizar_provincia(direccion.provincia if direccion else '')
    tipo_entrega = 'homeDelivery' if envio.tipo_entrega == 'domicilio' else 'agency'

    config_correo = config_proveedor('correo_argentino')

    payload = {
        'sellerId': cfg['agreement'],
        'order': {
            'senderData': {
                'id': cfg['agreement'],
                'businessName': 'Indira Gold',
                'areaCodePhone': '221',
                'phoneNumber': '6375660',
                'email': 'indiragoldoficial@gmail.com',
                'observation': '',
                'address': {
                    'streetName': 'Direccion de origen',
                    'streetNumber': '123',
                    'cityName': 'La Plata',
                    'floor': '',
                    'department': '',
                    'state': 'B',
                    'zipCode': config_correo.postal_code_origin or '1894',
                }
            },
            'shippingData': {
                'name': nombre_cliente,
                'areaCodePhone': '',
                'phoneNumber': telefono_cliente,
                'areaCodeCellphone': '',
                'cellphoneNumber': telefono_cliente,
                'email': email_cliente,
                'observation': f'Pedido #{pedido.id}',
                'address': {
                    'streetName': direccion.calle if direccion else '',
                    'streetNumber': direccion.numero if direccion else '',
                    'cityName': direccion.ciudad if direccion else '',
                    'floor': '',
                    'department': '',
                    'state': provincia_destino,
                    'zipCode': direccion.codigo_postal if direccion else '',
                }
            },
            'parcels': [{
                'dimensions': {
                    'height': str(paquete['height']),
                    'width': str(paquete['width']),
                    'depth': str(paquete['length']),
                },
                'productWeight': str(paquete['weight']),
                'productCategory': 'Indumentaria',
                'declaredValue': str(int(pedido.total)),
            }],
            'deliveryType': tipo_entrega,
            'agencyId': envio.sucursal or '',
            'saleDate': fecha_venta,
            'serviceType': 'CP',
            'shipmentClientId': str(pedido.id),
        }
    }

    url = f"{cfg['base_url']}/orders"
    respuesta = request_paqar('POST', url, cfg['api_key'], cfg['agreement'], payload)

    tracking = respuesta.get('trackingNumber') or respuesta.get('tracking')
    if not tracking:
        raise ErrorEnvio('PAQ.AR creo el envio pero no devolvio trackingNumber.')

    return tracking, respuesta


def obtener_etiqueta_paqar(tracking):
    cfg = config_paqar()
    if not paqar_configurado():
        raise ErrorEnvio('Falta configurar PAQ.AR 2.0.')

    url = f"{cfg['base_url']}/labels?labelFormat=10x15"
    payload = [{
        'sellerId': cfg['agreement'],
        'trackingNumber': tracking,
    }]

    respuesta = request_paqar('POST', url, cfg['api_key'], cfg['agreement'], payload)

    if not respuesta or not isinstance(respuesta, list) or len(respuesta) == 0:
        raise ErrorEnvio('PAQ.AR no devolvio datos de etiqueta.')

    etiqueta_data = respuesta[0]
    if etiqueta_data.get('result', '').startswith('ERROR'):
        raise ErrorEnvio(f"Error al obtener etiqueta: {etiqueta_data.get('result')}")

    file_base64 = etiqueta_data.get('fileBase64')
    if not file_base64:
        raise ErrorEnvio('PAQ.AR no devolvio el archivo de etiqueta.')

    return base64.b64decode(file_base64)


def buscar_sucursales_paqar(codigo_postal=None, provincia=None, localidad=None):
    cfg = config_paqar()
    if not paqar_configurado():
        raise ErrorEnvio('Falta configurar PAQ.AR 2.0.')

    params = []
    if codigo_postal:
        params.append(f'zipCode={codigo_postal}')
    if provincia:
        codigo_prov = normalizar_provincia(provincia)
        params.append(f'state={codigo_prov}')
    if localidad:
        params.append(f'city={localidad}')

    query = '&'.join(params) if params else ''
    url = f"{cfg['base_url']}/agencies"
    if query:
        url = f"{url}?{query}"

    try:
        respuesta = request_paqar('GET', url, cfg['api_key'], cfg['agreement'])
    except ErrorEnvio:
        return []

    if not respuesta:
        return []

    # La respuesta puede venir como lista directa o dentro de un objeto
    if isinstance(respuesta, dict):
        agencias = respuesta.get('agencies') or respuesta.get('data') or respuesta.get('items') or []
    elif isinstance(respuesta, list):
        agencias = respuesta
    else:
        return []

    sucursales = []
    for agencia in agencias:
        # Intentar múltiples nombres de campos
        direccion = agencia.get('address', {}) if isinstance(agencia.get('address'), dict) else {}

        # Campos del nombre
        nombre = (
            agencia.get('name') or
            agencia.get('nombre') or
            agencia.get('agencyName') or
            agencia.get('description') or
            ''
        )

        # Campos de dirección
        calle = (
            direccion.get('streetName') or
            direccion.get('street') or
            direccion.get('calle') or
            agencia.get('street') or
            agencia.get('address') if isinstance(agencia.get('address'), str) else ''
        )
        numero = direccion.get('streetNumber') or direccion.get('number') or ''
        dir_completa = f"{calle} {numero}".strip() if calle else ''

        # Campos de ciudad
        ciudad = (
            direccion.get('cityName') or
            direccion.get('city') or
            direccion.get('ciudad') or
            agencia.get('city') or
            agencia.get('ciudad') or
            ''
        )

        # Campos de código postal
        cp = (
            direccion.get('zipCode') or
            direccion.get('postalCode') or
            direccion.get('cp') or
            agencia.get('zipCode') or
            agencia.get('postalCode') or
            ''
        )

        # Campos de coordenadas
        lat = (
            agencia.get('latitude') or
            agencia.get('lat') or
            direccion.get('latitude') or
            direccion.get('lat')
        )
        lng = (
            agencia.get('longitude') or
            agencia.get('lng') or
            agencia.get('lon') or
            direccion.get('longitude') or
            direccion.get('lng')
        )

        sucursales.append({
            'id': str(agencia.get('agencyId') or agencia.get('id') or agencia.get('codigo') or ''),
            'nombre': nombre,
            'direccion': dir_completa,
            'ciudad': ciudad,
            'provincia': direccion.get('state') or agencia.get('state') or agencia.get('provincia') or '',
            'codigo_postal': str(cp) if cp else '',
            'latitud': lat,
            'longitud': lng,
            'horario': agencia.get('schedule') or agencia.get('horario') or '',
            '_raw': agencia,  # Para debug
        })

    return sucursales


def generar_etiqueta(envio):
    if envio.proveedor == 'flex':
        raise ErrorEnvio('Envio Flex no genera etiqueta de Correo Argentino.')

    if envio.proveedor == 'correo_argentino':
        if not paqar_configurado():
            raise ErrorEnvio('Falta configurar PAQ.AR 2.0 para generar etiquetas de Correo Argentino.')

        tracking, respuesta = crear_envio_paqar(envio)
        etiqueta_pdf = obtener_etiqueta_paqar(tracking)

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
