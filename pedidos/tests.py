"""Stock de los pedidos: reserva al crear el pedido, aceptación sin doble descuento, devoluciones
únicas, vencimiento de reservas y concurrencia (esta última solo con PostgreSQL)."""
import importlib
import json
import threading
import time
from datetime import timedelta
from decimal import Decimal
from unittest import mock, skipUnless

from django.apps import apps
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from carritos.models import Carrito, CarritoItem
from pedidos import stock_pedidos
from pedidos.models import Pago, Pedido, PedidoItem
from pedidos.views import cambiar_estado_pedido
from productos import stock as stock_productos
from productos.models import Categoria, Color, Producto, Proveedor, Talle, Variante, VarianteColor
from users.models import Cliente


class DatosStockMixin:
    """Catálogo mínimo: un producto con stock por talle y otro con stock por color."""

    def crear_datos(self):
        cache.clear()
        self.categoria = Categoria.objects.create(nombre='Cat')
        self.proveedor = Proveedor.objects.create(nombre='Prov', telefono='123')
        self.talle_m = Talle.objects.create(nombre='M')
        self.talle_l = Talle.objects.create(nombre='L')

        # Producto sin colores: el stock es el del talle
        self.remera = self.crear_producto('R-1', 'Remera', '1000.00')
        self.remera_m = self.crear_variante(self.remera, self.talle_m, 2)
        self.remera_l = self.crear_variante(self.remera, self.talle_l, 3)

        # Producto con stock por color: el stock del talle es la suma de sus colores
        self.bota = self.crear_producto('B-1', 'Bota', '5000.00')
        self.bota_m = self.crear_variante(self.bota, self.talle_m, 0)
        self.rojo = Color.objects.create(nombre='Rojo', codigo_hex='#ff0000')
        self.azul = Color.objects.create(nombre='Azul', codigo_hex='#0000ff')
        self.bota_m_rojo = VarianteColor.objects.create(variante=self.bota_m, color=self.rojo, stock=2)
        self.bota_m_azul = VarianteColor.objects.create(variante=self.bota_m, color=self.azul, stock=1)
        stock_productos.sincronizar_stock_variante(self.bota_m)
        stock_productos.sincronizar_stock_variante(self.remera_m)

        self.cliente_a = self.crear_cliente('30000001')
        self.cliente_b = self.crear_cliente('30000002')
        self.admin = User.objects.create_superuser(username='99999999', password='x', email='admin@example.test')

    def crear_producto(self, codigo, nombre, precio):
        return Producto.objects.create(
            codigo=codigo, nombre=nombre, tipo='Tipo', tela='Tela', precio=Decimal(precio), stock=0,
            categoria=self.categoria, proveedor=self.proveedor, activo=True,
        )

    def crear_variante(self, producto, talle, stock):
        return Variante.objects.create(
            producto=producto, talle=talle, stock=stock, precio=producto.precio, activa=True,
            qr_code=f'QR-{producto.codigo}-{talle.nombre}',
        )

    def crear_cliente(self, dni):
        user = User.objects.create_user(username=dni, password='x', first_name='Clienta', email=f'{dni}@example.test')
        return Cliente.objects.create(user=user, dni=dni, telefono='1155550000')

    def cliente_logueado(self, cliente):
        from django.test import Client
        client = Client()
        client.force_login(cliente.user)
        return client

    def admin_logueado(self):
        from django.test import Client
        client = Client()
        client.force_login(self.admin)
        return client

    def llenar_carrito(self, cliente, lineas):
        """lineas: [(variante, cantidad, color_nombre)]"""
        carrito = Carrito.objects.filter(cliente=cliente, activo=True).first() or Carrito.objects.create(
            cliente=cliente, activo=True, expires_at=timezone.now() + timedelta(hours=1)
        )
        carrito.items.all().delete()
        for variante, cantidad, color in lineas:
            CarritoItem.objects.create(
                carrito=carrito, variante=variante, color_nombre=color, cantidad=cantidad,
                precio_unitario=variante.producto.precio, precio_total=0,
            )
        return carrito

    def comprar(self, cliente, lineas, metodo_pago='transferencia', client=None):
        self.llenar_carrito(cliente, lineas)
        client = client or self.cliente_logueado(cliente)
        return client.post(reverse('pedidos:crear_pago'), {'metodo_entrega': 'local', 'metodo_pago': metodo_pago})

    def crear_pedido(self, cliente, lineas, estado='pendiente', metodo_pago='transferencia', stock_descontado=False):
        """Pedido armado a mano, sin mover stock."""
        total = sum(variante.producto.precio * cantidad for variante, cantidad, _ in lineas)
        pedido = Pedido.objects.create(
            cliente=cliente, total=total, deuda=total, tipo_venta='online', estado=estado,
            metodo_pago=metodo_pago, metodo_entrega='local', stock_descontado=stock_descontado,
        )
        for variante, cantidad, color in lineas:
            PedidoItem.objects.create(
                pedido=pedido, variante=variante, color_nombre=color, cantidad=cantidad,
                precio_unitario=variante.producto.precio, precio_total=variante.producto.precio * cantidad,
            )
        return pedido

    def stock(self, objeto):
        objeto.refresh_from_db(fields=['stock'])
        return objeto.stock

    def mock_mercado_pago(self, referencia_de_pedido=None, estado='approved', monto=None):
        """SDK de Mercado Pago falso: preferencia creada y, si se indica, un pago con esa referencia."""
        sdk = mock.MagicMock()
        sdk.preference.return_value.create.return_value = {
            'status': 201, 'response': {'init_point': 'https://mp.example.test/pagar'},
        }
        if referencia_de_pedido is not None:
            sdk.payment.return_value.get.return_value = {
                'status': 200,
                'response': {
                    'status': estado,
                    'external_reference': referencia_de_pedido,
                    'transaction_amount': float(monto or 0),
                    'installments': 1,
                    'payment_type_id': 'account_money',
                    'net_received_amount': float(monto or 0),
                },
            }
        return sdk


class ReservaAlCrearPedidoTests(DatosStockMixin, TestCase):
    def setUp(self):
        self.crear_datos()

    def test_transferencia_descuenta_al_crear_el_pedido(self):
        respuesta = self.comprar(self.cliente_a, [(self.remera_m, 1, None)])
        pedido = Pedido.objects.get(cliente=self.cliente_a)
        self.assertRedirects(respuesta, reverse('pedidos:pago_transferencia', args=[pedido.id]), fetch_redirect_response=False)
        self.assertEqual(pedido.estado, 'pendiente')
        self.assertTrue(pedido.stock_descontado)
        self.assertEqual(self.stock(self.remera_m), 1)
        self.assertEqual(self.stock(self.remera), 1 + 3)  # producto = suma de sus talles

    def test_aceptar_el_pago_no_vuelve_a_descontar(self):
        self.comprar(self.cliente_a, [(self.remera_m, 1, None)])
        pedido = Pedido.objects.get(cliente=self.cliente_a)
        self.admin_logueado().post(reverse('pedidos:actualizar_estado_pedido', args=[pedido.id]), {'estado': 'aceptado'})
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'aceptado')
        self.assertEqual(self.stock(self.remera_m), 1)

    def test_registrar_el_pago_completo_no_vuelve_a_descontar(self):
        self.comprar(self.cliente_a, [(self.remera_m, 2, None)])
        pedido = Pedido.objects.get(cliente=self.cliente_a)
        respuesta = self.admin_logueado().post(
            reverse('pedidos:registrar_pago_pedido', args=[pedido.id]),
            data=json.dumps({'monto': str(pedido.total), 'metodo_pago': 'transferencia'}),
            content_type='application/json',
        )
        self.assertTrue(respuesta.json()['success'])
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'aceptado')
        self.assertEqual(self.stock(self.remera_m), 0)

    def test_no_se_pueden_comprar_unidades_inexistentes(self):
        respuesta = self.comprar(self.cliente_a, [(self.remera_m, 3, None)])
        self.assertRedirects(respuesta, reverse('pedidos:checkout'), fetch_redirect_response=False)
        self.assertFalse(Pedido.objects.exists())
        self.assertEqual(self.stock(self.remera_m), 2)

    def test_la_segunda_clienta_no_se_lleva_la_unidad_reservada(self):
        self.comprar(self.cliente_a, [(self.bota_m, 1, 'Azul')])
        respuesta = self.comprar(self.cliente_b, [(self.bota_m, 1, 'Azul')])
        self.assertRedirects(respuesta, reverse('pedidos:checkout'), fetch_redirect_response=False)
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(self.stock(self.bota_m_azul), 0)

    def test_pedido_con_varios_productos_no_deja_descuentos_parciales(self):
        pedido = self.crear_pedido(self.cliente_a, [(self.remera_m, 1, None), (self.bota_m, 5, 'Rojo')])
        with self.assertRaises(ValueError):
            stock_pedidos.descontar_stock_pedido(pedido)
        pedido.refresh_from_db()
        self.assertFalse(pedido.stock_descontado)
        self.assertEqual(self.stock(self.remera_m), 2)
        self.assertEqual(self.stock(self.bota_m_rojo), 2)

    def test_lineas_repetidas_del_mismo_talle_y_color_se_validan_sumadas(self):
        with self.assertRaises(ValueError):
            stock_productos.descontar_stock_lineas([(self.remera_m, 2, None), (self.remera_m, 1, None)])
        self.assertEqual(self.stock(self.remera_m), 2)

    def test_stock_por_color_talle_y_producto_quedan_consistentes(self):
        self.comprar(self.cliente_a, [(self.bota_m, 1, 'Rojo'), (self.remera_l, 2, None)])
        self.assertEqual(self.stock(self.bota_m_rojo), 1)
        self.assertEqual(self.stock(self.bota_m_azul), 1)
        self.assertEqual(self.stock(self.bota_m), 2)       # talle = suma de colores
        self.assertEqual(self.stock(self.bota), 2)         # producto = suma de talles
        self.assertEqual(self.stock(self.remera_l), 1)
        pedido = Pedido.objects.get(cliente=self.cliente_a)
        self.admin_logueado().post(reverse('pedidos:actualizar_estado_pedido', args=[pedido.id]), {'estado': 'cancelado'})
        self.assertEqual(self.stock(self.bota_m_rojo), 2)
        self.assertEqual(self.stock(self.bota_m), 3)
        self.assertEqual(self.stock(self.bota), 3)
        self.assertEqual(self.stock(self.remera_l), 3)

    def test_efectivo_y_qr_tambien_reservan(self):
        self.comprar(self.cliente_a, [(self.remera_m, 1, None)], metodo_pago='efectivo')
        qr = {'qr_image': 'data:image/png;base64,AAAA', 'payment_url': 'https://mp.example.test/qr'}
        with mock.patch('pedidos.views.crear_qr_link_pago_mercado_pago', return_value=qr):
            respuesta = self.comprar(self.cliente_b, [(self.remera_m, 1, None)], metodo_pago='mercado_pago_qr')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Pedido.objects.filter(estado='pendiente', stock_descontado=True).count(), 2)
        self.assertEqual(self.stock(self.remera_m), 0)

    def test_editar_un_pendiente_reservado_mueve_el_stock(self):
        self.comprar(self.cliente_a, [(self.remera_l, 1, None)])
        pedido = Pedido.objects.get(cliente=self.cliente_a)
        item = pedido.items.get()
        self.admin_logueado().post(reverse('pedidos:editar_pedido', args=[pedido.id]), {
            f'cantidad_{item.id}': '3', 'metodo_entrega': 'local', 'estado': 'pendiente',
        })
        self.assertEqual(self.stock(self.remera_l), 0)


class CancelacionesYRepeticionesTests(DatosStockMixin, TestCase):
    def setUp(self):
        self.crear_datos()
        self.comprar(self.cliente_a, [(self.remera_m, 2, None)])
        self.pedido = Pedido.objects.get(cliente=self.cliente_a)
        self.assertEqual(self.stock(self.remera_m), 0)

    def test_cancelar_libera_las_unidades(self):
        self.admin_logueado().post(reverse('pedidos:actualizar_estado_pedido', args=[self.pedido.id]), {'estado': 'cancelado'})
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, 'cancelado')
        self.assertFalse(self.pedido.stock_descontado)
        self.assertEqual(self.stock(self.remera_m), 2)

    def test_rechazar_libera_las_unidades(self):
        self.admin_logueado().post(reverse('pedidos:actualizar_estado_pedido', args=[self.pedido.id]), {'estado': 'rechazado'})
        self.assertEqual(self.stock(self.remera_m), 2)

    def test_cancelar_un_pedido_aceptado_libera_las_unidades(self):
        admin = self.admin_logueado()
        admin.post(reverse('pedidos:actualizar_estado_pedido', args=[self.pedido.id]), {'estado': 'aceptado'})
        self.assertEqual(self.stock(self.remera_m), 0)
        admin.post(reverse('pedidos:actualizar_estado_pedido', args=[self.pedido.id]), {'estado': 'cancelado'})
        self.assertEqual(self.stock(self.remera_m), 2)

    def test_cancelar_dos_veces_devuelve_una_sola_vez(self):
        admin = self.admin_logueado()
        url = reverse('pedidos:actualizar_estado_pedido', args=[self.pedido.id])
        admin.post(url, {'estado': 'cancelado'})
        admin.post(url, {'estado': 'cancelado'})
        self.assertEqual(self.stock(self.remera_m), 2)
        self.assertFalse(stock_pedidos.reponer_stock_pedido(self.pedido))
        self.assertEqual(self.stock(self.remera_m), 2)

    def test_descontar_dos_veces_descuenta_una_sola_vez(self):
        self.assertFalse(stock_pedidos.descontar_stock_pedido(self.pedido))
        self.assertEqual(self.stock(self.remera_m), 0)

    def test_un_cambio_de_estado_que_no_es_cancelacion_no_libera(self):
        admin = self.admin_logueado()
        url = reverse('pedidos:actualizar_estado_pedido', args=[self.pedido.id])
        for estado in ('aceptado', 'en_preparacion', 'listo_retirar', 'entregado'):
            admin.post(url, {'estado': estado})
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, 'entregado')
        self.assertEqual(self.stock(self.remera_m), 0)


class VencimientoTests(DatosStockMixin, TestCase):
    def setUp(self):
        self.crear_datos()

    def envejecer(self, pedido, **delta):
        Pedido.objects.filter(pk=pedido.pk).update(created_at=timezone.now() - timedelta(**delta))

    def test_pendiente_vence_a_las_48_horas_y_libera(self):
        self.comprar(self.cliente_a, [(self.remera_m, 1, None)])
        pedido = Pedido.objects.get()
        self.envejecer(pedido, hours=47)
        self.assertEqual(stock_pedidos.vencer_reservas(), 0)
        self.envejecer(pedido, hours=49)
        self.assertEqual(stock_pedidos.vencer_reservas(), 1)
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'vencido')
        self.assertEqual(pedido.deuda, 0)
        self.assertEqual(self.stock(self.remera_m), 2)
        # Repetir no devuelve otra vez
        self.assertEqual(stock_pedidos.vencer_reservas(), 0)
        self.assertEqual(self.stock(self.remera_m), 2)

    def test_reserva_de_mercado_pago_vence_con_el_link(self):
        with mock.patch('pedidos.views.sdk', self.mock_mercado_pago()):
            self.comprar(self.cliente_a, [(self.remera_m, 1, None)], metodo_pago='mercado_pago')
        pedido = Pedido.objects.get()
        self.envejecer(pedido, minutes=70)
        self.assertEqual(stock_pedidos.vencer_reservas(), 0)  # margen para un pago en curso
        self.envejecer(pedido, minutes=80)
        self.assertEqual(stock_pedidos.vencer_reservas(), 1)
        self.assertEqual(self.stock(self.remera_m), 2)

    def test_pendiente_anterior_a_la_reserva_no_vence_solo_y_descuenta_al_aceptar(self):
        pedido = self.crear_pedido(self.cliente_a, [(self.remera_m, 1, None)])  # stock_descontado=False
        self.envejecer(pedido, days=10)
        self.assertEqual(stock_pedidos.vencer_reservas(), 0)
        self.admin_logueado().post(reverse('pedidos:actualizar_estado_pedido', args=[pedido.id]), {'estado': 'aceptado'})
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'aceptado')
        self.assertTrue(pedido.stock_descontado)
        self.assertEqual(self.stock(self.remera_m), 1)

    def test_admin_reactiva_un_vencido_si_hay_stock(self):
        self.comprar(self.cliente_a, [(self.remera_m, 1, None)])
        pedido = Pedido.objects.get()
        self.envejecer(pedido, hours=49)
        stock_pedidos.vencer_reservas()
        self.admin_logueado().post(reverse('pedidos:actualizar_estado_pedido', args=[pedido.id]), {'estado': 'aceptado'})
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'aceptado')
        self.assertEqual(pedido.deuda, pedido.total)
        self.assertEqual(self.stock(self.remera_m), 1)

    def test_no_se_reactiva_un_vencido_sin_stock(self):
        self.comprar(self.cliente_a, [(self.remera_m, 2, None)])
        pedido = Pedido.objects.get()
        self.envejecer(pedido, hours=49)
        stock_pedidos.vencer_reservas()
        self.comprar(self.cliente_b, [(self.remera_m, 2, None)])
        respuesta = self.admin_logueado().post(
            reverse('pedidos:actualizar_estado_pedido', args=[pedido.id]), {'estado': 'aceptado'}, follow=True
        )
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'vencido')
        self.assertIn('ya no hay stock', ' '.join(str(m) for m in respuesta.context['messages']))
        self.assertEqual(self.stock(self.remera_m), 0)


class MercadoPagoTests(DatosStockMixin, TestCase):
    def setUp(self):
        self.crear_datos()

    def ir_a_pagar(self, cliente, lineas):
        sdk = self.mock_mercado_pago()
        with mock.patch('pedidos.views.sdk', sdk):
            respuesta = self.comprar(cliente, lineas, metodo_pago='mercado_pago')
        return respuesta, sdk.preference.return_value.create.call_args[0][0]

    def volver_de_mercado_pago(self, cliente, preferencia, payment_id='111', estado='approved', client=None):
        pedido = Pedido.objects.get(pk=int(preferencia['external_reference'].split('_')[1]))
        sdk = self.mock_mercado_pago(preferencia['external_reference'], estado=estado, monto=pedido.total)
        client = client or self.cliente_logueado(cliente)
        with mock.patch('pedidos.views.sdk', sdk):
            return client.get(reverse('pedidos:pago_exitoso'), {'payment_id': payment_id}, follow=True)

    def test_ir_a_pagar_reserva_y_el_link_vence_con_la_reserva(self):
        respuesta, preferencia = self.ir_a_pagar(self.cliente_a, [(self.remera_m, 2, None)])
        self.assertRedirects(respuesta, 'https://mp.example.test/pagar', fetch_redirect_response=False)
        pedido = Pedido.objects.get()
        self.assertEqual((pedido.estado, pedido.metodo_pago, pedido.stock_descontado), ('pendiente', 'mercado_pago', True))
        self.assertEqual(preferencia['external_reference'].split('_')[:2], ['pedido', str(pedido.id)])
        self.assertTrue(preferencia['expires'])
        self.assertIn('expiration_date_to', preferencia)
        self.assertEqual(self.stock(self.remera_m), 0)
        # Mientras paga, nadie más se lleva esas unidades
        self.assertRedirects(self.comprar(self.cliente_b, [(self.remera_m, 1, None)]), reverse('pedidos:checkout'), fetch_redirect_response=False)

    def test_pago_aprobado_confirma_sin_volver_a_descontar(self):
        _, preferencia = self.ir_a_pagar(self.cliente_a, [(self.remera_m, 1, None)])
        self.volver_de_mercado_pago(self.cliente_a, preferencia)
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.estado, 'aceptado')
        self.assertEqual(pedido.monto_pagado, pedido.total)
        self.assertEqual(Pago.objects.filter(pedido=pedido).count(), 1)
        self.assertEqual(self.stock(self.remera_m), 1)
        self.assertFalse(CarritoItem.objects.filter(carrito__cliente=self.cliente_a).exists())

    def test_retorno_repetido_no_duplica_pago_ni_stock(self):
        _, preferencia = self.ir_a_pagar(self.cliente_a, [(self.remera_m, 1, None)])
        self.volver_de_mercado_pago(self.cliente_a, preferencia)
        respuesta = self.volver_de_mercado_pago(self.cliente_a, preferencia)
        self.assertIn('ya estaba registrado', ' '.join(str(m) for m in respuesta.context['messages']))
        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(self.stock(self.remera_m), 1)

    def test_pago_no_aprobado_no_confirma_y_la_reserva_sigue(self):
        _, preferencia = self.ir_a_pagar(self.cliente_a, [(self.remera_m, 1, None)])
        self.volver_de_mercado_pago(self.cliente_a, preferencia, estado='rejected')
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.estado, 'pendiente')
        self.assertFalse(Pago.objects.exists())
        self.assertEqual(self.stock(self.remera_m), 1)

    def test_pago_de_otra_clienta_no_confirma(self):
        _, preferencia = self.ir_a_pagar(self.cliente_a, [(self.remera_m, 1, None)])
        self.volver_de_mercado_pago(self.cliente_b, preferencia)
        self.assertEqual(Pedido.objects.get().estado, 'pendiente')
        self.assertFalse(Pago.objects.exists())

    def test_reintentar_el_pago_libera_la_reserva_anterior(self):
        _, primera = self.ir_a_pagar(self.cliente_a, [(self.remera_m, 2, None)])
        respuesta, segunda = self.ir_a_pagar(self.cliente_a, [(self.remera_m, 2, None)])
        self.assertRedirects(respuesta, 'https://mp.example.test/pagar', fetch_redirect_response=False)
        anterior = Pedido.objects.get(pk=int(primera['external_reference'].split('_')[1]))
        nuevo = Pedido.objects.get(pk=int(segunda['external_reference'].split('_')[1]))
        self.assertEqual((anterior.estado, anterior.stock_descontado), ('vencido', False))
        self.assertEqual((nuevo.estado, nuevo.stock_descontado), ('pendiente', True))
        self.assertEqual(self.stock(self.remera_m), 0)

    def test_pago_tardio_con_stock_reactiva_el_pedido(self):
        _, preferencia = self.ir_a_pagar(self.cliente_a, [(self.remera_m, 1, None)])
        Pedido.objects.update(created_at=timezone.now() - timedelta(hours=3))
        stock_pedidos.vencer_reservas()
        self.assertEqual(self.stock(self.remera_m), 2)
        self.volver_de_mercado_pago(self.cliente_a, preferencia)
        pedido = Pedido.objects.get()
        self.assertEqual((pedido.estado, pedido.stock_descontado), ('aceptado', True))
        self.assertEqual(self.stock(self.remera_m), 1)

    def test_pago_tardio_sin_stock_registra_el_pago_y_avisa(self):
        _, preferencia = self.ir_a_pagar(self.cliente_a, [(self.remera_m, 2, None)])
        Pedido.objects.update(created_at=timezone.now() - timedelta(hours=3))
        stock_pedidos.vencer_reservas()
        self.comprar(self.cliente_b, [(self.remera_m, 2, None)])
        respuesta = self.volver_de_mercado_pago(self.cliente_a, preferencia)
        pedido = Pedido.objects.get(cliente=self.cliente_a)
        self.assertEqual(pedido.estado, 'vencido')
        self.assertEqual(Pago.objects.filter(pedido=pedido).count(), 1)
        self.assertIn('ya no están disponibles', ' '.join(str(m) for m in respuesta.context['messages']))
        self.assertEqual(self.stock(self.remera_m), 0)

    def test_link_viejo_del_carrito_sigue_funcionando(self):
        """Links de pago creados antes de esta versión (referencia carrito_...)."""
        carrito = self.llenar_carrito(self.cliente_a, [(self.bota_m, 1, 'Rojo')])
        referencia = f'carrito_{carrito.id}_abc'
        client = self.cliente_logueado(self.cliente_a)
        session = client.session
        session['mp_external_reference'] = referencia
        session.save()
        with mock.patch('pedidos.views.sdk', self.mock_mercado_pago(referencia, monto=Decimal('5000.00'))):
            client.get(reverse('pedidos:pago_exitoso'), {'payment_id': '222'})
        pedido = Pedido.objects.get()
        self.assertEqual((pedido.estado, pedido.stock_descontado), ('aceptado', True))
        self.assertEqual(self.stock(self.bota_m_rojo), 1)


class OtrosFlujosTests(DatosStockMixin, TestCase):
    def setUp(self):
        self.crear_datos()

    def test_venta_presencial_descuenta_y_valida(self):
        admin = self.admin_logueado()
        url = reverse('pedidos:registrar_venta_local')
        datos = {'cliente_id': self.cliente_a.user_id, 'metodo_pago': 'efectivo', 'metodo_entrega': 'local',
                 'productos': [{'variante_id': self.bota_m.id, 'cantidad': 1, 'color': 'Azul'}]}
        self.assertTrue(admin.post(url, json.dumps(datos), content_type='application/json').json()['success'])
        self.assertEqual(self.stock(self.bota_m_azul), 0)
        self.assertEqual(self.stock(self.bota_m), 2)
        respuesta = admin.post(url, json.dumps(datos), content_type='application/json')
        self.assertFalse(respuesta.json()['success'])
        self.assertEqual(self.stock(self.bota_m_azul), 0)

    def test_migracion_marca_los_pedidos_existentes(self):
        aceptado = self.crear_pedido(self.cliente_a, [(self.remera_m, 1, None)], estado='entregado')
        pendiente = self.crear_pedido(self.cliente_a, [(self.remera_m, 1, None)])
        viejo = self.crear_pedido(self.cliente_a, [(self.remera_m, 1, None)], metodo_pago=None)
        cancelado = self.crear_pedido(self.cliente_a, [(self.remera_m, 1, None)], estado='cancelado')
        migracion = importlib.import_module('pedidos.migrations.0039_pedido_stock_descontado')
        migracion.marcar_stock_descontado(apps, None)
        marcas = dict(Pedido.objects.values_list('pk', 'stock_descontado'))
        self.assertEqual(
            [marcas[p.pk] for p in (aceptado, pendiente, viejo, cancelado)],
            [True, False, True, False],
        )

    def test_transicion_invalida_no_mueve_stock(self):
        pedido = self.crear_pedido(self.cliente_a, [(self.remera_m, 1, None)], estado='entregado', stock_descontado=True)
        with self.assertRaises(ValueError):
            cambiar_estado_pedido(pedido, 'cancelado')
        self.assertEqual(self.stock(self.remera_m), 2)


def en_paralelo(*funciones):
    """Corre las funciones a la vez (cada una en su hilo y su conexión a la base)."""
    barrera = threading.Barrier(len(funciones))
    resultados = [None] * len(funciones)
    errores = [None] * len(funciones)

    def correr(indice, funcion):
        try:
            barrera.wait()
            resultados[indice] = funcion()
        except Exception as error:  # se devuelve para verificarlo en el test
            errores[indice] = error
        finally:
            connection.close()

    hilos = [threading.Thread(target=correr, args=(i, f)) for i, f in enumerate(funciones)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=60)
    return resultados, errores


def con_demora(segundos=0.4):
    """Hace más lenta la parte del descuento que corre con las filas bloqueadas, para que las
    operaciones simultáneas se superpongan de verdad."""
    original = stock_productos.sincronizar_stock_variante

    def lenta(variante):
        time.sleep(segundos)
        return original(variante)

    return mock.patch('productos.stock.sincronizar_stock_variante', side_effect=lenta)


@skipUnless(connection.vendor == 'postgresql', 'La concurrencia real se prueba con PostgreSQL (SQLite no bloquea filas).')
class ConcurrenciaPostgresTests(DatosStockMixin, TransactionTestCase):
    def setUp(self):
        self.crear_datos()

    def test_dos_reservas_simultaneas_de_la_ultima_unidad(self):
        primero = self.crear_pedido(self.cliente_a, [(self.bota_m, 1, 'Azul')])
        segundo = self.crear_pedido(self.cliente_b, [(self.bota_m, 1, 'Azul')])
        with con_demora():
            resultados, errores = en_paralelo(
                lambda: stock_pedidos.descontar_stock_pedido(primero),
                lambda: stock_pedidos.descontar_stock_pedido(segundo),
            )
        self.assertEqual(sorted(r for r in resultados if r is not None), [True])
        self.assertEqual(len([e for e in errores if isinstance(e, ValueError)]), 1, errores)
        self.assertEqual(self.stock(self.bota_m_azul), 0)
        self.assertEqual(Pedido.objects.filter(stock_descontado=True).count(), 1)

    def test_dos_checkouts_simultaneos_no_se_llevan_la_misma_ultima_unidad(self):
        client_a = self.cliente_logueado(self.cliente_a)
        client_b = self.cliente_logueado(self.cliente_b)
        self.llenar_carrito(self.cliente_a, [(self.bota_m, 1, 'Azul')])
        self.llenar_carrito(self.cliente_b, [(self.bota_m, 1, 'Azul')])
        datos = {'metodo_entrega': 'local', 'metodo_pago': 'transferencia'}
        with con_demora():
            respuestas, errores = en_paralelo(
                lambda: client_a.post(reverse('pedidos:crear_pago'), datos),
                lambda: client_b.post(reverse('pedidos:crear_pago'), datos),
            )
        self.assertEqual(errores, [None, None])
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(self.stock(self.bota_m_azul), 0)
        self.assertEqual(sorted(r['Location'].endswith('/checkout/') for r in respuestas), [False, True])

    def test_compras_simultaneas_de_distintos_colores_mantienen_las_sumas(self):
        primero = self.crear_pedido(self.cliente_a, [(self.bota_m, 1, 'Rojo')])
        segundo = self.crear_pedido(self.cliente_b, [(self.bota_m, 1, 'Azul')])
        with con_demora(0.2):
            _, errores = en_paralelo(
                lambda: stock_pedidos.descontar_stock_pedido(primero),
                lambda: stock_pedidos.descontar_stock_pedido(segundo),
            )
        self.assertEqual(errores, [None, None])
        self.assertEqual((self.stock(self.bota_m_rojo), self.stock(self.bota_m_azul)), (1, 0))
        self.assertEqual(self.stock(self.bota_m), 1)
        self.assertEqual(self.stock(self.bota), 1)

    def test_cancelaciones_simultaneas_devuelven_una_sola_vez(self):
        self.comprar(self.cliente_a, [(self.remera_m, 2, None)])
        pedido = Pedido.objects.get()
        url = reverse('pedidos:actualizar_estado_pedido', args=[pedido.id])
        admin_1, admin_2 = self.admin_logueado(), self.admin_logueado()
        with con_demora():
            _, errores = en_paralelo(
                lambda: admin_1.post(url, {'estado': 'cancelado'}),
                lambda: admin_2.post(url, {'estado': 'cancelado'}),
            )
        self.assertEqual(errores, [None, None])
        self.assertEqual(self.stock(self.remera_m), 2)

    def test_retornos_simultaneos_de_mercado_pago_registran_un_solo_pago(self):
        sdk = self.mock_mercado_pago()
        with mock.patch('pedidos.views.sdk', sdk):
            self.comprar(self.cliente_a, [(self.remera_m, 1, None)], metodo_pago='mercado_pago')
        referencia = sdk.preference.return_value.create.call_args[0][0]['external_reference']
        pedido = Pedido.objects.get()
        client_1, client_2 = self.cliente_logueado(self.cliente_a), self.cliente_logueado(self.cliente_a)
        url = reverse('pedidos:pago_exitoso')
        with mock.patch('pedidos.views.sdk', self.mock_mercado_pago(referencia, monto=pedido.total)):
            _, errores = en_paralelo(
                lambda: client_1.get(url, {'payment_id': '333'}),
                lambda: client_2.get(url, {'payment_id': '333'}),
            )
        self.assertEqual(errores, [None, None])
        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(Pedido.objects.get().estado, 'aceptado')
        self.assertEqual(self.stock(self.remera_m), 1)

    def test_vencimientos_simultaneos_devuelven_una_sola_vez(self):
        self.comprar(self.cliente_a, [(self.remera_m, 2, None)])
        Pedido.objects.update(created_at=timezone.now() - timedelta(hours=49))
        with con_demora():
            resultados, errores = en_paralelo(stock_pedidos.vencer_reservas, stock_pedidos.vencer_reservas)
        self.assertEqual(errores, [None, None])
        self.assertEqual(sum(resultados), 1)
        self.assertEqual(self.stock(self.remera_m), 2)
