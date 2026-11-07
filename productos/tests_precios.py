"""Aumentos y descuentos de precio: un aumento sube el precio sin ser oferta; un descuento es oferta.
El precio que se muestra es el que se cobra (carrito, checkout y ventas presenciales)."""
import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from carritos.utils import precio_unitario_vigente
from pedidos.models import VentaLocalItem
from pedidos.tests import DatosStockMixin
from pedidos.views import calcular_descuento_cupon
from productos.models import Oferta, Producto
from productos.views import _sumar_meses


class PreciosAumentosDescuentosTests(DatosStockMixin, TestCase):
    def setUp(self):
        self.crear_datos()
        self.remera.precio = Decimal('20000.00')
        self.remera.save()

    def operacion(self, tipo, porcentaje, productos=None, **kwargs):
        oferta = Oferta.objects.create(nombre=f'{tipo} {porcentaje}', tipo=tipo, descuento=porcentaje, **kwargs)
        if productos:
            oferta.productos.set(productos)
        return oferta

    def recargar(self, producto):
        # Instancia nueva: los precios se calculan con las operaciones activas en ese momento
        return Producto.objects.get(pk=producto.pk)

    def test_sin_operaciones_mantiene_el_precio(self):
        remera = self.recargar(self.remera)
        self.assertEqual(remera.precio_lista, Decimal('20000.00'))
        self.assertEqual(remera.precio_final, Decimal('20000.00'))
        self.assertIsNone(remera.obtener_oferta_activa())

    def test_aumento_sube_el_precio_y_no_es_oferta(self):
        self.operacion(Oferta.TIPO_AUMENTO, 15, [self.remera])
        remera = self.recargar(self.remera)
        self.assertEqual(remera.precio_lista, Decimal('23000.00'))
        self.assertEqual(remera.precio_final, Decimal('23000.00'))
        self.assertIsNone(remera.obtener_oferta_activa())
        self.assertEqual(precio_unitario_vigente(self.remera_m), Decimal('23000.00'))

    def test_descuento_es_oferta(self):
        self.operacion(Oferta.TIPO_DESCUENTO, 15, [self.remera])
        remera = self.recargar(self.remera)
        self.assertEqual(remera.precio_lista, Decimal('20000.00'))
        self.assertEqual(remera.precio_final, Decimal('17000.00'))
        self.assertIsNotNone(remera.obtener_oferta_activa())
        self.assertEqual(precio_unitario_vigente(self.remera_m), Decimal('17000.00'))

    def test_aumento_y_descuento_juntos_descuento_sobre_el_precio_aumentado(self):
        self.operacion(Oferta.TIPO_AUMENTO, 15, [self.remera])
        self.operacion(Oferta.TIPO_DESCUENTO, 10, aplicar_a_todos=True)
        remera = self.recargar(self.remera)
        self.assertEqual(remera.precio_lista, Decimal('23000.00'))
        self.assertEqual(remera.precio_final, Decimal('20700.00'))

    def test_dos_aumentos_no_se_suman(self):
        self.operacion(Oferta.TIPO_AUMENTO, 10, [self.remera])
        self.operacion(Oferta.TIPO_AUMENTO, 20, [self.remera])
        # Gana el más nuevo del mismo nivel (producto), no 10 % + 20 %
        self.assertEqual(self.recargar(self.remera).precio_final, Decimal('24000.00'))

    def test_aumento_del_producto_gana_al_global(self):
        self.operacion(Oferta.TIPO_AUMENTO, 50, aplicar_a_todos=True)
        self.operacion(Oferta.TIPO_AUMENTO, 10, [self.remera])
        self.assertEqual(self.recargar(self.remera).precio_final, Decimal('22000.00'))

    def test_aumento_pausado_vuelve_al_precio_habitual(self):
        self.operacion(Oferta.TIPO_AUMENTO, 15, [self.remera], activa=False)
        self.assertEqual(self.recargar(self.remera).precio_final, Decimal('20000.00'))

    def test_aumento_no_cambia_stock_ni_categoria(self):
        stock_antes = self.recargar(self.remera).stock_total
        self.operacion(Oferta.TIPO_AUMENTO, 15, categoria=self.categoria)
        remera = self.recargar(self.remera)
        self.assertEqual(remera.stock_total, stock_antes)
        self.assertEqual(remera.categoria, self.categoria)
        self.assertEqual(remera.precio, Decimal('20000.00'))

    def test_home_aumento_fuera_de_ofertas_y_descuento_dentro(self):
        self.operacion(Oferta.TIPO_AUMENTO, 15, [self.remera])
        self.operacion(Oferta.TIPO_DESCUENTO, 20, [self.bota])
        respuesta = self.client.get(reverse('home:home'))
        en_ofertas = {p.pk for p in respuesta.context['productos_oferta']}
        self.assertNotIn(self.remera.pk, en_ofertas)
        self.assertIn(self.bota.pk, en_ofertas)
        # Los dos siguen en el catálogo general
        en_catalogo = {p.pk for p in respuesta.context['productos']}
        self.assertTrue({self.remera.pk, self.bota.pk} <= en_catalogo)
        self.assertContains(respuesta, '$23.000')
        self.assertContains(respuesta, '-20%')
        self.assertNotContains(respuesta, '-15%')

    def test_detalle_con_aumento_sin_etiqueta_ni_tachado(self):
        self.operacion(Oferta.TIPO_AUMENTO, 15, [self.remera])
        respuesta = self.client.get(reverse('productos:detalle_producto', args=[self.remera.id]))
        self.assertContains(respuesta, '23.000')
        self.assertNotContains(respuesta, 'class="product-price-old"')
        self.assertNotContains(respuesta, 'class="product-detail-discount"')

    def test_venta_presencial_cobra_el_precio_aumentado(self):
        self.operacion(Oferta.TIPO_AUMENTO, 15, [self.remera])
        admin = self.admin_logueado()
        variantes = admin.get(reverse('productos:obtener_variantes_producto', args=[self.remera.id])).json()
        self.assertEqual({v['precio'] for v in variantes['variantes']}, {23000.0})
        datos = {'cliente_id': self.cliente_a.user_id, 'metodo_pago': 'efectivo', 'metodo_entrega': 'local',
                 'productos': [{'variante_id': self.remera_m.id, 'cantidad': 1, 'color': ''}]}
        respuesta = admin.post(reverse('pedidos:registrar_venta_local'), json.dumps(datos), content_type='application/json')
        self.assertTrue(respuesta.json()['success'])
        self.assertEqual(VentaLocalItem.objects.get().precio_unitario, Decimal('23000.00'))

    def test_cupon_sigue_descontando_sobre_el_subtotal(self):
        self.operacion(Oferta.TIPO_AUMENTO, 15, aplicar_a_todos=True)
        Oferta.objects.create(nombre='Cupón', descuento=10, codigo='PROMO10', es_cupon=True)
        cupon, descuento = calcular_descuento_cupon(Decimal('23000.00'), 'promo10')
        self.assertEqual(cupon.tipo, Oferta.TIPO_DESCUENTO)
        self.assertEqual(descuento, Decimal('2300.00'))
        # Un cupón nunca se aplica como operación del catálogo
        self.assertEqual(self.recargar(self.remera).precio_final, Decimal('23000.00'))


class AdminOfertasAumentoTests(DatosStockMixin, TestCase):
    def setUp(self):
        self.crear_datos()

    def test_crear_aumento_desde_el_admin(self):
        respuesta = self.admin_logueado().post(reverse('productos:admin_ofertas'), {
            'tipo_oferta': 'catalogo', 'tipo': 'aumento', 'nombre': 'Inflación', 'descuento': '150',
            'alcance': 'productos', 'productos': [self.remera.id],
        })
        self.assertEqual(respuesta.status_code, 302)
        oferta = Oferta.objects.get()
        self.assertEqual((oferta.tipo, oferta.descuento), (Oferta.TIPO_AUMENTO, 150))

    def test_crear_aumento_sin_nombre(self):
        self.admin_logueado().post(reverse('productos:admin_ofertas'), {
            'tipo_oferta': 'catalogo', 'tipo': 'aumento', 'nombre': '', 'descuento': '15',
            'alcance': 'productos', 'productos': [self.remera.id],
        })
        oferta = Oferta.objects.get()
        self.assertEqual((oferta.tipo, oferta.nombre), (Oferta.TIPO_AUMENTO, 'Aumento +15%'))

    def test_descuento_sin_nombre_se_rechaza(self):
        self.admin_logueado().post(reverse('productos:admin_ofertas'), {
            'tipo_oferta': 'catalogo', 'tipo': 'descuento', 'nombre': '', 'descuento': '15',
            'alcance': 'todos',
        })
        self.assertFalse(Oferta.objects.exists())

    def test_descuento_mayor_a_100_se_rechaza(self):
        self.admin_logueado().post(reverse('productos:admin_ofertas'), {
            'tipo_oferta': 'catalogo', 'tipo': 'descuento', 'nombre': 'Mal', 'descuento': '150',
            'alcance': 'todos',
        })
        self.assertFalse(Oferta.objects.exists())

    def test_cupon_siempre_es_descuento(self):
        self.admin_logueado().post(reverse('productos:admin_ofertas'), {
            'tipo_oferta': 'cupon', 'tipo': 'aumento', 'nombre': 'Cupón', 'descuento': '10', 'codigo': 'HOLA',
        })
        self.assertEqual(Oferta.objects.get().tipo, Oferta.TIPO_DESCUENTO)


class CuponesVencimientoTests(DatosStockMixin, TestCase):
    """Cantidad de usos y vencimiento se combinan; el vencimiento puede ser por duración, fecha o ninguno."""

    def setUp(self):
        self.crear_datos()

    def crear_cupon(self, **datos):
        base = {'tipo_oferta': 'cupon', 'nombre': 'Cupón', 'descuento': '10', 'codigo': 'HOLA'}
        base.update(datos)
        return self.admin_logueado().post(reverse('productos:admin_ofertas'), base)

    def fin_del_dia(self, dia):
        return timezone.make_aware(datetime.combine(dia, time(23, 59, 59)))

    def test_usos_y_duracion_en_dias_juntos(self):
        self.crear_cupon(limite_usos='5', vencimiento_tipo='duracion', vencimiento_cantidad='10', vencimiento_unidad='dias')
        cupon = Oferta.objects.get()
        self.assertEqual(cupon.limite_usos, 5)
        self.assertEqual(cupon.fecha_fin, self.fin_del_dia(timezone.localdate() + timedelta(days=10)))
        self.assertTrue(cupon.puede_usarse()[0])

    def test_duracion_en_horas_vence_a_la_hora_exacta(self):
        antes = timezone.now()
        self.crear_cupon(limite_usos='2', vencimiento_tipo='duracion', vencimiento_cantidad='6', vencimiento_unidad='horas')
        cupon = Oferta.objects.get()
        self.assertEqual(cupon.limite_usos, 2)
        esperado = antes.replace(second=0, microsecond=0) + timedelta(hours=6)
        self.assertLess(abs((cupon.fecha_fin - esperado).total_seconds()), 61)
        self.assertTrue(cupon.puede_usarse()[0])

    def test_duracion_en_meses_y_anios(self):
        hoy = timezone.localdate()
        self.crear_cupon(vencimiento_tipo='duracion', vencimiento_cantidad='2', vencimiento_unidad='meses')
        self.assertEqual(Oferta.objects.get(codigo='HOLA').fecha_fin, self.fin_del_dia(_sumar_meses(hoy, 2)))
        self.crear_cupon(codigo='CHAU', vencimiento_tipo='duracion', vencimiento_cantidad='1', vencimiento_unidad='anios')
        self.assertEqual(Oferta.objects.get(codigo='CHAU').fecha_fin, self.fin_del_dia(_sumar_meses(hoy, 12)))

    def test_sumar_meses_ajusta_fin_de_mes(self):
        self.assertEqual(_sumar_meses(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(_sumar_meses(date(2028, 1, 31), 1), date(2028, 2, 29))
        self.assertEqual(_sumar_meses(date(2026, 11, 30), 3), date(2027, 2, 28))
        self.assertEqual(_sumar_meses(date(2028, 2, 29), 12), date(2029, 2, 28))

    def test_sin_vencimiento_con_usos(self):
        self.crear_cupon(limite_usos='5', vencimiento_tipo='sin', fecha_fin='2030-01-01')
        cupon = Oferta.objects.get()
        self.assertIsNone(cupon.fecha_fin)
        self.assertEqual(cupon.limite_usos, 5)

    def test_hasta_una_fecha_con_usos(self):
        manana = timezone.localdate() + timedelta(days=1)
        self.crear_cupon(limite_usos='3', vencimiento_tipo='fecha', fecha_fin=manana.isoformat())
        cupon = Oferta.objects.get()
        self.assertEqual((cupon.limite_usos, cupon.fecha_fin), (3, self.fin_del_dia(manana)))

    def test_fecha_pasada_se_rechaza(self):
        ayer = timezone.localdate() - timedelta(days=1)
        self.crear_cupon(vencimiento_tipo='fecha', fecha_fin=ayer.isoformat())
        self.assertFalse(Oferta.objects.exists())

    def test_duracion_invalida_se_rechaza(self):
        for cantidad in ('', '0', '-3', 'abc'):
            self.crear_cupon(vencimiento_tipo='duracion', vencimiento_cantidad=cantidad, vencimiento_unidad='dias')
        self.assertFalse(Oferta.objects.exists())

    def test_formulario_viejo_solo_con_fecha(self):
        manana = timezone.localdate() + timedelta(days=1)
        self.crear_cupon(fecha_fin=manana.isoformat())
        self.assertEqual(Oferta.objects.get().fecha_fin, self.fin_del_dia(manana))
