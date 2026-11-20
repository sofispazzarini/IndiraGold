from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from pedidos.models import ConfiguracionPago, OpcionEnvioFlex, Pedido, VentaLocal
from pedidos.tests import DatosStockMixin
from users.models import Direccion


class DescuentosVentaLocalTests(DatosStockMixin, TestCase):
    def setUp(self):
        self.crear_datos()
        self.admin_client = self.admin_logueado()
        self.configuracion, _ = ConfiguracionPago.objects.update_or_create(pk=1, defaults={
            'descuento_efectivo_porcentaje': 5,
            'descuento_transferencia_porcentaje': 10,
            'transferencia_activa': True,
        })

    def registrar(self, metodo_pago, **datos):
        return self.admin_client.post(reverse('pedidos:registrar_venta_local'), {
            'cliente_id': self.cliente_a.user_id,
            'metodo_pago': metodo_pago,
            'productos': [{'variante_id': self.bota_m.id, 'cantidad': 1, 'color': 'Rojo'}],
            **datos,
        }, content_type='application/json')

    def venta(self, respuesta):
        self.assertTrue(respuesta.json()['success'], respuesta.json())
        return VentaLocal.objects.get(pk=respuesta.json()['venta_id'])

    def test_transferencia_guarda_descuento_y_cobra_total_neto(self):
        self.bota.precio = Decimal('50000.00')
        self.bota.save(update_fields=['precio'])
        pagina = self.admin_client.get(reverse('pedidos:ventas_presenciales'))
        self.assertEqual(pagina.context['descuentos_venta_local'], {
            'efectivo': 5, 'transferencia': 10, 'mercado_pago': 0, 'tarjeta': 0,
        })

        venta = self.venta(self.registrar('transferencia', total_previsualizado='45000'))
        self.assertEqual(venta.items.get().subtotal, Decimal('50000.00'))
        self.assertEqual(venta.descuento_pago_porcentaje, Decimal('10.00'))
        self.assertEqual(venta.descuento_pago_monto, Decimal('5000.00'))
        self.assertEqual(venta.total, Decimal('45000.00'))
        self.assertEqual(venta.monto_pagado, venta.total)
        self.assertEqual(venta.pagos.get().monto, venta.total)
        self.assertEqual(self.stock(self.bota_m_rojo), 1)

        self.configuracion.descuento_transferencia_porcentaje = 30
        self.configuracion.save(update_fields=['descuento_transferencia_porcentaje'])
        detalle = self.admin_client.get(reverse('pedidos:detalle_venta_local', args=[venta.pk])).json()
        self.assertEqual((detalle['total'], detalle['descuento_pago_monto'], detalle['descuento_pago_porcentaje']),
                         (45000, 5000, 10))

    def test_efectivo_descuenta_productos_y_envio_antes_de_validar_deuda(self):
        direccion = Direccion.objects.create(
            cliente=self.cliente_a, calle='Calle', numero='1', ciudad='La Plata',
            provincia='Buenos Aires', codigo_postal='1900',
        )
        opcion = OpcionEnvioFlex.objects.create(nombre='Flex', precio=1000)
        envio = {'metodo_entrega': 'envio', 'direccion_id': direccion.pk, 'opcion_flex_id': opcion.pk}

        respuesta = self.registrar('efectivo', nueva_deuda='5800', **envio)
        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(VentaLocal.objects.exists())
        self.assertEqual(self.stock(self.bota_m_rojo), 2)

        venta = self.venta(self.registrar('efectivo', nueva_deuda='700', total_previsualizado='5700', **envio))
        self.assertEqual(venta.costo_envio, Decimal('1000.00'))
        self.assertEqual(venta.descuento_pago_monto, Decimal('300.00'))
        self.assertEqual(venta.total, Decimal('5700.00'))
        self.assertEqual(venta.saldo_pendiente, Decimal('700.00'))
        self.assertEqual(venta.monto_pagado, Decimal('5000.00'))

    def test_sin_promocion_o_transferencia_desactivada_cobra_el_original(self):
        self.configuracion.transferencia_activa = False
        self.configuracion.save(update_fields=['transferencia_activa'])
        for metodo in ('tarjeta', 'transferencia'):
            with self.subTest(metodo=metodo):
                venta = self.venta(self.registrar(metodo, total_previsualizado='5000'))
                self.assertEqual(venta.total, Decimal('5000.00'))
                self.assertEqual(venta.descuento_pago_porcentaje, 0)
                self.assertEqual(venta.descuento_pago_monto, 0)

    def test_total_previsualizado_desactualizado_no_registra_la_venta(self):
        respuesta = self.registrar('transferencia', total_previsualizado='4750')
        self.assertEqual(respuesta.status_code, 409)
        self.assertFalse(VentaLocal.objects.exists())
        self.assertEqual(self.stock(self.bota_m_rojo), 2)

    def test_estadisticas_usan_descuentos_historicos_y_cobros_guardados(self):
        self.venta(self.registrar('transferencia', nueva_deuda='1000'))  # 5.000 - 500 = 4.500, cobrado 3.500
        VentaLocal.objects.create(cliente=self.cliente_a, total=1000, monto_pagado=1000, metodo_pago='transferencia')

        pedido = self.crear_pedido(self.cliente_b, [(self.bota_m, 1, 'Azul')], estado='aceptado')
        Pedido.objects.filter(pk=pedido.pk).update(
            total=4320, monto_pagado=4320, deuda=0,
            descuento_monto=200, descuento_pago_porcentaje=10, descuento_pago_monto=480,
        )
        pendiente = self.crear_pedido(self.cliente_b, [(self.remera_m, 1, None)])
        Pedido.objects.filter(pk=pendiente.pk).update(total=900, descuento_pago_monto=100)
        fuera_de_periodo = self.venta(self.registrar('efectivo'))
        VentaLocal.objects.filter(pk=fuera_de_periodo.pk).update(created_at=timezone.now() - timedelta(days=7))
        ConfiguracionPago.objects.filter(pk=1).update(descuento_transferencia_porcentaje=25)

        hoy = timezone.localdate().isoformat()
        respuesta = self.admin_client.get(reverse('pedidos:estadisticas_ventas'), {
            'tipo_periodo': 'personalizado', 'fecha_inicio': hoy, 'fecha_fin': hoy,
        })
        self.assertContains(respuesta, 'Descuentos por medio de pago')
        contexto = respuesta.context
        self.assertEqual(contexto['total_original'], Decimal('11000.00'))
        self.assertEqual(contexto['total_descuentos'], Decimal('1180.00'))
        self.assertEqual(contexto['total_cupones'], Decimal('200.00'))
        self.assertEqual(contexto['total_vendido'], Decimal('9820.00'))
        self.assertEqual(contexto['ingresos_brutos'], Decimal('8820.00'))
        self.assertEqual(contexto['neto_negocio'], contexto['ingresos_brutos'])
        self.assertEqual(contexto['evolucion_diaria'][0]['total'], contexto['ingresos_brutos'])
        self.assertEqual(contexto['evolucion_diaria'][0]['cantidad'], 3)
        self.assertEqual(contexto['descuentos_por_medio'], [{
            'medio': 'Transferencia', 'online': Decimal('480.00'), 'local': Decimal('500.00'),
            'total': Decimal('980.00'),
        }])
        self.assertEqual({fila['tipo_venta']: (fila['total'], fila['cobrado']) for fila in contexto['ventas_por_tipo']}, {
            'online': (Decimal('4320.00'), Decimal('4320.00')),
            'venta_local': (Decimal('5500.00'), Decimal('4500.00')),
        })
