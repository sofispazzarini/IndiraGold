from django.test import TestCase

from productos.models import (
    Categoria,
    Color,
    Medida,
    Producto,
    Proveedor,
    Subcategoria,
    Talle,
    Variante,
    VarianteColor,
)
from productos.views import sincronizar_qrs_variante_color
from productos.views import producto_debe_regenerar_qr, variante_debe_regenerar_qr


class VarianteColorQRRegenerationTests(TestCase):
    def test_regenerar_qrs_al_cambiar_colores_de_variante(self):
        categoria = Categoria.objects.create(nombre='Ropa', activa=True)
        subcategoria = Subcategoria.objects.create(nombre='Prendas', categoria=categoria, activa=True)
        proveedor = Proveedor.objects.create(nombre='Proveedor Test', telefono='123456789')

        producto = Producto.objects.create(
            codigo='TEST-001',
            nombre='Camisa Test',
            tipo='Camiseta',
            tela='Algodón',
            descripcion='Desc',
            precio=100,
            stock=10,
            categoria=categoria,
            subcategoria=subcategoria,
            proveedor=proveedor,
        )
        talle = Talle.objects.create(nombre='M')
        variante = Variante.objects.create(
            producto=producto,
            talle=talle,
            stock=9,
            precio=100,
            qr_code='qr-antiguo',
        )

        color_rojo = Color.objects.create(nombre='Rojo', codigo_hex='#ff0000')
        color_azul = Color.objects.create(nombre='Azul', codigo_hex='#0000ff')

        VarianteColor.objects.create(variante=variante, color=color_rojo, qr_code='qr-rojo-viejo')
        VarianteColor.objects.create(variante=variante, color=color_azul, qr_code='qr-azul-viejo')

        variante.colores.set([color_rojo])

        sincronizar_qrs_variante_color(variante)

        self.assertEqual(VarianteColor.objects.filter(variante=variante).count(), 1)
        self.assertTrue(
            VarianteColor.objects.filter(variante=variante, color=color_rojo).exists()
        )
        self.assertFalse(
            VarianteColor.objects.filter(variante=variante, color=color_azul).exists()
        )

        color_actual = VarianteColor.objects.get(variante=variante, color=color_rojo)
        self.assertTrue(color_actual.qr_code)

    def test_forzar_regeneracion_de_qr_mantiene_los_mismos_colores_y_cambia_el_codigo(self):
        categoria = Categoria.objects.create(nombre='Ropa', activa=True)
        subcategoria = Subcategoria.objects.create(nombre='Prendas', categoria=categoria, activa=True)
        proveedor = Proveedor.objects.create(nombre='Proveedor Test', telefono='123456789')

        producto = Producto.objects.create(
            codigo='TEST-002',
            nombre='Pantalon Test',
            tipo='Pantalón',
            tela='Denim',
            descripcion='Desc',
            precio=200,
            stock=10,
            categoria=categoria,
            subcategoria=subcategoria,
            proveedor=proveedor,
        )
        talle = Talle.objects.create(nombre='L')
        variante = Variante.objects.create(
            producto=producto,
            talle=talle,
            stock=9,
            precio=200,
        )

        color_verde = Color.objects.create(nombre='Verde', codigo_hex='#00ff00')
        variante.colores.set([color_verde])

        sincronizar_qrs_variante_color(variante)
        qr_anterior = VarianteColor.objects.get(variante=variante, color=color_verde).qr_code

        sincronizar_qrs_variante_color(variante, regenerar_qr=True)
        qr_nuevo = VarianteColor.objects.get(variante=variante, color=color_verde).qr_code

        self.assertNotEqual(qr_anterior, qr_nuevo)
        self.assertTrue(qr_nuevo)

    def test_editar_variante_debe_regenerar_qr(self):
        categoria = Categoria.objects.create(nombre='Ropa', activa=True)
        subcategoria = Subcategoria.objects.create(nombre='Prendas', categoria=categoria, activa=True)
        proveedor = Proveedor.objects.create(nombre='Proveedor Test', telefono='123456789')

        producto = Producto.objects.create(
            codigo='TEST-003',
            nombre='Remera Test',
            tipo='Remera',
            tela='Algodón',
            descripcion='Desc',
            precio=150,
            stock=10,
            categoria=categoria,
            subcategoria=subcategoria,
            proveedor=proveedor,
        )
        talle = Talle.objects.create(nombre='S')
        variante = Variante.objects.create(
            producto=producto,
            talle=talle,
            stock=9,
            precio=150,
        )

        color_rojo = Color.objects.create(nombre='Rojo', codigo_hex='#ff0000')
        variante.colores.set([color_rojo])
        variante.medidas.set([
            Medida.objects.create(alto='10', ancho='20', largo='30', tiro='40')
        ])

        sincronizar_qrs_variante_color(variante)
        qr_anterior = VarianteColor.objects.get(variante=variante, color=color_rojo).qr_code

        variante.talle = Talle.objects.create(nombre='M')
        variante.save()
        variante.medidas.set([
            Medida.objects.create(alto='11', ancho='21', largo='31', tiro='41')
        ])
        sincronizar_qrs_variante_color(variante, regenerar_qr=True)

        qr_nuevo = VarianteColor.objects.get(variante=variante, color=color_rojo).qr_code
        self.assertNotEqual(qr_anterior, qr_nuevo)

    def test_los_cambios_solo_de_medidas_no_deben_regenerar_qr(self):
        categoria = Categoria.objects.create(nombre='Ropa', activa=True)
        subcategoria = Subcategoria.objects.create(nombre='Prendas', categoria=categoria, activa=True)
        proveedor = Proveedor.objects.create(nombre='Proveedor Test', telefono='123456789')

        producto = Producto.objects.create(
            codigo='TEST-004',
            nombre='Buzo Test',
            tipo='Buzo',
            tela='Frisa',
            descripcion='Desc',
            precio=250,
            stock=10,
            categoria=categoria,
            subcategoria=subcategoria,
            proveedor=proveedor,
        )
        talle = Talle.objects.create(nombre='XL')
        variante = Variante.objects.create(
            producto=producto,
            talle=talle,
            stock=9,
            precio=250,
        )
        color_negro = Color.objects.create(nombre='Negro', codigo_hex='#000000')
        variante.colores.set([color_negro])
        sincronizar_qrs_variante_color(variante)

        medidas_originales = [Medida.objects.create(alto='10', ancho='20', largo='30', tiro='40')]
        variante.medidas.set(medidas_originales)
        qr_anterior = VarianteColor.objects.get(variante=variante, color=color_negro).qr_code

        medidas_nuevas = [Medida.objects.create(alto='11', ancho='21', largo='31', tiro='41')]
        variante.medidas.set(medidas_nuevas)

        self.assertFalse(variante_debe_regenerar_qr(variante, variante.talle_id, [color_negro.id]))
        qr_nuevo = VarianteColor.objects.get(variante=variante, color=color_negro).qr_code
        self.assertEqual(qr_anterior, qr_nuevo)

    def test_cambio_de_codigo_de_producto_si_debe_regenerar_qr(self):
        self.assertTrue(producto_debe_regenerar_qr('ABC-1', 'ABC-2'))
        self.assertFalse(producto_debe_regenerar_qr('ABC-1', 'ABC-1'))
