"""Cambios de productos en ventas presenciales: stock por talle y color, diferencias de precio, notas
de crédito, duplicados y permisos. También verifica que los cambios de pedidos online sigan igual."""
import json
from decimal import Decimal
from unittest import mock, skipUnless

from django.db import IntegrityError, connection
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from pedidos.models import Cambio, NotaCredito, Pedido, VentaLocal
from pedidos.tests import DatosStockMixin, con_demora, en_paralelo
from users.models import Cliente


class CambioVentaLocalMixin(DatosStockMixin):
    def preparar(self):
        self.crear_datos()
        self.admin_client = self.admin_logueado()

    def vender(self, lineas, client=None):
        """Venta presencial real (por la vista del POS). lineas: [(variante, cantidad, color)]"""
        datos = {
            'cliente_id': self.cliente_a.user_id, 'metodo_pago': 'efectivo', 'metodo_entrega': 'local',
            'productos': [{'variante_id': v.id, 'cantidad': c, 'color': color or ''} for v, c, color in lineas],
        }
        respuesta = (client or self.admin_client).post(
            reverse('pedidos:registrar_venta_local'), json.dumps(datos), content_type='application/json'
        )
        self.assertTrue(respuesta.json()['success'], respuesta.json())
        return VentaLocal.objects.get(pk=respuesta.json()['venta_id'])

    def item(self, venta, variante, color=''):
        return venta.items.get(variante=variante, color=color)

    def url(self, venta_id):
        return reverse('pedidos:registrar_cambio_venta_local', args=[venta_id])

    def enviar(self, venta_id, datos, client=None):
        return (client or self.admin_client).post(self.url(venta_id), json.dumps(datos), content_type='application/json')

    def datos_cambio(self, item, cantidad_devuelta, variante, color, cantidad_entregada, **extra):
        return {
            'item_id': item.id, 'cantidad_devuelta': cantidad_devuelta,
            'variante_entregada': f'{variante.id}|{color or ""}', 'cantidad_entregada': cantidad_entregada,
            **extra,
        }

    def revisar(self, venta, datos, client=None):
        return self.enviar(venta.id, datos, client)

    def cambiar(self, venta, datos, client=None):
        """Revisa y confirma, como la pantalla. Devuelve (resumen, respuesta de la confirmación)."""
        revision = self.revisar(venta, datos, client)
        self.assertEqual(revision.status_code, 200, revision.json())
        confirmar = dict(datos, confirmar=True, operacion_id=revision.json()['operacion_id'])
        return revision.json(), self.enviar(venta.id, confirmar, client)


class CambioVentaLocalTests(CambioVentaLocalMixin, TestCase):
    def setUp(self):
        self.preparar()

    def test_cambio_exitoso_devuelve_y_descuenta_en_los_colores_correctos(self):
        venta = self.vender([(self.bota_m, 1, 'Rojo')])
        self.assertEqual((self.stock(self.bota_m_rojo), self.stock(self.bota_m_azul)), (1, 1))

        resumen, respuesta = self.cambiar(venta, self.datos_cambio(self.item(venta, self.bota_m, 'Rojo'), 1, self.bota_m, 'Azul', 1))
        self.assertTrue(respuesta.json()['success'], respuesta.json())
        self.assertEqual(resumen['resumen']['resultado'], 'sin_diferencia')
        self.assertEqual((self.stock(self.bota_m_rojo), self.stock(self.bota_m_azul)), (2, 0))
        self.assertEqual(self.stock(self.bota_m), 2)   # talle = suma de colores
        self.assertEqual(self.stock(self.bota), 2)     # producto = suma de talles

        cambio = Cambio.objects.get()
        self.assertEqual((cambio.venta_local_id, cambio.pedido_id), (venta.id, None))
        self.assertEqual((cambio.variante_devuelta, cambio.color_devuelto, cambio.cantidad_devuelta), (self.bota_m, 'Rojo', 1))
        self.assertEqual((cambio.variante_entregada, cambio.color_entregado, cambio.cantidad_entregada), (self.bota_m, 'Azul', 1))
        self.assertEqual((cambio.producto_devuelto, cambio.producto_entregado), (self.bota, self.bota))
        self.assertEqual((cambio.precio_devuelto, cambio.precio_entregado, cambio.diferencia),
                         (Decimal('5000.00'), Decimal('5000.00'), Decimal('0.00')))
        self.assertEqual(cambio.registrado_por, self.admin)
        venta.refresh_from_db()
        self.assertEqual((venta.total, venta.saldo_pendiente, venta.estado_pago), (Decimal('5000.00'), Decimal('0.00'), 'PAGADO'))
        self.assertFalse(NotaCredito.objects.exists())
        # La venta original no se toca: sus líneas siguen como se vendieron
        self.assertEqual(list(venta.items.values_list('variante_id', 'color', 'cantidad')), [(self.bota_m.id, 'Rojo', 1)])

    def test_talle_sin_colores_devuelve_y_descuenta_el_talle(self):
        venta = self.vender([(self.remera_l, 2, None)])
        self.assertEqual((self.stock(self.remera_l), self.stock(self.remera_m)), (1, 2))
        _, respuesta = self.cambiar(venta, self.datos_cambio(self.item(venta, self.remera_l), 1, self.remera_m, '', 1))
        self.assertTrue(respuesta.json()['success'])
        self.assertEqual((self.stock(self.remera_l), self.stock(self.remera_m)), (2, 1))
        self.assertEqual(self.stock(self.remera), 3)

    def test_sin_stock_del_reemplazo_no_se_registra_nada(self):
        venta = self.vender([(self.remera_l, 1, None)])
        self.vender([(self.bota_m, 1, 'Azul')])  # se lleva el último azul
        datos = self.datos_cambio(self.item(venta, self.remera_l), 1, self.bota_m, 'Azul', 1)
        revision = self.revisar(venta, datos)
        self.assertEqual(revision.status_code, 400)
        self.assertIn('No hay stock suficiente', revision.json()['error'])
        # Aunque la confirmación llegue igual, el stock se vuelve a validar con las filas bloqueadas
        respuesta = self.enviar(venta.id, dict(datos, confirmar=True, operacion_id='a' * 32))
        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(Cambio.objects.exists())
        self.assertEqual((self.stock(self.remera_l), self.stock(self.bota_m_azul)), (2, 0))

    def test_no_se_cambian_mas_unidades_que_las_compradas(self):
        venta = self.vender([(self.remera_l, 2, None)])
        item = self.item(venta, self.remera_l)
        respuesta = self.revisar(venta, self.datos_cambio(item, 3, self.remera_m, '', 1))
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('como máximo 2', respuesta.json()['error'])

        self.assertTrue(self.cambiar(venta, self.datos_cambio(item, 2, self.remera_m, '', 2))[1].json()['success'])
        respuesta = self.revisar(venta, self.datos_cambio(item, 1, self.remera_m, '', 0 + 1))
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('como máximo 0', respuesta.json()['error'])
        detalle = self.admin_client.get(reverse('pedidos:detalle_venta_local', args=[venta.id])).json()
        self.assertEqual(detalle['productos'][0]['cambiables'], 0)

    def test_diferencia_a_cobrar_suma_al_saldo_de_la_venta_y_se_paga_como_siempre(self):
        venta = self.vender([(self.remera_l, 1, None)])
        resumen, respuesta = self.cambiar(venta, self.datos_cambio(self.item(venta, self.remera_l), 1, self.bota_m, 'Rojo', 1))
        self.assertEqual((resumen['resumen']['diferencia'], resumen['resumen']['resultado']), ('4000.00', 'cobrar'))
        self.assertIn('abona $4.000', resumen['resumen']['detalle'])
        self.assertIn('debe abonar $4.000', respuesta.json()['mensaje'])
        venta.refresh_from_db()
        self.assertEqual((venta.total, venta.monto_pagado, venta.saldo_pendiente, venta.estado_pago),
                         (Decimal('5000.00'), Decimal('1000.00'), Decimal('4000.00'), 'PARCIAL'))
        self.assertEqual(Cliente.objects.get(pk=self.cliente_a.pk).deuda_total, Decimal('4000.00'))
        self.assertEqual(Cambio.objects.get().diferencia, Decimal('4000.00'))
        self.assertFalse(NotaCredito.objects.exists())

        pago = self.admin_client.post(
            reverse('pedidos:registrar_pago_venta', args=[venta.id]), json.dumps({'monto': '4000'}), content_type='application/json'
        )
        self.assertTrue(pago.json()['success'])
        venta.refresh_from_db()
        self.assertEqual((venta.saldo_pendiente, venta.estado_pago), (Decimal('0.00'), 'PAGADO'))
        self.assertEqual(Cliente.objects.get(pk=self.cliente_a.pk).deuda_total, Decimal('0.00'))

    def test_diferencia_a_favor_genera_una_nota_de_credito_de_la_venta(self):
        venta = self.vender([(self.bota_m, 1, 'Rojo')])
        resumen, respuesta = self.cambiar(venta, self.datos_cambio(self.item(venta, self.bota_m, 'Rojo'), 1, self.remera_m, '', 2))
        self.assertEqual((resumen['resumen']['diferencia'], resumen['resumen']['resultado']), ('-3000.00', 'nota_credito'))
        nota = NotaCredito.objects.get()
        self.assertEqual((nota.venta_local_id, nota.pedido_id, nota.monto, nota.estado), (venta.id, None, Decimal('3000.00'), 'vigente'))
        self.assertEqual(Cambio.objects.get().diferencia, Decimal('-3000.00'))
        venta.refresh_from_db()
        self.assertEqual((venta.total, venta.saldo_pendiente, venta.estado_pago), (Decimal('5000.00'), Decimal('0.00'), 'PAGADO'))
        self.assertEqual(self.stock(self.remera_m), 0)
        self.assertIn('Se generó una nota de crédito por $3.000', respuesta.json()['mensaje'])

    def test_los_precios_del_navegador_se_ignoran(self):
        venta = self.vender([(self.remera_l, 1, None)])
        datos = self.datos_cambio(
            self.item(venta, self.remera_l), 1, self.bota_m, 'Rojo', 1,
            precio_entregado='1', precio_devuelto='99999', diferencia='-99999', precio='1',
        )
        _, respuesta = self.cambiar(venta, datos)
        self.assertTrue(respuesta.json()['success'])
        cambio = Cambio.objects.get()
        self.assertEqual((cambio.precio_devuelto, cambio.precio_entregado, cambio.diferencia),
                         (Decimal('1000.00'), Decimal('5000.00'), Decimal('4000.00')))
        self.assertFalse(NotaCredito.objects.exists())

    def test_un_producto_de_otra_venta_no_se_puede_cambiar(self):
        venta = self.vender([(self.remera_l, 1, None)])
        otra = self.vender([(self.bota_m, 1, 'Rojo')])
        datos = self.datos_cambio(self.item(otra, self.bota_m, 'Rojo'), 1, self.remera_m, '', 1)
        _, respuesta = self.cambiar_esperando_error(venta, datos)
        self.assertIn('producto de esta venta', respuesta.json()['error'])
        self.assertFalse(Cambio.objects.exists())
        self.assertEqual((self.stock(self.bota_m_rojo), self.stock(self.remera_m)), (1, 2))

    def cambiar_esperando_error(self, venta, datos):
        revision = self.revisar(venta, datos)
        self.assertEqual(revision.status_code, 400)
        respuesta = self.enviar(venta.id, dict(datos, confirmar=True, operacion_id='b' * 32))
        self.assertEqual(respuesta.status_code, 400)
        return revision, respuesta

    def test_datos_invalidos_se_rechazan_en_el_servidor(self):
        venta = self.vender([(self.bota_m, 1, 'Rojo')])
        item = self.item(venta, self.bota_m, 'Rojo')
        casos = [
            self.datos_cambio(item, 0, self.remera_m, '', 1),
            self.datos_cambio(item, 'abc', self.remera_m, '', 1),
            self.datos_cambio(item, 1, self.remera_m, '', -1),
            self.datos_cambio(item, 1, self.bota_m, 'Violeta', 1),   # color que no existe
            self.datos_cambio(item, 1, self.bota_m, '', 1),          # talle con colores sin color
            dict(self.datos_cambio(item, 1, self.remera_m, '', 1), variante_entregada='999999|'),
            dict(self.datos_cambio(item, 1, self.remera_m, '', 1), item_id='x'),
        ]
        for datos in casos:
            with self.subTest(datos=datos):
                self.cambiar_esperando_error(venta, datos)
        self.assertEqual(self.enviar(venta.id, ['no', 'es', 'un', 'objeto']).status_code, 400)
        self.assertFalse(Cambio.objects.exists())
        self.assertEqual((self.stock(self.bota_m_rojo), self.stock(self.remera_m)), (1, 2))

    def test_confirmar_sin_revisar_se_rechaza(self):
        venta = self.vender([(self.remera_l, 1, None)])
        datos = self.datos_cambio(self.item(venta, self.remera_l), 1, self.remera_m, '', 1, confirmar=True)
        self.assertEqual(self.enviar(venta.id, datos).status_code, 400)
        self.assertEqual(self.enviar(venta.id, dict(datos, operacion_id='<script>')).status_code, 400)
        self.assertFalse(Cambio.objects.exists())

    def test_venta_inexistente_responde_404(self):
        self.assertEqual(self.enviar(999999, {'item_id': 1}).status_code, 404)
        self.assertEqual(self.admin_client.get(self.url(999999)).status_code, 404)

    def test_solo_un_administrador_puede_registrar_cambios(self):
        venta = self.vender([(self.remera_l, 1, None)])
        datos = self.datos_cambio(self.item(venta, self.remera_l), 1, self.remera_m, '', 1)
        clienta = self.cliente_logueado(self.cliente_a)
        self.assertEqual(self.enviar(venta.id, dict(datos, confirmar=True, operacion_id='c' * 32), clienta).status_code, 302)
        from django.test import Client
        anonimo = Client()
        respuesta = anonimo.post(self.url(venta.id), json.dumps(datos), content_type='application/json')
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn('/users/login/', respuesta['Location'])
        self.assertFalse(Cambio.objects.exists())
        self.assertEqual(self.stock(self.remera_m), 2)

    def test_la_misma_confirmacion_repetida_registra_un_solo_cambio(self):
        venta = self.vender([(self.remera_l, 2, None)])
        datos = self.datos_cambio(self.item(venta, self.remera_l), 1, self.remera_m, '', 1)
        _, primera = self.cambiar(venta, datos)
        operacion_id = Cambio.objects.get().operacion_id
        segunda = self.enviar(venta.id, dict(datos, confirmar=True, operacion_id=operacion_id))
        self.assertTrue(segunda.json()['success'])
        self.assertTrue(segunda.json()['duplicado'])
        self.assertEqual(Cambio.objects.count(), 1)
        self.assertEqual((self.stock(self.remera_l), self.stock(self.remera_m)), (2, 1))
        # La misma operación no se puede usar en otra venta
        otra = self.vender([(self.remera_l, 1, None)])
        datos_otra = self.datos_cambio(self.item(otra, self.remera_l), 1, self.remera_m, '', 1)
        self.assertEqual(self.enviar(otra.id, dict(datos_otra, confirmar=True, operacion_id=operacion_id)).status_code, 400)
        self.assertEqual(Cambio.objects.count(), 1)

    def test_un_error_al_guardar_no_deja_cambios_parciales_de_stock(self):
        venta = self.vender([(self.bota_m, 1, 'Rojo')])
        datos = self.datos_cambio(self.item(venta, self.bota_m, 'Rojo'), 1, self.remera_m, '', 1)
        revision = self.revisar(venta, datos).json()
        for error in (IntegrityError('falla'), ValueError('No se pudo guardar.')):
            with self.subTest(error=type(error).__name__), \
                    mock.patch('pedidos.views.Cambio.objects.create', side_effect=error):
                respuesta = self.enviar(venta.id, dict(datos, confirmar=True, operacion_id=revision['operacion_id']))
            self.assertEqual(respuesta.status_code, 400)
            self.assertEqual((self.stock(self.bota_m_rojo), self.stock(self.remera_m)), (1, 2))
            self.assertFalse(NotaCredito.objects.exists())
            self.assertFalse(Cambio.objects.exists())

    def test_el_detalle_muestra_el_historial_y_las_notas_de_credito(self):
        venta = self.vender([(self.bota_m, 1, 'Rojo')])
        self.cambiar(venta, self.datos_cambio(self.item(venta, self.bota_m, 'Rojo'), 1, self.remera_m, '', 1, motivo='Le quedó grande'))
        detalle = self.admin_client.get(reverse('pedidos:detalle_venta_local', args=[venta.id])).json()
        self.assertEqual(detalle['cambio_url'], self.url(venta.id))
        cambio = detalle['cambios'][0]
        self.assertEqual(cambio['devuelto'], 'Bota · Talle M · Rojo')
        self.assertEqual(cambio['entregado'], 'Remera · Talle M')
        self.assertEqual((cambio['cantidad_devuelta'], cambio['cantidad_entregada'], cambio['diferencia']), (1, 1, -4000.0))
        self.assertEqual(cambio['motivo'], 'Le quedó grande')
        self.assertEqual(cambio['usuario'], self.admin.username)
        self.assertEqual(detalle['notas_credito'][0]['monto'], 4000.0)
        self.assertEqual(detalle['notas_credito'][0]['estado'], 'Vigente')

    def test_opciones_de_reemplazo_solo_con_stock(self):
        venta = self.vender([(self.bota_m, 1, 'Azul')])
        valores = [v['valor'] for v in self.admin_client.get(self.url(venta.id)).json()['variantes']]
        self.assertIn(f'{self.bota_m.id}|Rojo', valores)
        self.assertNotIn(f'{self.bota_m.id}|Azul', valores)  # se vendió el último
        self.assertIn(f'{self.remera_m.id}|', valores)


class VentasLocalesSiguenIgualTests(CambioVentaLocalMixin, TestCase):
    def setUp(self):
        self.preparar()

    def test_el_detalle_conserva_sus_datos(self):
        venta = self.vender([(self.bota_m, 1, 'Rojo'), (self.remera_l, 2, None)])
        detalle = self.admin_client.get(reverse('pedidos:detalle_venta_local', args=[venta.id])).json()
        for clave in ('cliente', 'fecha', 'total', 'pagado', 'pendiente', 'estado', 'metodo_pago', 'ticket_cambio_url', 'productos'):
            self.assertIn(clave, detalle)
        self.assertEqual(detalle['total'], 7000.0)
        self.assertEqual(sorted(p['cambiables'] for p in detalle['productos']), [1, 2])
        self.assertEqual((detalle['cambios'], detalle['notas_credito']), ([], []))

    def test_imprimir_el_ticket_de_cambio_no_registra_un_cambio(self):
        venta = self.vender([(self.remera_l, 1, None)])
        respuesta = self.admin_client.get(reverse('pedidos:ticket_cambio_venta_local', args=[venta.id]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Cambio.objects.exists())
        self.assertEqual(self.stock(self.remera_l), 2)

    def test_la_pantalla_de_ventas_presenciales_carga(self):
        self.vender([(self.remera_l, 1, None)])
        respuesta = self.admin_client.get(reverse('pedidos:ventas_presenciales'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'abrirFormularioCambio')


class CambioPedidoOnlineSigueIgualTests(CambioVentaLocalMixin, TestCase):
    def setUp(self):
        self.preparar()

    def pedido_aceptado(self, lineas):
        self.comprar(self.cliente_a, lineas)
        pedido = Pedido.objects.get(cliente=self.cliente_a)
        self.admin_client.post(reverse('pedidos:actualizar_estado_pedido', args=[pedido.id]), {'estado': 'aceptado'})
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'aceptado')
        return pedido

    def test_el_cambio_online_funciona_como_antes(self):
        pedido = self.pedido_aceptado([(self.bota_m, 1, 'Rojo')])
        self.assertEqual(self.stock(self.bota_m_rojo), 1)
        item = pedido.items.get()
        self.admin_client.post(reverse('pedidos:registrar_cambio', args=[pedido.id]), {
            'item_devuelto': item.id, 'variante_entregada': f'{self.remera_m.id}|', 'motivo': 'Talle',
        })
        cambio = Cambio.objects.get()
        self.assertEqual((cambio.pedido_id, cambio.venta_local_id), (pedido.id, None))
        self.assertEqual((cambio.cantidad_devuelta, cambio.cantidad_entregada), (1, 1))
        self.assertIsNone(cambio.diferencia)  # los campos nuevos no se usan en los cambios online
        self.assertEqual((self.stock(self.bota_m_rojo), self.stock(self.remera_m)), (2, 1))
        nota = NotaCredito.objects.get()
        self.assertEqual((nota.pedido_id, nota.venta_local_id, nota.monto), (pedido.id, None, Decimal('4000.00')))

    def test_los_cambios_de_un_circuito_no_cuentan_en_el_otro(self):
        pedido = self.pedido_aceptado([(self.remera_l, 1, None)])
        venta = self.vender([(self.remera_l, 1, None)])
        self.cambiar(venta, self.datos_cambio(self.item(venta, self.remera_l), 1, self.remera_m, '', 1))
        detalle = self.admin_client.get(reverse('pedidos:detalle_pedido', args=[pedido.id]))
        self.assertEqual(detalle.context['items_cambiables'][0][1], 1)
        self.admin_client.post(reverse('pedidos:registrar_cambio', args=[pedido.id]), {
            'item_devuelto': pedido.items.get().id, 'variante_entregada': f'{self.remera_m.id}|',
        })
        self.assertEqual(Cambio.objects.filter(pedido=pedido).count(), 1)
        detalle_venta = self.admin_client.get(reverse('pedidos:detalle_venta_local', args=[venta.id])).json()
        self.assertEqual(detalle_venta['productos'][0]['cambiables'], 0)
        self.assertEqual(len(detalle_venta['cambios']), 1)


@skipUnless(connection.vendor == 'postgresql', 'La concurrencia real se prueba con PostgreSQL (SQLite no bloquea filas).')
class CambioVentaLocalConcurrenciaTests(CambioVentaLocalMixin, TransactionTestCase):
    def setUp(self):
        self.preparar()

    def test_dos_confirmaciones_simultaneas_de_la_misma_operacion(self):
        venta = self.vender([(self.remera_l, 2, None)])
        datos = self.datos_cambio(self.item(venta, self.remera_l), 1, self.remera_m, '', 1)
        confirmar = dict(datos, confirmar=True, operacion_id=self.revisar(venta, datos).json()['operacion_id'])
        admin_1, admin_2 = self.admin_logueado(), self.admin_logueado()
        with con_demora():
            respuestas, errores = en_paralelo(
                lambda: self.enviar(venta.id, confirmar, admin_1),
                lambda: self.enviar(venta.id, confirmar, admin_2),
            )
        self.assertEqual(errores, [None, None])
        self.assertEqual(sorted(bool(r.json().get('duplicado')) for r in respuestas), [False, True])
        self.assertEqual(Cambio.objects.count(), 1)
        self.assertEqual((self.stock(self.remera_l), self.stock(self.remera_m)), (2, 1))

    def test_dos_cambios_simultaneos_de_la_ultima_unidad_comprada(self):
        venta = self.vender([(self.remera_l, 1, None)])
        datos = self.datos_cambio(self.item(venta, self.remera_l), 1, self.remera_m, '', 1)
        primera = dict(datos, confirmar=True, operacion_id=self.revisar(venta, datos).json()['operacion_id'])
        segunda = dict(datos, confirmar=True, operacion_id=self.revisar(venta, datos).json()['operacion_id'])
        admin_1, admin_2 = self.admin_logueado(), self.admin_logueado()
        with con_demora():
            respuestas, errores = en_paralelo(
                lambda: self.enviar(venta.id, primera, admin_1),
                lambda: self.enviar(venta.id, segunda, admin_2),
            )
        self.assertEqual(errores, [None, None])
        self.assertEqual(sorted(r.status_code for r in respuestas), [200, 400])
        self.assertEqual(Cambio.objects.count(), 1)
        self.assertEqual((self.stock(self.remera_l), self.stock(self.remera_m)), (3, 1))
