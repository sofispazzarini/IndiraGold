import hashlib
import hmac
from decimal import Decimal
from unittest import mock

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from pedidos.mercado_pago import base_url, items_preferencia
from pedidos.models import Pago, Pedido
from pedidos.tests import DatosStockMixin


class PreferenciaValidacionTests(SimpleTestCase):
    def test_linea_cero_con_envio_se_agrupa_sin_cambiar_total(self):
        items = [{'unit_price': 0, 'quantity': 2}, {'unit_price': 8000, 'quantity': 1}]
        salida = items_preferencia(items, Decimal('8000.00'))
        self.assertEqual(len(salida), 1)
        self.assertEqual(Decimal(str(salida[0]['unit_price'])), Decimal('8000'))

    def test_redondeo_se_agrupa_y_precios_validos_se_conservan(self):
        items = [{'unit_price': 0.33, 'quantity': 3}]
        self.assertIs(items_preferencia(items, Decimal('0.99')), items)
        self.assertEqual(items_preferencia(items, Decimal('1.00'))[0]['unit_price'], 1)

    def test_total_no_cobrable_no_se_envia_a_mp(self):
        for total in ('0', '-1', 'NaN', 'Infinity'):
            with self.subTest(total=total), self.assertRaises(ValueError):
                items_preferencia([], total)

    @override_settings(DEBUG=False)
    def test_urls_produccion_requieren_https_y_origen_sin_ruta(self):
        for url in ('http://indiragold.com.ar', '', 'https://indiragold.com.ar/x',
                    'https://indiragold.com.ar?x=1', 'https://usuario:clave@indiragold.com.ar'):
            with self.subTest(url=url), override_settings(SITE_URL=url), self.assertRaises(ValueError):
                base_url()


@override_settings(MERCADO_PAGO_WEBHOOK_SECRET='secreto-de-pruebas')
class WebhookTests(DatosStockMixin, TestCase):
    def setUp(self):
        self.crear_datos()
        self.client = Client(enforce_csrf_checks=True)
        self.sdk = self.mock_mercado_pago()
        with mock.patch('pedidos.views.sdk', self.sdk):
            self.comprar(self.cliente_a, [(self.remera_m, 1, None)], metodo_pago='mercado_pago')
        self.pedido = Pedido.objects.get()
        self.referencia = self.pedido.mercado_pago_referencia
        self.detalle = {'id': 123, 'status': 'approved', 'external_reference': self.referencia,
                        'transaction_amount': float(self.pedido.total), 'currency_id': 'ARS', 'installments': 1}
        self.sdk.payment.return_value.get.return_value = {'status': 200, 'response': self.detalle}
        manifiesto = 'id:123;request-id:request-1;ts:1234567890;'
        firma = hmac.new(b'secreto-de-pruebas', manifiesto.encode(), hashlib.sha256).hexdigest()
        self.headers = {'HTTP_X_SIGNATURE': f'ts=1234567890,v1={firma}', 'HTTP_X_REQUEST_ID': 'request-1'}
        self.url = reverse('pedidos:mercado_pago_webhook') + '?data.id=123&type=payment'

    def notificar(self):
        with mock.patch('pedidos.views.sdk', self.sdk):
            return self.client.post(self.url, '{}', content_type='application/json', **self.headers)

    def test_preferencia_persiste_referencia_y_notificacion_https(self):
        preferencia = self.sdk.preference.return_value.create.call_args.args[0]
        self.assertEqual(preferencia['external_reference'], self.referencia)
        self.assertEqual(preferencia['notification_url'], 'https://www.indiragold.com.ar/pedidos/mercado-pago/webhook/')

    def test_sin_sesion_confirma_y_reintento_no_duplica_pago_stock_ni_email(self):
        with mock.patch('pedidos.views.enviar_emails_pago_mercado_pago') as email:
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self.notificar().status_code, 200)
                self.assertEqual(self.notificar().status_code, 200)
            email.assert_called_once()
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, 'aceptado')
        self.assertEqual(self.pedido.deuda, 0)
        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(self.stock(self.remera_m), 1)
        # Retorno posterior al webhook no debe volver a reservar ni pagar.
        client = self.cliente_logueado(self.cliente_a)
        with mock.patch('pedidos.views.sdk', self.sdk):
            response = client.get(reverse('pedidos:pago_exitoso'), {'payment_id': '123'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(self.stock(self.remera_m), 1)

    def test_firma_incorrecta_y_recurso_cambiado_no_consultan_la_api(self):
        for cambio in ({'HTTP_X_SIGNATURE': 'ts=1234567890,v1=incorrecta'}, {'HTTP_X_REQUEST_ID': 'otro'}):
            headers = dict(self.headers, **cambio)
            with mock.patch('pedidos.views.sdk', self.sdk):
                response = self.client.post(self.url, '{}', content_type='application/json', **headers)
            self.assertEqual(response.status_code, 401)
        self.sdk.payment.assert_not_called()
        self.assertFalse(Pago.objects.exists())

    def test_api_caida_pide_reintento(self):
        self.sdk.payment.return_value.get.side_effect = TimeoutError()
        self.assertEqual(self.notificar().status_code, 503)
        self.assertFalse(Pago.objects.exists())

    def test_monto_moneda_referencia_y_estado_se_validan(self):
        for campo, valor, status in (
            ('transaction_amount', float(self.pedido.total) - 0.01, 422),
            ('transaction_amount', float(self.pedido.total) + 1, 422),
            ('currency_id', 'USD', 422),
            ('external_reference', self.referencia[:-1] + ('a' if self.referencia[-1] != 'a' else 'b'), 422),
            ('status', 'pending', 200), ('status', 'refunded', 200),
        ):
            with self.subTest(campo=campo, valor=valor):
                original = self.detalle[campo]
                self.detalle[campo] = valor
                self.assertEqual(self.notificar().status_code, status)
                self.assertFalse(Pago.objects.exists())
                self.detalle[campo] = original
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, 'pendiente')

    def test_fallo_de_preferencia_no_deja_pedido_ni_reserva_adicional(self):
        self.sdk.preference.return_value.create.side_effect = TimeoutError()
        antes = Pedido.objects.count()
        with mock.patch('pedidos.views.sdk', self.sdk):
            response = self.comprar(self.cliente_b, [(self.remera_l, 1, None)], metodo_pago='mercado_pago')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Pedido.objects.count(), antes)
        self.assertEqual(self.stock(self.remera_l), 3)

    def test_retorno_repetido_no_borra_un_carrito_nuevo(self):
        self.assertEqual(self.notificar().status_code, 200)
        client = self.cliente_logueado(self.cliente_a)
        # Otro carrito con las mismas líneas, sin referencia pendiente de retorno.
        self.llenar_carrito(self.cliente_a, [(self.remera_m, 1, None)])
        with mock.patch('pedidos.views.sdk', self.sdk):
            client.get(reverse('pedidos:pago_exitoso'), {'payment_id': '123'})
        from carritos.models import CarritoItem
        self.assertTrue(CarritoItem.objects.filter(carrito__cliente=self.cliente_a).exists())
