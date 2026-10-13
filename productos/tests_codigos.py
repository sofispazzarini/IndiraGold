"""Códigos automáticos de producto (ART-0001...): secuencia, unicidad, concurrencia, edición, borrado,
y el buscador de las ventas en el local. También verifica que variantes, colores, stock y QR sigan igual."""
import importlib
import json
import time
from decimal import Decimal
from unittest import mock, skipUnless

from django.apps import apps
from django.contrib.auth.models import User
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from pedidos.models import VentaLocal
from pedidos.tests import en_paralelo
from productos import codigos
from productos.models import (
    Categoria, Producto, Proveedor, SecuenciaCodigoProducto, Subcategoria, Talle, Variante, VarianteColor,
)
from users.models import Cliente


def ultimo_numero():
    return SecuenciaCodigoProducto.objects.get(nombre='producto').ultimo_numero


class CodigosMixin:
    def preparar(self):
        self.admin = User.objects.create_superuser(username='99999999', password='x', email='admin@example.test')
        self.client.force_login(self.admin)
        self.categoria = Categoria.objects.create(nombre='Ropa')
        self.subcategoria = Subcategoria.objects.create(nombre='Remeras', categoria=self.categoria)
        self.proveedor = Proveedor.objects.create(nombre='Prov', telefono='123')

    def producto(self, nombre='Remera', codigo=''):
        """Producto creado por el ORM; sin código, recibe el automático."""
        return Producto.objects.create(
            codigo=codigo, nombre=nombre, tipo='T', tela='T', precio=Decimal('1000.00'), stock=0,
            categoria=self.categoria, subcategoria=self.subcategoria, proveedor=self.proveedor,
        )

    def alta_por_formulario(self, nombre='Remera Lisa', **extra):
        """Alta como en "Agregar producto": un talle M con dos colores con stock."""
        variantes = [{
            'talle': 'M', 'stock': 5, 'precio': 0, 'medidas': [],
            'colores': [
                {'colorNombre': 'Rojo', 'colorHex': '#ff0000', 'colorNinguno': False, 'stock': 3},
                {'colorNombre': 'Azul', 'colorHex': '#0000ff', 'colorNinguno': False, 'stock': 2},
            ],
        }]
        datos = {
            'nombre': nombre, 'tipo': 'Remera', 'tela': 'Algodón', 'temporada': '', 'descripcion': '',
            'avios': '', 'etiquetas': '', 'precio': '1000', 'stock': '0', 'proveedor': self.proveedor.id,
            'tamano_paquete': 'chico', 'activo': 'on', 'variantes_json': json.dumps(variantes), **extra,
        }
        return self.client.post(reverse('productos:agregar_producto', args=[self.subcategoria.id]), datos)


class CodigoAutomaticoTests(CodigosMixin, TestCase):
    def setUp(self):
        self.preparar()

    def test_el_alta_por_formulario_genera_el_codigo_y_mantiene_variantes_colores_stock_y_qr(self):
        respuesta = self.alta_por_formulario(codigo='ESCRITO-A-MANO')
        self.assertEqual(respuesta.status_code, 302)
        producto = Producto.objects.get()
        self.assertEqual(producto.codigo, 'ART-0001')  # un código enviado por el navegador se ignora
        variante = producto.variantes.get()
        self.assertEqual(variante.qr_code, f'VAR-{variante.pk:04d}')
        colores = {vc.color.nombre: vc for vc in VarianteColor.objects.filter(variante=variante).select_related('color')}
        self.assertEqual({nombre: vc.stock for nombre, vc in colores.items()}, {'Rojo': 3, 'Azul': 2})
        self.assertTrue(all(len(vc.qr_code) == 36 for vc in colores.values()))  # QR por color: uuid, como antes
        variante.refresh_from_db()
        producto.refresh_from_db()
        self.assertEqual((variante.stock, producto.stock), (5, 5))

    def test_codigos_secuenciales_y_distintos(self):
        codigos_generados = [self.producto(f'P{i}').codigo for i in range(3)]
        self.assertEqual(codigos_generados, ['ART-0001', 'ART-0002', 'ART-0003'])
        self.assertEqual(ultimo_numero(), 3)

    def test_sigue_desde_el_mayor_codigo_art_existente_sin_tocar_los_demas(self):
        existentes = {self.producto('A', 'DEMO-001').pk: 'DEMO-001', self.producto('B', 'ART-0007').pk: 'ART-0007',
                      self.producto('C', 'art-0010').pk: 'art-0010', self.producto('D', 'ART-12X').pk: 'ART-12X'}
        self.assertEqual(self.producto('Nuevo').codigo, 'ART-0011')
        self.assertEqual(dict(Producto.objects.filter(pk__in=existentes).values_list('pk', 'codigo')), existentes)

    def test_un_codigo_cargado_a_mano_con_el_proximo_numero_no_se_duplica(self):
        SecuenciaCodigoProducto.objects.filter(nombre='producto').update(ultimo_numero=4)
        self.producto('Manual', 'ART-0005')
        self.assertEqual(self.producto('Nuevo').codigo, 'ART-0006')

    def test_borrar_un_producto_no_libera_su_codigo(self):
        self.producto('Uno')
        segundo = self.producto('Dos')
        self.client.post(reverse('productos:eliminar_producto', args=[segundo.pk]))
        self.assertFalse(Producto.objects.filter(pk=segundo.pk).exists())
        self.assertEqual(self.producto('Tres').codigo, 'ART-0003')

    def test_abrir_cancelar_o_fallar_no_consume_numeros(self):
        self.client.get(reverse('productos:agregar_producto', args=[self.subcategoria.id]))
        self.alta_por_formulario(nombre='')  # formulario inválido: no se guarda
        self.assertFalse(Producto.objects.exists())
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.producto('Se deshace')
                raise RuntimeError('falla después de asignar el código')
        self.assertEqual(ultimo_numero(), 0)
        self.assertEqual(self.producto('Primero').codigo, 'ART-0001')

    def test_editar_no_cambia_el_codigo_ni_regenera_qr(self):
        self.alta_por_formulario()
        producto = Producto.objects.get()
        variante = producto.variantes.get()
        qrs_antes = (variante.qr_code, sorted(VarianteColor.objects.filter(variante=variante).values_list('qr_code', flat=True)))
        datos = {
            'codigo': 'OTRO-CODIGO', 'nombre': 'Remera Nueva', 'tipo': 'Remera', 'tela': 'Lino', 'temporada': 'Verano',
            'descripcion': 'x', 'avios': '', 'etiquetas': '', 'precio': '1500', 'stock': '0',
            'proveedor': self.proveedor.id, 'tamano_paquete': 'mediano', 'activo': 'on',
        }
        respuesta = self.client.post(reverse('productos:editar_producto', args=[producto.pk]), datos)
        self.assertEqual(respuesta.status_code, 302)
        producto.refresh_from_db()
        variante.refresh_from_db()
        self.assertEqual((producto.codigo, producto.nombre, producto.precio), ('ART-0001', 'Remera Nueva', Decimal('1500.00')))
        self.assertEqual(
            (variante.qr_code, sorted(VarianteColor.objects.filter(variante=variante).values_list('qr_code', flat=True))),
            qrs_antes,
        )

    def test_los_formularios_muestran_el_codigo_automatico(self):
        alta = self.client.get(reverse('productos:agregar_producto', args=[self.subcategoria.id]))
        self.assertContains(alta, 'El código se genera automáticamente al guardar')
        self.assertNotContains(alta, 'name="codigo"')
        producto = self.producto('Existente', 'DEMO-009')
        edicion = self.client.get(reverse('productos:editar_producto', args=[producto.pk]))
        self.assertContains(edicion, 'value="DEMO-009"')
        self.assertContains(edicion, 'disabled')
        self.assertContains(edicion, 'Se asigna al crear el producto y no cambia.')

    def test_la_migracion_arranca_desde_el_mayor_art_y_no_vuelve_atras(self):
        migracion = importlib.import_module('productos.migrations.0037_secuencia_codigo_producto')
        self.producto('A', 'ART-0042')
        self.producto('B', 'DEMO-100')
        SecuenciaCodigoProducto.objects.all().delete()
        migracion.iniciar_secuencia(apps, None)
        self.assertEqual(ultimo_numero(), 42)
        SecuenciaCodigoProducto.objects.filter(nombre='producto').update(ultimo_numero=50)
        migracion.iniciar_secuencia(apps, None)  # volver a correrla no lo baja
        self.assertEqual(ultimo_numero(), 50)

    def test_sin_contador_se_crea_desde_el_mayor_existente(self):
        SecuenciaCodigoProducto.objects.all().delete()
        self.producto('A', 'ART-0003')
        self.assertEqual(self.producto('B').codigo, 'ART-0004')


class BuscadorVentasLocalTests(CodigosMixin, TestCase):
    def setUp(self):
        self.preparar()
        self.lisa = self.con_stock(self.producto('Remera Lisa'))         # ART-0001
        self.rayada = self.con_stock(self.producto('Remera Rayada'))     # ART-0002
        self.vieja = self.con_stock(self.producto('Pantalón', 'DEMO-777'))
        for numero in range(3, 13):
            self.con_stock(self.producto(f'Otro {numero}'))              # ART-0003 ... ART-0012

    def con_stock(self, producto):
        talle, _ = Talle.objects.get_or_create(nombre='U')
        Variante.objects.create(producto=producto, talle=talle, stock=4, precio=producto.precio)
        return producto

    def buscar(self, q):
        return self.client.get(reverse('productos:buscar_productos'), {'q': q}).json()

    def test_codigo_completo_trae_solo_ese_producto(self):
        for q in ('ART-0002', 'art-0002', ' ART-0002 '):
            with self.subTest(q=q):
                self.assertEqual([p['id'] for p in self.buscar(q)], [self.rayada.id])
        self.assertEqual([p['codigo'] for p in self.buscar('ART-0001')], ['ART-0001'])  # no trae ART-0010/11/12
        self.assertEqual([p['id'] for p in self.buscar('DEMO-777')], [self.vieja.id])

    def test_nombre_y_fragmentos_siguen_funcionando(self):
        self.assertEqual({p['id'] for p in self.buscar('Remera')}, {self.lisa.id, self.rayada.id})
        self.assertEqual([p['id'] for p in self.buscar('rayad')], [self.rayada.id])

    def test_el_qr_de_la_variante_sigue_funcionando(self):
        variante = self.rayada.variantes.get()
        resultado = self.buscar(variante.qr_code)
        self.assertEqual((resultado[0]['id'], resultado[0]['auto_select'], resultado[0]['scanned_variante_id']),
                         (self.rayada.id, True, variante.id))

    def test_el_producto_con_codigo_nuevo_se_vende_en_el_local(self):
        user = User.objects.create_user(username='30000001', password='x', email='c@example.test')
        cliente = Cliente.objects.create(user=user, dni='30000001', telefono='1155550000')
        variante = self.rayada.variantes.get()
        datos = {'cliente_id': user.id, 'metodo_pago': 'efectivo', 'metodo_entrega': 'local',
                 'productos': [{'variante_id': variante.id, 'cantidad': 1, 'color': ''}]}
        respuesta = self.client.post(reverse('pedidos:registrar_venta_local'), json.dumps(datos), content_type='application/json')
        self.assertTrue(respuesta.json()['success'], respuesta.json())
        variante.refresh_from_db()
        self.assertEqual(variante.stock, 3)
        self.assertEqual(VentaLocal.objects.get(cliente=cliente).items.get().producto, self.rayada)


@skipUnless(connection.vendor == 'postgresql', 'La concurrencia real se prueba con PostgreSQL (SQLite no bloquea filas).')
class CodigosConcurrenciaTests(CodigosMixin, TransactionTestCase):
    def setUp(self):
        self.preparar()

    def test_altas_simultaneas_no_repiten_codigo(self):
        original = codigos.codigo_en_uso

        def lento(codigo):
            time.sleep(0.4)  # con el contador bloqueado: las altas se superponen de verdad
            return original(codigo)

        with mock.patch('productos.codigos.codigo_en_uso', side_effect=lento):
            resultados, errores = en_paralelo(*[lambda i=i: self.producto(f'Simultáneo {i}').codigo for i in range(3)])
        self.assertEqual(errores, [None, None, None])
        self.assertEqual(sorted(resultados), ['ART-0001', 'ART-0002', 'ART-0003'])
        self.assertEqual(ultimo_numero(), 3)
