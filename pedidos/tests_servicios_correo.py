"""Correo Argentino Clásico (CP) y Expreso (EP) en el checkout: cotización, elección del servicio,
pedido y etiqueta de PAQ.AR. La API de MiCorreo, Mercado Pago y PAQ.AR se simulan: estas pruebas no
consultan tarifas reales."""
from decimal import Decimal
from unittest import mock

from django.contrib.messages import get_messages
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from pedidos import servicios_envio
from pedidos.models import ConfiguracionEnvio, ConfiguracionPaquete, EnvioPedido, Pago, Pedido
from pedidos.servicios_envio import ConfigProveedor, ErrorEnvio, codigo_servicio_correo, extraer_servicios_correo
from pedidos.tests import DatosStockMixin
from users.models import Direccion

NOMBRES_API = {'CP': 'Paq.ar Clasico', 'EP': 'Paq.ar Expreso'}

CONFIG_CORREO_PRUEBA = ConfigProveedor(
    nombre='correo_argentino', base_url='https://correo.example.test', token='token-de-prueba', usuario='',
    password='', auth_endpoint='', cotizar_endpoint='/rates', customer_id='0001', postal_code_origin='1000',
    crear_endpoint='/shipping', etiqueta_endpoint='/label',
)


def tarifa(codigo, precio, minimo=None, maximo=None, entrega='D', nombre=None):
    """Una tarifa como las de la respuesta de MiCorreo (POST /rates)."""
    datos = {
        'deliveredType': entrega,
        'productType': codigo,
        'productName': NOMBRES_API.get(codigo, codigo) if nombre is None else nombre,
        'price': precio,
    }
    if minimo is not None:
        datos['deliveryTimeMin'] = minimo
    if maximo is not None:
        datos['deliveryTimeMax'] = maximo
    return datos


def servicios(cp='5000.00', ep='7000.00'):
    """Lo que devuelve cotizar_correo_argentino(), ya ordenado por precio."""
    lista = []
    if cp is not None:
        lista.append({'codigo': 'CP', 'nombre': NOMBRES_API['CP'], 'precio': Decimal(cp), 'plazo': '5 a 8 días'})
    if ep is not None:
        lista.append({'codigo': 'EP', 'nombre': NOMBRES_API['EP'], 'precio': Decimal(ep), 'plazo': '2 a 3 días'})
    return sorted(lista, key=lambda servicio: servicio['precio'])


class ExtraccionServiciosTests(SimpleTestCase):
    def test_extrae_clasico_y_expreso_con_codigo_nombre_precio_y_plazo(self):
        respuesta = {'validTo': '2026-10-13T00:00:00', 'rates': [
            tarifa('CP', 5000.5, '3', '6'),
            tarifa('EP', '7200', 1, 2),
            tarifa('XX', 100),
        ]}
        self.assertEqual(extraer_servicios_correo(respuesta, 'D'), [
            {'codigo': 'CP', 'nombre': 'Paq.ar Clasico', 'precio': Decimal('5000.50'), 'plazo': '3 a 6 días'},
            {'codigo': 'EP', 'nombre': 'Paq.ar Expreso', 'precio': Decimal('7200.00'), 'plazo': '1 a 2 días'},
        ])

    def test_ordena_por_precio_ascendente(self):
        respuesta = {'rates': [tarifa('CP', 9000), tarifa('EP', 4000)]}
        self.assertEqual([s['codigo'] for s in extraer_servicios_correo(respuesta, 'D')], ['EP', 'CP'])

    def test_el_plazo_sale_solo_de_delivery_time_min_y_max(self):
        respuesta = {'rates': [tarifa('CP', 5000, 2, 5), tarifa('EP', 7000, '1', '1')]}
        plazos = {s['codigo']: s['plazo'] for s in extraer_servicios_correo(respuesta, 'D')}
        self.assertEqual(plazos, {'CP': '2 a 5 días', 'EP': '1 día'})

    def test_sin_plazo_de_la_api_no_se_inventa(self):
        con_otros_campos = dict(tarifa('EP', 7000), deliveryTime='3', deliveryDays=3, estimatedDays='2')
        respuesta = {'rates': [tarifa('CP', 5000), con_otros_campos, tarifa('XX', 1, 1, 2)]}
        resultado = extraer_servicios_correo(respuesta, 'D')
        self.assertEqual([s['plazo'] for s in resultado], ['', ''])
        respuesta = {'rates': [tarifa('CP', 5000, 'abc', None), tarifa('EP', 7000, -1, '2.5')]}
        self.assertEqual([s['plazo'] for s in extraer_servicios_correo(respuesta, 'D')], ['', ''])
        for servicio in resultado:
            self.assertNotIn('hábiles', servicio['plazo'])

    def test_un_solo_extremo_del_plazo_no_se_completa(self):
        respuesta = {'rates': [tarifa('CP', 5000, None, 6), tarifa('EP', 7000, 2, None)]}
        plazos = {s['codigo']: s['plazo'] for s in extraer_servicios_correo(respuesta, 'D')}
        self.assertEqual(plazos, {'CP': 'Hasta 6 días', 'EP': 'Desde 2 días'})

    def test_ignora_tarifas_de_otra_modalidad(self):
        respuesta = {'rates': [tarifa('CP', 5000, entrega='S'), tarifa('EP', 7000, entrega='D')]}
        self.assertEqual([s['codigo'] for s in extraer_servicios_correo(respuesta, 'D')], ['EP'])
        self.assertEqual([s['codigo'] for s in extraer_servicios_correo(respuesta, 'S')], ['CP'])

    def test_sin_clasico_ni_expreso_responde_un_error(self):
        for respuesta in ({'rates': []}, {'rates': [tarifa('XX', 100)]}, {'rates': [tarifa('CP', 0)]}, {}):
            with self.assertRaises(ErrorEnvio):
                extraer_servicios_correo(respuesta, 'D')

    def test_el_nombre_guardado_identifica_siempre_al_servicio(self):
        respuesta = {'rates': [tarifa('CP', 5000, nombre=''), tarifa('EP', 7000, nombre='Servicio premium')]}
        nombres = {s['codigo']: s['nombre'] for s in extraer_servicios_correo(respuesta, 'D')}
        self.assertEqual(nombres, {'CP': 'Correo Argentino Clásico', 'EP': 'Correo Argentino Expreso'})
        for nombre in nombres.values():
            self.assertEqual(codigo_servicio_correo(nombre), 'EP' if 'Expreso' in nombre else 'CP')

    def test_codigo_del_servicio_segun_el_nombre(self):
        self.assertEqual(codigo_servicio_correo('Paq.ar Expreso'), 'EP')
        self.assertEqual(codigo_servicio_correo('CORREO ARGENTINO EXPRÉS'), 'EP')
        self.assertEqual(codigo_servicio_correo('Correo Argentino Clásico'), 'CP')
        self.assertEqual(codigo_servicio_correo(None), 'CP')
        self.assertEqual(codigo_servicio_correo(''), 'CP')


class TipoDeEntregaTests(DatosStockMixin, TestCase):
    def setUp(self):
        self.crear_datos()

    def payload(self, tipo_entrega):
        respuesta = {'rates': [tarifa('CP', 5000, entrega='S' if tipo_entrega == 'sucursal' else 'D')]}
        with mock.patch('pedidos.servicios_envio.config_proveedor', return_value=CONFIG_CORREO_PRUEBA), \
                mock.patch('pedidos.servicios_envio.obtener_token', return_value='token-de-prueba'), \
                mock.patch('pedidos.servicios_envio.request_json', return_value=respuesta) as request_json:
            servicios_envio.cotizar_correo_argentino('1900', tipo_entrega, [])
        return request_json.call_args[0][3]

    def test_domicilio_cotiza_con_delivered_type_d(self):
        self.assertEqual(self.payload('domicilio')['deliveredType'], 'D')

    def test_sucursal_cotiza_con_delivered_type_s(self):
        self.assertEqual(self.payload('sucursal')['deliveredType'], 'S')


class CheckoutCorreoMixin(DatosStockMixin):
    def preparar(self):
        self.crear_datos()
        ConfiguracionEnvio.objects.update_or_create(pk=1, defaults={'correo_activo': True})
        self.direccion = self.crear_direccion(self.cliente_a, '1900')
        self.llenar_carrito(self.cliente_a, [(self.remera_m, 1, None)])
        self.client_a = self.cliente_logueado(self.cliente_a)

    def crear_direccion(self, cliente, codigo_postal):
        return Direccion.objects.create(
            cliente=cliente, etiqueta='Casa', calle='Calle', numero='123', ciudad='La Plata',
            provincia='Buenos Aires', codigo_postal=codigo_postal,
        )

    def cotizar(self, lista=None, client=None, **datos):
        datos = {'tipo_correo': 'domicilio', 'direccion_correo_id': self.direccion.id, **datos}
        with mock.patch('pedidos.views.cotizar_correo_argentino', return_value=lista or servicios()) as cotizar:
            respuesta = (client or self.client_a).post(reverse('pedidos:cotizar_correo_argentino'), datos)
        return respuesta, cotizar

    def pagar(self, servicio='', lista=None, metodo_pago='transferencia', client=None, **extra):
        datos = {
            'metodo_entrega': 'correo', 'metodo_pago': metodo_pago, 'correo': 'correo_argentino',
            'tipo_correo': 'domicilio', 'direccion_correo_id': self.direccion.id, 'servicio_correo': servicio,
            **extra,
        }
        with mock.patch('pedidos.views.cotizar_correo_argentino', return_value=lista or servicios()) as cotizar:
            respuesta = (client or self.client_a).post(reverse('pedidos:crear_pago'), datos)
        return respuesta, cotizar

    def mensajes(self, respuesta):
        return ' '.join(str(mensaje) for mensaje in get_messages(respuesta.wsgi_request))


class CotizacionCheckoutTests(CheckoutCorreoMixin, TestCase):
    def setUp(self):
        self.preparar()

    def test_devuelve_los_servicios_y_elige_el_mas_barato(self):
        respuesta, cotizar = self.cotizar()
        datos = respuesta.json()
        self.assertTrue(datos['success'])
        self.assertEqual(datos['servicios'], [
            {'codigo': 'CP', 'nombre': 'Paq.ar Clasico', 'precio': '5000.00', 'plazo': '5 a 8 días'},
            {'codigo': 'EP', 'nombre': 'Paq.ar Expreso', 'precio': '7000.00', 'plazo': '2 a 3 días'},
        ])
        self.assertEqual(datos['servicio_seleccionado'], 'CP')
        self.assertEqual(cotizar.call_args[0][:2], ('1900', 'domicilio'))
        cotizacion = self.client_a.session['correo_cotizacion']
        self.assertEqual((cotizacion['servicio'], cotizacion['servicio_nombre']), ('CP', 'Paq.ar Clasico'))
        self.assertEqual([s['precio'] for s in cotizacion['servicios']], ['5000.00', '7000.00'])

    def test_si_el_expreso_es_mas_barato_queda_elegido_por_defecto(self):
        respuesta, _ = self.cotizar(servicios(cp='9000.00', ep='6000.00'))
        self.assertEqual(respuesta.json()['servicio_seleccionado'], 'EP')

    def test_recotizar_conserva_el_servicio_elegido_si_sigue_disponible(self):
        self.cotizar()
        self.assertEqual(self.cotizar(servicio_correo='EP')[0].json()['servicio_seleccionado'], 'EP')
        # Sin código en el pedido se usa el que quedó guardado en la sesión
        self.assertEqual(self.cotizar()[0].json()['servicio_seleccionado'], 'EP')
        # Si ya no está, pasa al más barato
        datos = self.cotizar(servicios(ep=None), servicio_correo='EP')[0].json()
        self.assertEqual(datos['servicio_seleccionado'], 'CP')
        self.assertEqual(self.client_a.session['correo_cotizacion']['servicio'], 'CP')

    def test_sucursal_cotiza_con_el_codigo_postal_de_la_sucursal(self):
        _, cotizar = self.cotizar(tipo_correo='sucursal', codigo_postal='B1878AAA', direccion_correo_id='')
        self.assertEqual(cotizar.call_args[0][:2], ('1878', 'sucursal'))

    def test_si_la_cotizacion_falla_no_queda_un_precio_anterior(self):
        self.cotizar()
        with mock.patch('pedidos.views.cotizar_correo_argentino', side_effect=ErrorEnvio('Sin tarifas.')):
            respuesta = self.client_a.post(reverse('pedidos:cotizar_correo_argentino'), {
                'tipo_correo': 'domicilio', 'direccion_correo_id': self.direccion.id,
            })
        self.assertEqual(respuesta.status_code, 400)
        self.assertNotIn('correo_cotizacion', self.client_a.session)


class EleccionServicioTests(CheckoutCorreoMixin, TestCase):
    def setUp(self):
        self.preparar()

    def test_sin_servicio_se_cobra_el_mas_barato(self):
        self.cotizar()
        self.pagar()
        pedido = Pedido.objects.get()
        self.assertEqual((pedido.costo_envio, pedido.tarifa_correo_nombre), (Decimal('5000.00'), 'Paq.ar Clasico'))
        self.assertEqual(pedido.total, Decimal('1000.00') + Decimal('5000.00'))

    def test_la_cotizacion_compatible_se_reutiliza(self):
        self.cotizar()
        _, cotizar = self.pagar('EP')
        cotizar.assert_not_called()
        self.assertEqual(Pedido.objects.get().costo_envio, Decimal('7000.00'))

    def test_otro_codigo_postal_no_reutiliza_la_cotizacion(self):
        self.cotizar()
        self.direccion = self.crear_direccion(self.cliente_a, '1878')
        _, cotizar = self.pagar('EP', servicios(cp='5100.00', ep='7100.00'))
        self.assertEqual(cotizar.call_args[0][:2], ('1878', 'domicilio'))
        self.assertEqual(Pedido.objects.get().costo_envio, Decimal('7100.00'))

    def test_otro_tipo_de_entrega_no_reutiliza_la_cotizacion(self):
        self.cotizar(tipo_correo='sucursal', codigo_postal='1900', direccion_correo_id='')
        _, cotizar = self.pagar('CP', servicios(cp='5200.00'))
        self.assertEqual(cotizar.call_args[0][:2], ('1900', 'domicilio'))
        self.assertEqual(Pedido.objects.get().costo_envio, Decimal('5200.00'))

    def test_otro_paquete_no_reutiliza_la_cotizacion(self):
        self.cotizar()
        ConfiguracionPaquete.objects.filter(tamano='mediano').update(peso_gramos=950)
        _, cotizar = self.pagar('CP', servicios(cp='5300.00'))
        cotizar.assert_called_once()
        self.assertEqual(Pedido.objects.get().costo_envio, Decimal('5300.00'))

    def test_el_precio_y_el_nombre_no_se_toman_del_navegador(self):
        self.cotizar()
        self.pagar(
            'EP', costo_envio='1', precio='1', importe='1', precio_correo='1', total='1',
            tarifa_correo_nombre='Gratis', correo_costo_final='1',
        )
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.costo_envio, Decimal('7000.00'))
        self.assertEqual(pedido.total, Decimal('8000.00'))
        self.assertEqual(pedido.tarifa_correo_nombre, 'Paq.ar Expreso')

    def test_un_codigo_inventado_no_crea_el_pedido(self):
        self.cotizar()
        respuesta, _ = self.pagar('ZZ')
        self.assertRedirects(respuesta, reverse('pedidos:checkout'), fetch_redirect_response=False)
        self.assertIn('servicio de Correo Argentino válido', self.mensajes(respuesta))
        self.assertFalse(Pedido.objects.exists())

    def test_un_servicio_que_ya_no_esta_disponible_da_un_error_controlado(self):
        self.cotizar(servicios(ep=None))
        respuesta, _ = self.pagar('EP')
        self.assertRedirects(respuesta, reverse('pedidos:checkout'), fetch_redirect_response=False)
        self.assertIn('Correo Argentino Expreso ya no está disponible', self.mensajes(respuesta))
        self.assertFalse(Pedido.objects.exists())
        self.assertEqual(self.stock(self.remera_m), 2)


class PedidoGuardaElServicioTests(CheckoutCorreoMixin, TestCase):
    def setUp(self):
        self.preparar()

    def test_pedido_pendiente_por_transferencia(self):
        self.cotizar()
        self.pagar('EP')
        pedido = Pedido.objects.get()
        self.assertEqual((pedido.estado, pedido.tarifa_correo_nombre), ('pendiente', 'Paq.ar Expreso'))
        self.assertEqual(self.client_a.session['correo_servicio_final'], 'Paq.ar Expreso')

    def test_pedido_pendiente_de_mercado_pago_y_su_confirmacion(self):
        self.cotizar()
        sdk = self.mock_mercado_pago()
        with mock.patch('pedidos.views.sdk', sdk):
            self.pagar('EP', metodo_pago='mercado_pago')
        preferencia = sdk.preference.return_value.create.call_args[0][0]
        self.assertIn({'title': 'Envio por correo', 'quantity': 1, 'currency_id': 'ARS', 'unit_price': 7000.0}, preferencia['items'])
        pedido = Pedido.objects.get()
        self.assertEqual((pedido.estado, pedido.tarifa_correo_nombre), ('pendiente', 'Paq.ar Expreso'))

        sdk = self.mock_mercado_pago(preferencia['external_reference'], monto=pedido.total)
        with mock.patch('pedidos.views.sdk', sdk):
            self.client_a.get(reverse('pedidos:pago_exitoso'), {'payment_id': '333'})
        pedido.refresh_from_db()
        self.assertEqual((pedido.estado, pedido.tarifa_correo_nombre), ('aceptado', 'Paq.ar Expreso'))
        self.assertEqual(Pedido.objects.count(), 1)

    def test_link_viejo_de_mercado_pago_crea_el_pedido_con_el_servicio_cotizado(self):
        carrito = self.llenar_carrito(self.cliente_a, [(self.remera_m, 1, None)])
        referencia = f'carrito_{carrito.id}_abc'
        session = self.client_a.session
        session.update({
            'mp_external_reference': referencia, 'metodo_entrega': 'correo', 'correo': 'correo_argentino',
            'tipo_correo': 'domicilio', 'direccion_correo_id': self.direccion.id,
            'correo_costo_final': '7000.00', 'correo_servicio_final': 'Paq.ar Expreso',
        })
        session.save()
        with mock.patch('pedidos.views.sdk', self.mock_mercado_pago(referencia, monto=Decimal('8000.00'))):
            self.client_a.get(reverse('pedidos:pago_exitoso'), {'payment_id': '444'})
        pedido = Pedido.objects.get()
        self.assertEqual((pedido.estado, pedido.costo_envio), ('aceptado', Decimal('7000.00')))
        self.assertEqual(pedido.tarifa_correo_nombre, 'Paq.ar Expreso')
        self.assertEqual(Pago.objects.filter(pedido=pedido).count(), 1)

    def test_confirmar_pedido_sigue_deshabilitado(self):
        """El flujo viejo confirmar_pedido redirige al checkout sin crear pedidos."""
        self.cotizar()
        respuesta = self.client_a.post(reverse('pedidos:confirmar_pedido'), {
            'metodo_entrega': 'correo', 'correo': 'correo_argentino', 'tipo_correo': 'domicilio',
            'direccion_correo_id': self.direccion.id, 'servicio_correo': 'EP',
        })
        self.assertRedirects(respuesta, reverse('pedidos:checkout'), fetch_redirect_response=False)
        self.assertFalse(Pedido.objects.exists())

    def test_otros_metodos_de_entrega_no_guardan_un_servicio_de_correo(self):
        self.cotizar()
        self.pagar('EP')
        self.assertEqual(self.client_a.session['correo_servicio_final'], 'Paq.ar Expreso')
        self.llenar_carrito(self.cliente_a, [(self.remera_l, 1, None)])
        self.client_a.post(reverse('pedidos:crear_pago'), {'metodo_entrega': 'local', 'metodo_pago': 'transferencia'})
        pedido = Pedido.objects.latest('id')
        self.assertEqual((pedido.metodo_entrega, pedido.costo_envio), ('local', Decimal('0.00')))
        self.assertIsNone(pedido.tarifa_correo_nombre)

    def test_link_viejo_con_retiro_en_local_no_guarda_un_servicio_de_correo(self):
        carrito = self.llenar_carrito(self.cliente_a, [(self.remera_m, 1, None)])
        referencia = f'carrito_{carrito.id}_abc'
        session = self.client_a.session
        session.update({
            'mp_external_reference': referencia, 'metodo_entrega': 'local', 'correo': 'correo_argentino',
            'correo_costo_final': '7000.00', 'correo_servicio_final': 'Paq.ar Expreso',
        })
        session.save()
        with mock.patch('pedidos.views.sdk', self.mock_mercado_pago(referencia, monto=Decimal('1000.00'))):
            self.client_a.get(reverse('pedidos:pago_exitoso'), {'payment_id': '555'})
        pedido = Pedido.objects.get()
        self.assertEqual((pedido.costo_envio, pedido.tarifa_correo_nombre), (Decimal('0.00'), None))


class EtiquetaPaqarTests(CheckoutCorreoMixin, TestCase):
    def setUp(self):
        self.preparar()

    def service_type(self, tarifa_correo_nombre):
        pedido = self.crear_pedido(self.cliente_a, [(self.remera_m, 1, None)])
        Pedido.objects.filter(pk=pedido.pk).update(
            metodo_entrega='correo', correo='correo_argentino', tipo_correo='domicilio',
            direccion=self.direccion, tarifa_correo_nombre=tarifa_correo_nombre,
        )
        envio = EnvioPedido.objects.create(pedido=Pedido.objects.get(pk=pedido.pk), proveedor='correo_argentino')
        configuracion = {'base_url': 'https://paqar.example.test', 'api_key': 'clave-de-prueba', 'agreement': '1'}
        with mock.patch('pedidos.servicios_envio.config_paqar', return_value=configuracion), \
                mock.patch('pedidos.servicios_envio.request_paqar', return_value={'trackingNumber': 'TN1'}) as request_paqar:
            tracking, _ = servicios_envio.crear_envio_paqar(envio)
        self.assertEqual(tracking, 'TN1')
        return request_paqar.call_args[0][4]['order']['serviceType']

    def test_expreso_genera_el_envio_con_ep(self):
        self.assertEqual(self.service_type('Paq.ar Expreso'), 'EP')
        self.assertEqual(self.service_type('Correo Argentino Expreso'), 'EP')

    def test_clasico_genera_el_envio_con_cp(self):
        self.assertEqual(self.service_type('Paq.ar Clasico'), 'CP')

    def test_pedidos_anteriores_sin_servicio_siguen_con_cp(self):
        self.assertEqual(self.service_type(None), 'CP')
        self.assertEqual(self.service_type(''), 'CP')
