"""Configuración editable de los paquetes de envío (chico, mediano, grande) y su uso al cotizar
Correo Argentino. La API de Correo Argentino se simula: estas pruebas no hacen pedidos reales."""
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import DataError, IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.forms.models import model_to_dict
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from carritos.models import Carrito, CarritoItem
from pedidos import servicios_envio
from pedidos.models import ConfiguracionPaquete
from pedidos.servicios_envio import ConfigProveedor, ErrorEnvio, calcular_paquete_envio
from productos.forms import ProductoForm
from productos.models import Categoria, Producto, Proveedor, Talle, Variante
from users.models import Cliente

CAMPOS_MEDIDAS = ('peso_gramos', 'alto_cm', 'ancho_cm', 'largo_cm')

# Medidas distintas para cada tamaño, así cada prueba ve claramente cuál se usó
MEDIDAS_PRUEBA = {
    'chico': (111, 2, 11, 12),
    'mediano': (222, 4, 21, 22),
    'grande': (333, 6, 31, 32),
}


def cargar_medidas(medidas=MEDIDAS_PRUEBA):
    for tamano, (peso, alto, ancho, largo) in medidas.items():
        ConfiguracionPaquete.objects.filter(tamano=tamano).update(
            peso_gramos=peso, alto_cm=alto, ancho_cm=ancho, largo_cm=largo
        )


def dimensiones(tamano):
    peso, alto, ancho, largo = MEDIDAS_PRUEBA[tamano]
    return {'weight': peso, 'height': alto, 'width': ancho, 'length': largo}


class ConfiguracionPaqueteAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username='99999999', password='x', email='admin@example.test')
        self.client.force_login(self.admin)

    def test_la_migracion_carga_los_tres_tamanos_con_los_valores_que_se_usaban(self):
        cargados = {
            c.tamano: (c.peso_gramos, c.alto_cm, c.ancho_cm, c.largo_cm)
            for c in ConfiguracionPaquete.objects.all()
        }
        self.assertEqual(cargados, {
            'chico': (200, 3, 20, 25),
            'mediano': (400, 5, 25, 35),
            'grande': (800, 10, 35, 45),
        })

    def test_el_admin_lista_y_edita_un_tamano(self):
        self.assertEqual(self.client.get(reverse('admin:pedidos_configuracionpaquete_changelist')).status_code, 200)
        mediano = ConfiguracionPaquete.objects.get(tamano='mediano')
        url = reverse('admin:pedidos_configuracionpaquete_change', args=[mediano.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        respuesta = self.client.post(url, {'peso_gramos': 650, 'alto_cm': 6, 'ancho_cm': 26, 'largo_cm': 36})
        self.assertEqual(respuesta.status_code, 302)
        mediano.refresh_from_db()
        self.assertEqual((mediano.peso_gramos, mediano.alto_cm, mediano.ancho_cm, mediano.largo_cm), (650, 6, 26, 36))
        self.assertEqual(mediano.tamano, 'mediano')

    def test_el_admin_crea_un_tamano_que_falta(self):
        ConfiguracionPaquete.objects.filter(tamano='grande').delete()
        respuesta = self.client.post(reverse('admin:pedidos_configuracionpaquete_add'), {
            'tamano': 'grande', 'peso_gramos': 900, 'alto_cm': 12, 'ancho_cm': 36, 'largo_cm': 46,
        })
        self.assertEqual(respuesta.status_code, 302)
        grande = ConfiguracionPaquete.objects.get(tamano='grande')
        self.assertEqual((grande.peso_gramos, grande.alto_cm, grande.ancho_cm, grande.largo_cm), (900, 12, 36, 46))

    def test_con_los_tres_cargados_no_se_agrega_ni_se_borra(self):
        self.assertEqual(self.client.get(reverse('admin:pedidos_configuracionpaquete_add')).status_code, 403)
        chico = ConfiguracionPaquete.objects.get(tamano='chico')
        self.assertEqual(self.client.get(reverse('admin:pedidos_configuracionpaquete_delete', args=[chico.pk])).status_code, 403)

    def test_no_se_permiten_peso_ni_medidas_en_cero_o_negativos(self):
        for campo in CAMPOS_MEDIDAS:
            for valor in (0, -5):
                configuracion = ConfiguracionPaquete.objects.get(tamano='chico')
                setattr(configuracion, campo, valor)
                with self.assertRaises(ValidationError) as error:
                    configuracion.full_clean()
                self.assertIn(campo, error.exception.message_dict)

        # Desde el admin: el formulario rechaza el 0 y no guarda nada
        chico = ConfiguracionPaquete.objects.get(tamano='chico')
        respuesta = self.client.post(
            reverse('admin:pedidos_configuracionpaquete_change', args=[chico.pk]),
            {'peso_gramos': 0, 'alto_cm': 3, 'ancho_cm': 20, 'largo_cm': 25},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'El peso tiene que ser mayor que 0.')
        chico.refresh_from_db()
        self.assertEqual(chico.peso_gramos, 200)

        # En la base, los campos son enteros sin signo: un negativo no se guarda aunque se saltee la
        # validación (PostgreSQL/SQLite: CHECK >= 0; MySQL en modo estricto: UNSIGNED fuera de rango)
        for campo in CAMPOS_MEDIDAS:
            with self.assertRaises((IntegrityError, DataError)), transaction.atomic():
                ConfiguracionPaquete.objects.filter(tamano='chico').update(**{campo: -1})

    def test_no_se_permiten_dos_configuraciones_del_mismo_tamano(self):
        duplicada = ConfiguracionPaquete(tamano='chico', peso_gramos=100, alto_cm=1, ancho_cm=1, largo_cm=1)
        with self.assertRaises(ValidationError) as error:
            duplicada.full_clean()
        self.assertEqual(error.exception.message_dict['tamano'], ['Ya existe una configuración para ese tamaño de paquete.'])
        with self.assertRaises(IntegrityError), transaction.atomic():
            ConfiguracionPaquete.objects.create(tamano='chico', peso_gramos=100, alto_cm=1, ancho_cm=1, largo_cm=1)

        # Desde el admin (con un tamaño faltante, para que se pueda agregar): no acepta repetir otro
        ConfiguracionPaquete.objects.filter(tamano='grande').delete()
        respuesta = self.client.post(reverse('admin:pedidos_configuracionpaquete_add'), {
            'tamano': 'chico', 'peso_gramos': 100, 'alto_cm': 1, 'ancho_cm': 1, 'largo_cm': 1,
        })
        self.assertContains(respuesta, 'Ya existe una configuración para ese tamaño de paquete.')
        self.assertEqual(ConfiguracionPaquete.objects.filter(tamano='chico').count(), 1)


class CatalogoMixin:
    def crear_catalogo(self):
        self.categoria = Categoria.objects.create(nombre='Cat')
        self.proveedor = Proveedor.objects.create(nombre='Prov', telefono='123')
        self.talle = Talle.objects.create(nombre='U')
        self.variantes = {
            tamano: self.crear_variante(f'P-{tamano}', tamano)
            for tamano in ('chico', 'mediano', 'grande')
        }

    def crear_variante(self, codigo, tamano):
        producto = Producto.objects.create(
            codigo=codigo, nombre=f'Producto {tamano}', tipo='Tipo', tela='Tela', precio=Decimal('1000.00'),
            stock=5, categoria=self.categoria, proveedor=self.proveedor, activo=True, tamano_paquete=tamano,
        )
        return Variante.objects.create(
            producto=producto, talle=self.talle, stock=5, precio=producto.precio, activa=True, qr_code=f'QR-{codigo}',
        )

    def item(self, tamano, cantidad=1):
        return SimpleNamespace(variante=self.variantes[tamano], cantidad=cantidad)


class CalculoPaqueteTests(CatalogoMixin, TestCase):
    def setUp(self):
        self.crear_catalogo()
        cargar_medidas()

    def test_producto_chico_usa_el_paquete_chico(self):
        self.assertEqual(calcular_paquete_envio([self.item('chico')]), dimensiones('chico'))

    def test_producto_mediano_usa_el_paquete_mediano(self):
        self.assertEqual(calcular_paquete_envio([self.item('mediano')]), dimensiones('mediano'))

    def test_producto_grande_usa_el_paquete_grande(self):
        self.assertEqual(calcular_paquete_envio([self.item('grande')]), dimensiones('grande'))

    def test_un_cambio_en_el_admin_se_usa_en_el_proximo_calculo(self):
        ConfiguracionPaquete.objects.filter(tamano='grande').update(peso_gramos=1500)
        self.assertEqual(calcular_paquete_envio([self.item('grande')])['weight'], 1500)

    def test_la_combinacion_de_productos_sigue_igual(self):
        # Pesos y altos se suman por unidad; ancho y largo, el mayor (con el chico como mínimo)
        paquete = calcular_paquete_envio([self.item('chico', 2), self.item('grande')])
        self.assertEqual(paquete, {'weight': 111 * 2 + 333, 'height': 2 * 2 + 6, 'width': 31, 'length': 32})

    def test_sin_productos_se_usa_el_paquete_mediano(self):
        self.assertEqual(calcular_paquete_envio([]), dimensiones('mediano'))

    def test_un_tamano_desconocido_se_cotiza_como_mediano(self):
        Producto.objects.filter(pk=self.variantes['chico'].producto_id).update(tamano_paquete='otro')
        self.variantes['chico'].producto.refresh_from_db()
        self.assertEqual(calcular_paquete_envio([self.item('chico')])['weight'], 222)

    def test_un_valor_en_cero_cargado_por_fuera_del_admin_cuenta_como_faltante(self):
        for campo in CAMPOS_MEDIDAS:
            cargar_medidas()
            ConfiguracionPaquete.objects.filter(tamano='grande').update(**{campo: 0})
            with self.assertRaisesMessage(ErrorEnvio, 'falta configurar el paquete "Grande"'):
                calcular_paquete_envio([self.item('grande')])

    def test_si_falta_un_tamano_se_avisa_sin_inventar_valores(self):
        ConfiguracionPaquete.objects.filter(tamano='grande').delete()
        with self.assertRaisesMessage(ErrorEnvio, 'falta configurar el paquete "Grande"'):
            calcular_paquete_envio([self.item('grande')])
        # Los otros tamaños siguen funcionando
        self.assertEqual(calcular_paquete_envio([self.item('mediano')]), dimensiones('mediano'))

    def test_el_formulario_de_producto_solo_ofrece_los_tres_tamanos_y_conserva_el_elegido(self):
        producto = self.variantes['grande'].producto
        form = ProductoForm(instance=producto)
        self.assertEqual([valor for valor, _ in form.fields['tamano_paquete'].choices], ['chico', 'mediano', 'grande'])

        datos = model_to_dict(producto, fields=ProductoForm.Meta.fields)
        datos = {clave: valor for clave, valor in datos.items() if valor is not None and clave != 'imagen_tecnica'}
        form = ProductoForm(datos, instance=producto)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        producto.refresh_from_db()
        self.assertEqual(producto.tamano_paquete, 'grande')

        datos['tamano_paquete'] = 'chico'
        form = ProductoForm(datos, instance=producto)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        producto.refresh_from_db()
        self.assertEqual(producto.tamano_paquete, 'chico')


CONFIG_CORREO_PRUEBA = ConfigProveedor(
    nombre='correo_argentino', base_url='https://correo.example.test', token='token-de-prueba', usuario='',
    password='', auth_endpoint='', cotizar_endpoint='/rates', customer_id='0001', postal_code_origin='1000',
    crear_endpoint='/shipping', etiqueta_endpoint='/label',
)


class CotizacionTests(CatalogoMixin, TestCase):
    """La API de Correo Argentino se reemplaza por respuestas simuladas."""

    def setUp(self):
        self.crear_catalogo()
        cargar_medidas()

    def cotizar(self, funcion, respuesta, items):
        with mock.patch('pedidos.servicios_envio.config_proveedor', return_value=CONFIG_CORREO_PRUEBA), \
                mock.patch('pedidos.servicios_envio.obtener_token', return_value='token-de-prueba'), \
                mock.patch('pedidos.servicios_envio.request_json', return_value=respuesta) as request_json:
            resultado = funcion('1900', 'domicilio', items)
        return resultado, request_json.call_args[0][3]

    def test_la_cotizacion_envia_las_medidas_configuradas(self):
        (importe, _), payload = self.cotizar(
            servicios_envio.cotizar_correo_argentino, {'rates': [{'price': 4321.5}]}, [self.item('grande')]
        )
        self.assertEqual(importe, Decimal('4321.50'))
        self.assertEqual(payload['dimensions'], dimensiones('grande'))
        self.assertEqual(payload['postalCodeDestination'], '1900')

    def test_todas_las_tarifas_envian_las_medidas_configuradas(self):
        respuesta = {'rates': [{'price': 5000, 'serviceName': 'Clasico'}, {'price': 7000, 'serviceName': 'Expreso'}]}
        tarifas, payload = self.cotizar(
            servicios_envio.cotizar_correo_argentino_todas_tarifas, respuesta, [self.item('chico', 3)]
        )
        self.assertEqual([t['precio'] for t in tarifas], [Decimal('5000.00'), Decimal('7000.00')])
        self.assertEqual(payload['dimensions'], {'weight': 333, 'height': 6, 'width': 11, 'length': 12})

    def test_si_falta_un_tamano_la_cotizacion_no_llama_a_la_api(self):
        ConfiguracionPaquete.objects.filter(tamano='chico').delete()
        with mock.patch('pedidos.servicios_envio.config_proveedor', return_value=CONFIG_CORREO_PRUEBA), \
                mock.patch('pedidos.servicios_envio.obtener_token', return_value='token-de-prueba'), \
                mock.patch('pedidos.servicios_envio.request_json') as request_json:
            with self.assertRaises(ErrorEnvio):
                servicios_envio.cotizar_correo_argentino('1900', 'domicilio', [self.item('mediano')])
        request_json.assert_not_called()


class CotizacionCheckoutTests(CatalogoMixin, TestCase):
    def setUp(self):
        self.crear_catalogo()
        cargar_medidas()
        user = User.objects.create_user(username='30000001', password='x', email='c@example.test')
        self.cliente = Cliente.objects.create(user=user, dni='30000001', telefono='1155550000')
        carrito = Carrito.objects.create(cliente=self.cliente, activo=True, expires_at=timezone.now() + timedelta(hours=1))
        CarritoItem.objects.create(
            carrito=carrito, variante=self.variantes['mediano'], cantidad=2,
            precio_unitario=Decimal('1000.00'), precio_total=Decimal('2000.00'),
        )
        self.client.force_login(user)
        self.url = reverse('pedidos:cotizar_correo_argentino')

    def test_la_cotizacion_del_checkout_usa_la_configuracion(self):
        with mock.patch('pedidos.views.cotizar_correo_argentino', return_value=(Decimal('3500.00'), {})):
            respuesta = self.client.post(self.url, {'tipo_correo': 'sucursal', 'codigo_postal': 'B1900AVW'})
        datos = respuesta.json()
        self.assertTrue(datos['success'])
        self.assertEqual(datos['paquete'], {'weight': 444, 'height': 8, 'width': 21, 'length': 22})

    def test_si_falta_la_configuracion_el_checkout_responde_un_error_claro(self):
        ConfiguracionPaquete.objects.filter(tamano='mediano').delete()
        respuesta = self.client.post(self.url, {'tipo_correo': 'sucursal', 'codigo_postal': '1900'})
        self.assertEqual(respuesta.status_code, 400)
        datos = respuesta.json()
        self.assertFalse(datos['success'])
        self.assertIn('falta configurar el paquete "Mediano"', datos['error'])


class MigracionPaquetesTests(TransactionTestCase):
    """La migración nueva no toca los productos: cada uno conserva el tamaño que ya tenía."""

    anterior = [('pedidos', '0040_merge_20261011_1001')]
    nueva = [('pedidos', '0041_configuracion_paquete')]

    def test_los_productos_existentes_conservan_su_tamano(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.anterior)
        apps_anteriores = executor.loader.project_state(self.anterior).apps
        ProductoAnterior = apps_anteriores.get_model('productos', 'Producto')
        categoria = apps_anteriores.get_model('productos', 'Categoria').objects.create(nombre='Cat')
        proveedor = apps_anteriores.get_model('productos', 'Proveedor').objects.create(nombre='Prov', telefono='1')
        tamanos = {'P-1': 'grande', 'P-2': 'chico', 'P-3': 'mediano'}
        for codigo, tamano in tamanos.items():
            ProductoAnterior.objects.create(
                codigo=codigo, nombre=codigo, tipo='T', tela='T', precio=Decimal('10.00'), stock=1,
                categoria=categoria, proveedor=proveedor, tamano_paquete=tamano,
            )

        executor = MigrationExecutor(connection)
        executor.migrate(self.nueva)

        self.assertEqual(dict(Producto.objects.values_list('codigo', 'tamano_paquete')), tamanos)
        self.assertEqual(set(ConfiguracionPaquete.objects.values_list('tamano', flat=True)), {'chico', 'mediano', 'grande'})
