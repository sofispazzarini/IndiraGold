"""Descuentos sobre productos + envío, permisos, persistencia y precios publicados."""
from decimal import Decimal
import json
from pathlib import Path
import shutil
import subprocess
from unittest import skipUnless
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from pedidos.descuentos import calcular_totales, porcentaje_pago
from pedidos.models import ConfiguracionEnvio, ConfiguracionPago, OpcionEnvioFlex, Pedido
from users.models import Direccion
from pedidos.tests import DatosStockMixin
from productos.models import CategoriaOrden, CategoriaOrdenProducto, Oferta


class CalculoDescuentosTests(SimpleTestCase):
    def test_ejemplos_incluyen_envio(self):
        self.assertEqual(calcular_totales(50000, 8000, 10), {
            'porcentaje': Decimal('10'), 'descuento': Decimal('5800.00'), 'total': Decimal('52200.00')})
        self.assertEqual(calcular_totales(50000, 8000, 15)['total'], Decimal('49300.00'))

    def test_cero_cien_y_envio_gratis(self):
        self.assertEqual(calcular_totales(50000, 8000, 0)['total'], Decimal('58000.00'))
        self.assertEqual(calcular_totales(50000, 8000, 100)['total'], Decimal('0.00'))
        self.assertEqual(calcular_totales(50000, 0, 15)['total'], Decimal('42500.00'))

    def test_redondeo_decimal_al_centavo(self):
        self.assertEqual(calcular_totales('0.05', 0, 10)['descuento'], Decimal('0.01'))
        self.assertEqual(calcular_totales('123.45', '6.78', '12.34')['total'], Decimal('114.16'))

    def test_cupon_se_aplica_antes_del_descuento_pago(self):
        self.assertEqual(calcular_totales(50000, 8000, 10, 5000)['total'], Decimal('47700.00'))

    def test_medio_distinto_no_hereda_porcentaje(self):
        config = ConfiguracionPago(descuento_transferencia_porcentaje=10, descuento_efectivo_porcentaje=15)
        self.assertEqual(porcentaje_pago(config, 'transferencia'), 10)
        self.assertEqual(porcentaje_pago(config, 'efectivo'), 15)
        self.assertEqual(porcentaje_pago(config, 'mercado_pago'), 0)
        self.assertEqual(porcentaje_pago(config, 'mercado_pago_qr'), 0)
        config.transferencia_activa = False
        self.assertEqual(porcentaje_pago(config, 'transferencia'), 0)

    @skipUnless(shutil.which('node'), 'Requiere Node para comparar frontend y backend')
    def test_frontend_y_backend_coinciden_en_importes_y_redondeo(self):
        casos = [[s, e, p, c] for s in ['0.05', '1.05', '123.45', '50000']
                 for e in ['0', '6.78', '8000'] for p in ['0', '10', '12.34', '15', '100']
                 for c in ['0', '0.01', '20']]
        script = "const f = require('./pedidos/static/pedidos/descuentos_pago.js');let s='';process.stdin.on('data',d=>s+=d);process.stdin.on('end',()=>process.stdout.write(JSON.stringify(JSON.parse(s).map(c=>f.calcular(...c)))));"
        resultado = subprocess.run([shutil.which('node'), '-e', script], input=json.dumps(casos),
                                   text=True, capture_output=True, check=True, cwd=Path(__file__).resolve().parent.parent)
        for caso, frontend in zip(casos, json.loads(resultado.stdout)):
            with self.subTest(caso=caso):
                backend = calcular_totales(*caso)
                self.assertEqual(Decimal(str(frontend['total'])), backend['total'])
                self.assertEqual(Decimal(str(frontend['descuento'])), backend['descuento'])

    def test_porcentajes_invalidos(self):
        for porcentaje in ['-0.01', '100.01', 'NaN', 'Infinity']:
            with self.subTest(porcentaje=porcentaje), self.assertRaises(ValueError):
                calcular_totales(50000, 8000, porcentaje)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class CheckoutDescuentosTests(DatosStockMixin, TestCase):
    def setUp(self):
        self.crear_datos()
        self.remera.precio = Decimal('50000.00')
        self.remera.save()
        self.config = ConfiguracionPago.actual()
        self.config.descuento_transferencia_porcentaje = Decimal('10.00')
        self.config.descuento_efectivo_porcentaje = Decimal('15.00')
        self.config.save()
        patcher = mock.patch('pedidos.views.enviar_email_confirmacion_pedido')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_transferencia_guarda_descuento_total_y_deuda(self):
        self.comprar(self.cliente_a, [(self.remera_m, 1, None)])
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.descuento_pago_porcentaje, Decimal('10.00'))
        self.assertEqual(pedido.descuento_pago_monto, Decimal('5000.00'))
        self.assertEqual(pedido.total, Decimal('45000.00'))
        self.assertEqual(pedido.deuda, pedido.total)
        self.assertEqual(pedido.descuento_monto, 0)

    def test_efectivo_usa_su_porcentaje_sin_sumar_transferencia(self):
        self.comprar(self.cliente_a, [(self.remera_m, 1, None)], 'efectivo')
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.descuento_pago_porcentaje, 15)
        self.assertEqual(pedido.total, Decimal('42500.00'))

    def test_configuracion_cero_desactiva(self):
        self.config.descuento_transferencia_porcentaje = 0
        self.config.save()
        self.comprar(self.cliente_a, [(self.remera_m, 1, None)])
        self.assertEqual(Pedido.objects.get().total, Decimal('50000.00'))

    def test_transferencia_correo_descuenta_sobre_envio_del_servidor(self):
        envio = ConfiguracionEnvio.actual()
        envio.correo_activo = True
        envio.save()
        self.llenar_carrito(self.cliente_a, [(self.remera_m, 1, None)])
        cliente = self.cliente_logueado(self.cliente_a)
        with mock.patch('pedidos.views.costo_correo_argentino_desde_sesion', return_value=(Decimal('8000'), 'Clásico')):
            respuesta = cliente.post(reverse('pedidos:crear_pago'), {
                'metodo_entrega': 'correo', 'metodo_pago': 'transferencia',
                'correo': 'correo_argentino', 'tipo_correo': 'sucursal',
                'sucursal_correo': 'La Plata', 'codigo_postal_sucursal': '1900',
                'costo_envio': '1', 'total': '1', 'descuento_pago_porcentaje': '99',
            })
        self.assertEqual(respuesta.status_code, 302)
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.costo_envio, Decimal('8000.00'))
        self.assertEqual(pedido.descuento_pago_monto, Decimal('5800.00'))
        self.assertEqual(pedido.total, Decimal('52200.00'))

    def test_transferencia_flex_pago_y_gratis(self):
        direccion = Direccion.objects.create(cliente=self.cliente_a, calle='Calle', numero='1', ciudad='La Plata',
                                              provincia='Buenos Aires', codigo_postal='1900')
        opcion = OpcionEnvioFlex.objects.create(nombre='Flex', precio=8000)
        for gratis, esperado in [(False, Decimal('52200.00')), (True, Decimal('45000.00'))]:
            with self.subTest(gratis=gratis):
                opcion.es_gratis = gratis
                opcion.save()
                self.llenar_carrito(self.cliente_a, [(self.remera_m, 1, None)])
                self.cliente_logueado(self.cliente_a).post(reverse('pedidos:crear_pago'), {
                    'metodo_entrega': 'flex', 'metodo_pago': 'transferencia',
                    'direccion_id': direccion.pk, 'opcion_flex_id': opcion.pk})
                pedido = Pedido.objects.latest('pk')
                self.assertEqual(pedido.total, esperado)
                self.assertEqual(pedido.descuento_pago_porcentaje, 10)

    def test_cien_por_ciento_crea_pedido_gratuito_sin_cambiar_flujo(self):
        self.config.descuento_transferencia_porcentaje = 100
        self.config.save()
        self.comprar(self.cliente_a, [(self.remera_m, 1, None)])
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.total, Decimal('0.00'))
        self.assertEqual(pedido.descuento_pago_monto, Decimal('50000.00'))
        self.assertEqual(pedido.estado, 'pendiente')

    def test_editar_pedido_usa_porcentaje_historico(self):
        self.comprar(self.cliente_a, [(self.remera_m, 1, None)])
        pedido = Pedido.objects.get()
        self.config.descuento_transferencia_porcentaje = 50
        self.config.save()
        self.admin_logueado().post(reverse('pedidos:editar_pedido', args=[pedido.pk]), {})
        pedido.refresh_from_db()
        self.assertEqual(pedido.total, Decimal('45000.00'))
        self.assertEqual(pedido.descuento_pago_porcentaje, 10)
        self.assertEqual(pedido.descuento_pago_monto, Decimal('5000.00'))

    def test_efectivo_con_envio_sigue_sin_permitirse(self):
        self.llenar_carrito(self.cliente_a, [(self.remera_m, 1, None)])
        self.cliente_logueado(self.cliente_a).post(reverse('pedidos:crear_pago'), {
            'metodo_entrega': 'correo', 'metodo_pago': 'efectivo'})
        self.assertFalse(Pedido.objects.exists())

    def test_cupon_y_pago_conservan_importes_separados(self):
        Oferta.objects.create(nombre='Cupón', descuento=10, codigo='PROMO', es_cupon=True)
        cliente = self.cliente_logueado(self.cliente_a)
        sesion = cliente.session
        sesion['codigo_descuento'] = 'PROMO'
        sesion.save()
        self.comprar(self.cliente_a, [(self.remera_m, 1, None)], client=cliente)
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.descuento_monto, Decimal('5000.00'))
        self.assertEqual(pedido.descuento_pago_monto, Decimal('4500.00'))
        self.assertEqual(pedido.total, Decimal('40500.00'))

    def test_historial_conserva_total_al_cambiar_configuracion_y_aceptar(self):
        self.comprar(self.cliente_a, [(self.remera_m, 1, None)])
        pedido = Pedido.objects.get()
        self.config.descuento_transferencia_porcentaje = 50
        self.config.save()
        self.admin_logueado().post(reverse('pedidos:actualizar_estado_pedido', args=[pedido.id]), {'estado': 'aceptado'})
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, 'aceptado')
        self.assertEqual((pedido.total, pedido.descuento_pago_porcentaje, pedido.descuento_pago_monto),
                         (Decimal('45000.00'), Decimal('10.00'), Decimal('5000.00')))
        self.assertEqual(self.stock(self.remera_m), 1)
        respuesta = self.admin_logueado().get(reverse('pedidos:detalle_pedido', args=[pedido.id]))
        self.assertContains(respuesta, 'Descuento por Transferencia bancaria (10%)')

    def test_mercado_pago_sin_descuento_y_preferencia_igual_al_pedido(self):
        sdk = self.mock_mercado_pago()
        with mock.patch('pedidos.views.sdk', sdk):
            self.comprar(self.cliente_a, [(self.remera_m, 1, None)], 'mercado_pago')
        pedido = Pedido.objects.get()
        datos = sdk.preference.return_value.create.call_args.args[0]
        importe = sum(Decimal(str(item['unit_price'])) * item['quantity'] for item in datos['items'])
        self.assertEqual(importe, pedido.total)
        self.assertEqual(pedido.total, Decimal('50000.00'))
        self.assertEqual(pedido.descuento_pago_monto, 0)

    def test_mp_con_cupon_redondeado_por_unidad_coincide_con_total(self):
        self.remera.precio = Decimal('1.05')
        self.remera.save()
        Oferta.objects.create(nombre='Cupón', descuento=10, codigo='CENTAVOS', es_cupon=True)
        cliente = self.cliente_logueado(self.cliente_a)
        sesion = cliente.session
        sesion['codigo_descuento'] = 'CENTAVOS'
        sesion.save()
        sdk = self.mock_mercado_pago()
        with mock.patch('pedidos.views.sdk', sdk):
            self.comprar(self.cliente_a, [(self.remera_m, 2, None)], 'mercado_pago', client=cliente)
        pedido = Pedido.objects.get()
        datos = sdk.preference.return_value.create.call_args.args[0]
        self.assertEqual(sum(Decimal(str(i['unit_price'])) * i['quantity'] for i in datos['items']), pedido.total)

    def datos_config(self, transferencia='10', efectivo='15'):
        return {'mercado_pago_activo': 'on', 'transferencia_activa': 'on',
                'titular_cuenta': self.config.titular_cuenta, 'cuit_cuil': self.config.cuit_cuil,
                'cvu': self.config.cvu, 'alias': self.config.alias,
                'texto_mercado_pago': self.config.texto_mercado_pago, 'texto_transferencia': self.config.texto_transferencia,
                'retencion_tarjeta_porcentaje': '0', 'retencion_mercado_pago_presencial_porcentaje': '0',
                'descuento_transferencia_porcentaje': transferencia, 'descuento_efectivo_porcentaje': efectivo}

    def test_admin_guarda_porcentajes_independientes_y_mensaje(self):
        respuesta = self.admin_logueado().post(reverse('pedidos:configurar_pagos'), self.datos_config('12.50', '0'), follow=True)
        self.assertContains(respuesta, 'Configuracion de pagos actualizada.')
        self.config.refresh_from_db()
        self.assertEqual(self.config.descuento_transferencia_porcentaje, Decimal('12.50'))
        self.assertEqual(self.config.descuento_efectivo_porcentaje, 0)

    def test_admin_rechaza_porcentajes_invalidos_sin_guardar(self):
        for valor in ['-1', '100.01', 'NaN', 'Infinity', 'abc']:
            with self.subTest(valor=valor):
                respuesta = self.admin_logueado().post(reverse('pedidos:configurar_pagos'), self.datos_config(valor))
                self.assertEqual(respuesta.status_code, 200)
                self.assertTrue(respuesta.context['form'].errors)
                self.config.refresh_from_db()
                self.assertEqual(self.config.descuento_transferencia_porcentaje, Decimal('10.00'))

    def test_cliente_y_anonimo_no_modifican_configuracion(self):
        for cliente in [self.client, self.cliente_logueado(self.cliente_a)]:
            respuesta = cliente.post(reverse('pedidos:configurar_pagos'), self.datos_config('80', '80'))
            self.assertEqual(respuesta.status_code, 302)
        self.config.refresh_from_db()
        self.assertEqual(self.config.descuento_transferencia_porcentaje, Decimal('10.00'))

    def test_validadores_del_modelo(self):
        self.config.descuento_efectivo_porcentaje = Decimal('100.01')
        with self.assertRaises(ValidationError):
            self.config.full_clean()

    def test_catalogo_y_detalle_muestran_precios_por_medio(self):
        for url in [reverse('home:home'), reverse('productos:detalle_producto', args=[self.remera.id])]:
            respuesta = self.client.get(url)
            self.assertContains(respuesta, '10% OFF abonando con transferencia')
            self.assertContains(respuesta, '15% OFF abonando en efectivo')
            self.assertContains(respuesta, '$45.000')
            self.assertContains(respuesta, '$42.500')
            self.assertNotContains(respuesta, 'Precio orientativo sin envío')
            self.assertNotContains(respuesta, 'descuentos-pago__nota')

    def test_cero_no_publica_descuentos_y_transferencia_inactiva_no_se_anuncia(self):
        self.config.transferencia_activa = False
        self.config.descuento_efectivo_porcentaje = 0
        self.config.save()
        respuesta = self.client.get(reverse('home:home'))
        self.assertNotContains(respuesta, 'OFF abonando')

    def test_checkout_expone_porcentajes_y_resumen(self):
        self.llenar_carrito(self.cliente_a, [(self.remera_m, 1, None)])
        respuesta = self.cliente_logueado(self.cliente_a).get(reverse('pedidos:checkout'))
        self.assertContains(respuesta, 'transferencia: 10.00')
        self.assertContains(respuesta, 'efectivo: 15.00')
        self.assertContains(respuesta, 'id="descuento-pago-row"')

    def test_catalogo_solo_publica_talles_activos_con_stock(self):
        self.remera_l.stock = 0
        self.remera_l.save(update_fields=['stock'])
        respuesta = self.client.get(reverse('home:home'))
        producto = next(p for p in respuesta.context['productos'] if p.pk == self.remera.pk)
        self.assertEqual(producto.talles_con_stock, str(self.talle_m.pk))
        self.assertContains(respuesta, 'type="checkbox" name="talles"')
        self.assertContains(respuesta, 'Limpiar talles')
        self.assertContains(respuesta, 'Limpiar filtros')


    def test_todas_las_tarjetas_incluyen_promociones_compartidas(self):
        for nombre in ['Destacados', 'Novedades']:
            seccion = CategoriaOrden.objects.create(nombre=nombre)
            CategoriaOrdenProducto.objects.create(categoria_orden=seccion, producto=self.remera)
        Oferta.objects.create(nombre='Oferta', descuento=10, aplicar_a_todos=True)
        respuesta = self.client.get(reverse('home:home'))
        html = respuesta.content.decode()
        tarjetas = html.count('class="product-card"')
        self.assertGreaterEqual(tarjetas, 6)
        self.assertEqual(html.count('aria-label="Descuentos por método de pago"'), tarjetas)
        self.assertEqual(html.count('10% OFF abonando con transferencia'), tarjetas)
        self.assertEqual(html.count('15% OFF abonando en efectivo'), tarjetas)

    def test_un_solo_descuento_y_ninguno_en_ambas_paginas(self):
        for transferencia, efectivo in [(10, 0), (0, 15), (0, 0)]:
            self.config.descuento_transferencia_porcentaje = transferencia
            self.config.descuento_efectivo_porcentaje = efectivo
            self.config.save()
            for url in [reverse('home:home'), reverse('productos:detalle_producto', args=[self.remera.pk])]:
                with self.subTest(transferencia=transferencia, efectivo=efectivo, url=url):
                    respuesta = self.client.get(url)
                    html = respuesta.content.decode()
                    self.assertEqual('OFF abonando con transferencia' in html, transferencia > 0)
                    self.assertEqual('OFF abonando en efectivo' in html, efectivo > 0)
                    self.assertEqual('aria-label="Descuentos por método de pago"' in html, bool(transferencia or efectivo))

    def test_porcentajes_actualizados_se_reflejan_al_recargar(self):
        urls = [reverse('home:home'), reverse('productos:detalle_producto', args=[self.remera.pk])]
        for url in urls:
            self.assertContains(self.client.get(url), '$45.000')
        self.config.descuento_transferencia_porcentaje = 20
        self.config.save()
        for url in urls:
            respuesta = self.client.get(url)
            self.assertContains(respuesta, '20% OFF abonando con transferencia')
            self.assertContains(respuesta, '$40.000')
            self.assertNotContains(respuesta, '10% OFF abonando con transferencia')

    def test_variantes_con_copia_antigua_no_alteran_el_precio_cobrado(self):
        from carritos.utils import precio_unitario_vigente
        self.remera_m.precio = Decimal('123.00')
        self.remera_m.save(update_fields=['precio'])
        for variante in [self.remera_m, self.remera_l]:
            self.assertEqual(precio_unitario_vigente(variante), Decimal('50000.00'))
        respuesta = self.client.get(reverse('productos:detalle_producto', args=[self.remera.pk]))
        self.assertContains(respuesta, '$45.000')
        self.assertContains(respuesta, 'Promociones disponibles')
        self.assertNotContains(respuesta, '$110,70')

    def test_descuento_publicado_respeta_oferta_y_precio_original(self):
        oferta = Oferta.objects.create(nombre='Oferta', descuento=20)
        oferta.productos.add(self.remera)
        for url in [reverse('home:home'), reverse('productos:detalle_producto', args=[self.remera.pk])]:
            respuesta = self.client.get(url)
            self.assertContains(respuesta, '$50.000')
            self.assertContains(respuesta, '$36.000')
            self.assertContains(respuesta, '$34.000')
