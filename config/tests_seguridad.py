from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from pedidos.tests import DatosStockMixin


@override_settings(SECURE_SSL_REDIRECT=True, CSRF_COOKIE_SECURE=True, SESSION_COOKIE_SECURE=True)
class CsrfProduccionTests(DatosStockMixin, TestCase):
    def setUp(self):
        self.crear_datos()

    def navegador(self, host):
        return Client(enforce_csrf_checks=True, HTTP_HOST=host)

    def test_http_redirige_antes_de_servir_formularios_en_ambos_dominios(self):
        for host in ('indiragold.com.ar', 'www.indiragold.com.ar'):
            for ruta in ('/', '/users/login/', '/users/registro/', '/pedidos/checkout/'):
                with self.subTest(host=host, ruta=ruta):
                    response = self.navegador(host).get(ruta + '?next=1')
                    self.assertEqual(response.status_code, 301)
                    self.assertEqual(response['Location'], f'https://{host}{ruta}?next=1')

    def test_login_https_con_cookie_y_token_funciona_sin_trusted_origins(self):
        for host in ('indiragold.com.ar', 'www.indiragold.com.ar'):
            client = self.navegador(host)
            response = client.get('/users/login/', secure=True)
            self.assertTrue(response.cookies['csrftoken']['secure'])
            self.assertEqual(response.cookies['csrftoken']['samesite'], 'Lax')
            self.assertIn('no-store', response['Cache-Control'])
            token = client.cookies['csrftoken'].value
            with override_settings(CSRF_TRUSTED_ORIGINS=[]):
                response = client.post('/users/login/', {
                    'username': self.cliente_a.user.username, 'password': 'x', 'csrfmiddlewaretoken': token,
                }, secure=True, HTTP_ORIGIN=f'https://{host}')
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.cookies['sessionid']['secure'])
            self.assertNotEqual(client.cookies['csrftoken'].value, token)

    def test_falta_cookie_token_antiguo_y_origen_ajeno_se_rechazan(self):
        host = 'www.indiragold.com.ar'
        rutas = ('/users/login/', '/users/registro/', '/users/confirmar-direccion/',
                 '/users/verificar-codigo-email/', '/carritos/agregar/', '/pedidos/crear-pago/')
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                client = self.navegador(host)
                response = client.post(ruta, secure=True, HTTP_ORIGIN=f'https://{host}')
                self.assertEqual(response.status_code, 403)
        client = self.navegador(host)
        client.get('/users/login/', secure=True)
        token = client.cookies['csrftoken'].value
        self.assertEqual(client.post('/users/login/', {'csrfmiddlewaretoken': 'a' * 32},
                                    secure=True, HTTP_ORIGIN=f'https://{host}').status_code, 403)
        self.assertEqual(client.post('/users/login/', {'csrfmiddlewaretoken': token},
                                    secure=True, HTTP_ORIGIN='https://evil.example').status_code, 403)

    def test_carrito_ajax_y_checkout_con_csrf_real(self):
        host = 'www.indiragold.com.ar'
        client = self.navegador(host)
        client.get('/', secure=True)
        token = client.cookies['csrftoken'].value
        response = client.post('/carritos/agregar/', {'variante_id': self.remera_m.pk, 'cantidad': 1},
                               secure=True, HTTP_ORIGIN=f'https://{host}', HTTP_X_CSRFTOKEN=token,
                               HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(client.session.get('carrito'))
        client.post('/users/login/', {'username': self.cliente_a.user.username, 'password': 'x',
                                     'csrfmiddlewaretoken': token}, secure=True, HTTP_ORIGIN=f'https://{host}')
        response = client.get('/pedidos/checkout/', secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'csrfmiddlewaretoken')

    def test_registro_verificacion_tiene_csrf_y_conserva_sesion(self):
        host = 'www.indiragold.com.ar'
        client = self.navegador(host)
        response = client.get('/users/registro/', secure=True)
        self.assertContains(response, 'csrfmiddlewaretoken')
        session = client.session
        session['codigo_verificacion'] = '123456'
        session.save()
        url = reverse('users:verificar_codigo_email')
        response = client.post(url, {'codigo': '123456'}, secure=True, HTTP_ORIGIN=f'https://{host}')
        self.assertEqual(response.status_code, 403)
        response = client.post(url, {'codigo': '123456'}, secure=True, HTTP_ORIGIN=f'https://{host}',
                               HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        self.assertTrue(response.json()['success'])
        self.assertTrue(client.session['email_verificado'])

    @override_settings(SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'))
    def test_proxy_configurado_no_crea_bucle_de_redireccion(self):
        response = self.navegador('www.indiragold.com.ar').get('/users/login/', HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(response.status_code, 200)
