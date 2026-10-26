"""Costos de cobro: desglose de los pagos de Mercado Pago según la API, retenciones estimadas de los
cobros en el local (Posnet y Mercado Pago), pagos parciales, estadísticas y comando de diagnóstico.

Todos los importes y porcentajes de estas pruebas son ilustrativos (inventados para probar los
cálculos): no son tarifas reales de Mercado Pago ni de ningún Posnet. La API de Mercado Pago se simula."""
import json
from datetime import date
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from pedidos.costos_cobro import desglose_pago_mercado_pago, retencion_cobro_presencial
from pedidos.models import ConfiguracionPago, Gasto, NotaCredito, Pago, PagoVentaLocal, Pedido, VentaLocal
from pedidos.tests import DatosStockMixin


def respuesta_api(bruto, tipo, cuotas=1, cargos=(), neto=None, **extra):
    """Respuesta de GET /v1/payments/{id} con la forma documentada (neto dentro de transaction_details)."""
    detalle = {
        'status': 'approved',
        'transaction_amount': bruto,
        'payment_type_id': tipo,
        'installments': cuotas,
        'fee_details': [{'type': tipo_cargo, 'fee_payer': pagador, 'amount': importe} for tipo_cargo, pagador, importe in cargos],
    }
    if neto is not None:
        detalle['transaction_details'] = {'net_received_amount': neto}
    detalle.update(extra)
    return detalle


def d(valor):
    return None if valor is None else Decimal(valor)


class DesgloseMercadoPagoTests(SimpleTestCase):
    def assertDesglose(self, detalle, costos, cargos, neto, otros, bruto='10000.00'):
        desglose = desglose_pago_mercado_pago(detalle)
        self.assertEqual(
            (desglose['bruto'], desglose['costos_comercio'], desglose['cargos_cliente'], desglose['neto'], desglose['otros_descuentos']),
            (d(bruto), d(costos), d(cargos), d(neto), d(otros)),
        )
        return desglose

    def test_dinero_en_cuenta_tiene_costo(self):
        detalle = respuesta_api(10000, 'account_money', cargos=[('mercadopago_fee', 'collector', 96.8)], neto=9903.2)
        self.assertDesglose(detalle, '96.80', '0.00', '9903.20', '0.00')

    def test_debito(self):
        detalle = respuesta_api(10000, 'debit_card', cargos=[('mercadopago_fee', 'collector', 150)], neto=9850)
        self.assertDesglose(detalle, '150.00', '0.00', '9850.00', '0.00')

    def test_credito_en_un_pago(self):
        detalle = respuesta_api(10000, 'credit_card', cargos=[('mercadopago_fee', 'collector', 700)], neto=9300)
        self.assertDesglose(detalle, '700.00', '0.00', '9300.00', '0.00')

    def test_cuotas_sin_interes_las_paga_el_comercio(self):
        detalle = respuesta_api(10000, 'credit_card', cuotas=6, neto=7241, cargos=[
            ('mercadopago_fee', 'collector', 700), ('financing_fee', 'collector', 2059),
        ])
        self.assertDesglose(detalle, '2759.00', '0.00', '7241.00', '0.00')

    def test_cuotas_con_interes_el_interes_lo_paga_la_clienta(self):
        detalle = respuesta_api(10000, 'credit_card', cuotas=3, neto=9300, cargos=[
            ('mercadopago_fee', 'collector', 700), ('financing_fee', 'payer', 1500),
        ])
        # Antes se sumaban los dos (2.200) como costo del comercio
        self.assertDesglose(detalle, '700.00', '1500.00', '9300.00', '0.00')

    def test_descuentos_que_solo_se_ven_en_el_neto(self):
        detalle = respuesta_api(10000, 'credit_card', cargos=[('mercadopago_fee', 'collector', 700)], neto=9200)
        desglose = self.assertDesglose(detalle, '700.00', '0.00', '9200.00', '100.00')
        # Sin doble descuento: costos + otros = bruto - neto
        self.assertEqual(desglose['costos_comercio'] + desglose['otros_descuentos'], desglose['bruto'] - desglose['neto'])

    def test_sin_neto_queda_desconocido(self):
        detalle = respuesta_api(10000, 'account_money', cargos=[('mercadopago_fee', 'collector', 96.8)])
        self.assertDesglose(detalle, '96.80', '0.00', None, None)

    def test_respuesta_vieja_con_el_neto_fuera_de_lugar_no_inventa_importes(self):
        detalle = {'status': 'approved', 'transaction_amount': 10000, 'payment_type_id': 'account_money',
                   'net_received_amount': 10000}
        self.assertDesglose(detalle, None, None, None, None)

    def test_un_cargo_sin_pagador_deja_los_costos_desconocidos(self):
        detalle = respuesta_api(10000, 'credit_card', cargos=[('mercadopago_fee', None, 700)], neto=9300)
        # Se conoce el total descontado (bruto - neto) pero no a quién corresponde
        self.assertDesglose(detalle, None, None, '9300.00', '700.00')

    def test_respuesta_vacia(self):
        self.assertDesglose({}, None, None, None, None, bruto=None)
        self.assertDesglose(None, None, None, None, None, bruto=None)


class PagoOnlineGuardaLosCostosTests(DatosStockMixin, TestCase):
    def setUp(self):
        self.crear_datos()

    def pagar(self, detalle_sin_referencia, payment_id='900'):
        sdk = self.mock_mercado_pago()
        with mock.patch('pedidos.views.sdk', sdk):
            self.comprar(self.cliente_a, [(self.bota_m, 2, 'Rojo')], metodo_pago='mercado_pago')
        referencia = sdk.preference.return_value.create.call_args[0][0]['external_reference']
        detalle = dict(detalle_sin_referencia, external_reference=referencia)
        sdk_pago = mock.MagicMock()
        sdk_pago.payment.return_value.get.return_value = {'status': 200, 'response': detalle}
        client = self.cliente_logueado(self.cliente_a)
        with mock.patch('pedidos.views.sdk', sdk_pago):
            client.get(reverse('pedidos:pago_exitoso'), {'payment_id': payment_id})
            client.get(reverse('pedidos:pago_exitoso'), {'payment_id': payment_id})  # retorno repetido
        return Pago.objects.get()

    def test_dinero_en_cuenta_guarda_costos_y_neto_de_la_api(self):
        pago = self.pagar(respuesta_api(10000, 'account_money', cargos=[('mercadopago_fee', 'collector', 96.8)], neto=9853.2))
        self.assertEqual(
            (pago.retencion_mercado_pago, pago.neto_recibido, pago.cargos_cliente_mercado_pago, pago.otros_descuentos_mercado_pago),
            (Decimal('96.80'), Decimal('9853.20'), Decimal('0.00'), Decimal('50.00')),
        )
        self.assertEqual(Pago.objects.count(), 1)

    def test_respuesta_incompleta_queda_desconocida(self):
        pago = self.pagar({'status': 'approved', 'transaction_amount': 10000, 'payment_type_id': 'account_money'})
        self.assertEqual(Pedido.objects.get().estado, 'aceptado')
        self.assertIsNone(pago.retencion_mercado_pago)
        self.assertIsNone(pago.neto_recibido)
        self.assertIsNone(pago.otros_descuentos_mercado_pago)


class CobrosEnElLocalTests(DatosStockMixin, TestCase):
    def setUp(self):
        self.crear_datos()
        self.admin_client = self.admin_logueado()
        ConfiguracionPago.objects.update_or_create(pk=1, defaults={
            'retencion_tarjeta_porcentaje': Decimal('5'),
            'retencion_mercado_pago_presencial_porcentaje': Decimal('2'),
        })

    def vender(self, metodo_pago, deuda='0', productos=None):
        datos = {
            'cliente_id': self.cliente_a.user_id, 'metodo_pago': metodo_pago, 'metodo_entrega': 'local', 'nueva_deuda': deuda,
            'productos': productos or [{'variante_id': self.bota_m.id, 'cantidad': 2, 'color': 'Rojo'}],  # $10.000
        }
        respuesta = self.admin_client.post(reverse('pedidos:registrar_venta_local'), json.dumps(datos), content_type='application/json')
        self.assertTrue(respuesta.json()['success'], respuesta.json())
        return VentaLocal.objects.get(pk=respuesta.json()['venta_id'])

    def cobrar(self, venta, monto, metodo_pago=None):
        datos = {'monto': monto}
        if metodo_pago is not None:
            datos['metodo_pago'] = metodo_pago
        return self.admin_client.post(reverse('pedidos:registrar_pago_venta', args=[venta.id]), json.dumps(datos), content_type='application/json')

    def test_tarjeta_usa_el_porcentaje_de_posnet(self):
        venta = self.vender('tarjeta')
        self.assertEqual(venta.retencion, Decimal('500.00'))
        self.assertEqual(list(venta.pagos.values_list('metodo_pago', 'monto', 'retencion')), [('tarjeta', Decimal('10000.00'), Decimal('500.00'))])

    def test_mercado_pago_en_el_local_no_usa_el_porcentaje_de_posnet(self):
        venta = self.vender('mercado_pago')
        self.assertEqual(venta.retencion, Decimal('200.00'))
        ConfiguracionPago.objects.filter(pk=1).update(retencion_mercado_pago_presencial_porcentaje=0)
        otra = self.vender('mercado_pago', productos=[{'variante_id': self.remera_l.id, 'cantidad': 3, 'color': ''}])
        self.assertEqual((otra.monto_pagado, otra.retencion), (Decimal('3000.00'), Decimal('0.00')))

    def test_efectivo_no_tiene_retencion(self):
        self.assertEqual(self.vender('efectivo').retencion, Decimal('0.00'))

    def test_transferencia_se_registra_sin_retencion(self):
        venta = self.vender('transferencia', deuda='4000')
        self.assertEqual((venta.metodo_pago, venta.retencion), ('transferencia', Decimal('0.00')))
        self.assertTrue(self.cobrar(venta, '1000', 'transferencia').json()['success'])
        venta.refresh_from_db()
        self.assertEqual(venta.retencion, Decimal('0.00'))
        self.assertEqual(list(venta.pagos.values_list('metodo_pago', flat=True).distinct()), ['transferencia'])

    def test_venta_parcial_y_cobros_posteriores_con_su_medio(self):
        venta = self.vender('tarjeta', deuda='4000')
        self.assertEqual((venta.monto_pagado, venta.saldo_pendiente, venta.retencion), (Decimal('6000.00'), Decimal('4000.00'), Decimal('300.00')))

        self.assertTrue(self.cobrar(venta, '1000', 'mercado_pago').json()['success'])
        self.assertTrue(self.cobrar(venta, '1000', 'efectivo').json()['success'])
        self.assertTrue(self.cobrar(venta, '1000').json()['success'])  # sin medio: el de la venta (tarjeta)
        venta.refresh_from_db()
        self.assertEqual(venta.retencion, Decimal('300.00') + Decimal('20.00') + Decimal('0.00') + Decimal('50.00'))
        self.assertEqual(
            list(venta.pagos.order_by('id').values_list('metodo_pago', 'retencion')),
            [('tarjeta', Decimal('300.00')), ('mercado_pago', Decimal('20.00')), ('efectivo', Decimal('0.00')), ('tarjeta', Decimal('50.00'))],
        )
        self.assertEqual((venta.saldo_pendiente, venta.estado_pago), (Decimal('1000.00'), 'PARCIAL'))

    def test_cobros_rechazados_no_suman_retencion(self):
        venta = self.vender('tarjeta', deuda='4000')
        self.assertEqual(self.cobrar(venta, '1000', 'cheque').status_code, 400)
        self.assertEqual(self.cobrar(venta, '5000', 'tarjeta').status_code, 400)   # más que el saldo
        self.assertTrue(self.cobrar(venta, '4000', 'tarjeta').json()['success'])
        self.assertEqual(self.cobrar(venta, '4000', 'tarjeta').status_code, 400)   # ya no hay saldo
        venta.refresh_from_db()
        self.assertEqual((venta.retencion, venta.pagos.count()), (Decimal('500.00'), 2))

    def test_retencion_estimada_redondea_a_centavos(self):
        configuracion = ConfiguracionPago(retencion_tarjeta_porcentaje=Decimal('3.33'))
        self.assertEqual(retencion_cobro_presencial(Decimal('1000.55'), 'tarjeta', configuracion), Decimal('33.32'))
        self.assertEqual(retencion_cobro_presencial(Decimal('0'), 'tarjeta', configuracion), Decimal('0.00'))


class EstadisticasNetoNegocioTests(DatosStockMixin, TestCase):
    def setUp(self):
        self.crear_datos()
        self.admin_client = self.admin_logueado()
        ConfiguracionPago.objects.update_or_create(pk=1, defaults={'retencion_tarjeta_porcentaje': Decimal('5')})

    def contexto(self):
        return self.admin_client.get(reverse('pedidos:estadisticas_ventas'), {'tipo_periodo': 'hoy'}).context

    def test_neto_negocio_parte_de_lo_cobrado_y_no_descuenta_dos_veces(self):
        # Pedido online cobrado con Mercado Pago: costos 700 + otros descuentos 100 (neto 9.200)
        pedido = self.crear_pedido(self.cliente_a, [(self.bota_m, 2, 'Rojo')], estado='aceptado')
        Pedido.objects.filter(pk=pedido.pk).update(monto_pagado=Decimal('10000.00'), deuda=0)
        Pago.objects.create(
            pedido=pedido, metodo='Mercado Pago', monto=Decimal('10000.00'), retencion_mercado_pago=Decimal('700.00'),
            neto_recibido=Decimal('9200.00'), otros_descuentos_mercado_pago=Decimal('100.00'),
        )
        # Pedido cobrado sin datos de costos de la API
        otro = self.crear_pedido(self.cliente_b, [(self.remera_m, 1, None)], estado='aceptado')
        Pedido.objects.filter(pk=otro.pk).update(monto_pagado=Decimal('1000.00'), deuda=0)
        Pago.objects.create(pedido=otro, metodo='Mercado Pago', monto=Decimal('1000.00'), retencion_mercado_pago=None, neto_recibido=None)
        # Venta del local con tarjeta: total 5.000, cobrado 3.000 (retención 150), debe 2.000
        datos = {'cliente_id': self.cliente_a.user_id, 'metodo_pago': 'tarjeta', 'metodo_entrega': 'local', 'nueva_deuda': '2000',
                 'productos': [{'variante_id': self.bota_m.id, 'cantidad': 1, 'color': 'Azul'}]}
        venta_id = self.admin_client.post(reverse('pedidos:registrar_venta_local'), json.dumps(datos), content_type='application/json').json()['venta_id']
        NotaCredito.objects.create(venta_local_id=venta_id, monto=Decimal('500.00'))
        NotaCredito.objects.create(pedido=pedido, monto=Decimal('300.00'))
        NotaCredito.objects.create(pedido=pedido, monto=Decimal('999.00'), estado='anulada')
        Gasto.objects.create(descripcion='Bolsas', monto=Decimal('1000.00'), fecha=date.today())

        contexto = self.contexto()
        self.assertEqual(contexto['ingresos_brutos'], Decimal('14000.00'))      # 10.000 + 1.000 + 3.000 cobrados
        self.assertEqual(contexto['total_notas_credito'], Decimal('800.00'))    # 500 del local + 300 del pedido
        self.assertEqual(contexto['total_retenciones'], Decimal('950.00'))      # 700 + 100 + 150
        self.assertEqual(contexto['pagos_sin_costos'], 1)
        self.assertEqual(contexto['total_deudas'], Decimal('2000.00'))          # el saldo de la venta del local
        self.assertEqual(contexto['neto_negocio'], Decimal('14000.00') - Decimal('800.00') - Decimal('1000.00') - Decimal('950.00'))
        self.assertEqual(contexto['total_con_deudas'], Decimal('10000.00') + Decimal('1000.00') + Decimal('5000.00') - Decimal('800.00'))

    def test_pagos_anteriores_siguen_sumando_lo_guardado(self):
        pedido = self.crear_pedido(self.cliente_a, [(self.remera_m, 1, None)], estado='aceptado')
        Pedido.objects.filter(pk=pedido.pk).update(monto_pagado=Decimal('1000.00'), deuda=0)
        # Pago guardado con la versión anterior: retención y neto calculados entonces, sin "otros"
        Pago.objects.create(pedido=pedido, metodo='Mercado Pago', monto=Decimal('1000.00'),
                            retencion_mercado_pago=Decimal('80.00'), neto_recibido=Decimal('920.00'))
        contexto = self.contexto()
        self.assertEqual((contexto['total_retenciones'], contexto['pagos_sin_costos']), (Decimal('80.00'), 0))


class ConfiguracionYDiagnosticoTests(DatosStockMixin, TestCase):
    def setUp(self):
        self.crear_datos()
        self.admin_client = self.admin_logueado()

    def test_la_configuracion_guarda_el_porcentaje_de_mercado_pago_en_el_local(self):
        respuesta = self.admin_client.get(reverse('pedidos:configurar_pagos'))
        self.assertContains(respuesta, 'Costo estimado (informativo)')
        self.assertContains(respuesta, 'retencion_mercado_pago_presencial_porcentaje')
        datos = {
            'mercado_pago_activo': 'on', 'transferencia_activa': 'on', 'titular_cuenta': 'Titular', 'cuit_cuil': '20-1-1',
            'cvu': '0', 'alias': 'alias', 'texto_mercado_pago': 'MP', 'texto_transferencia': 'TR',
            'retencion_tarjeta_porcentaje': '4.5', 'retencion_mercado_pago_presencial_porcentaje': '2,25',
            'cuotas[]': ['3'], 'retencion_porcentaje[]': ['10'], 'activo[]': ['0'],
        }
        self.assertEqual(self.admin_client.post(reverse('pedidos:configurar_pagos'), datos).status_code, 302)
        configuracion = ConfiguracionPago.actual()
        self.assertEqual((configuracion.retencion_tarjeta_porcentaje, configuracion.retencion_mercado_pago_presencial_porcentaje),
                         (Decimal('4.50'), Decimal('2.25')))
        datos['retencion_mercado_pago_presencial_porcentaje'] = '120'
        self.assertEqual(self.admin_client.post(reverse('pedidos:configurar_pagos'), datos).status_code, 200)
        self.assertEqual(ConfiguracionPago.actual().retencion_mercado_pago_presencial_porcentaje, Decimal('2.25'))

    def test_el_comando_de_diagnostico_no_modifica_nada(self):
        pedido = self.crear_pedido(self.cliente_a, [(self.remera_m, 1, None)], estado='aceptado')
        detalle = respuesta_api(1000, 'account_money', cargos=[('mercadopago_fee', 'collector', 9.68)], neto=990.32)
        pago = Pago.objects.create(pedido=pedido, metodo='Mercado Pago', monto=Decimal('1000.00'),
                                   retencion_mercado_pago=Decimal('0.00'), neto_recibido=Decimal('1000.00'),
                                   detalle_mercado_pago=detalle)
        salida = StringIO()
        call_command('diagnosticar_costos_mercado_pago', stdout=salida)
        texto = salida.getvalue()
        self.assertIn(f'{pago.id};{pedido.id};', texto)
        self.assertIn(';0.00;9.68;1000.00;990.32;0.00;0.00;DIFERENCIA', texto)
        self.assertIn('No se modificó ningún dato.', texto)
        pago.refresh_from_db()
        self.assertEqual((pago.retencion_mercado_pago, pago.neto_recibido), (Decimal('0.00'), Decimal('1000.00')))
        self.assertNotIn('30000001', texto)  # sin datos personales
