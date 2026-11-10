from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings

from pedidos.tests import DatosStockMixin
from productos.imagenes import TAMANOS, generar_derivadas, nombre_derivada, url_imagen
from productos.models import ImagenProducto, Producto


class ImagenesProductoTests(DatosStockMixin, TestCase):
    def setUp(self):
        self.crear_datos()
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        override = override_settings(MEDIA_ROOT=temp.name)
        override.enable()
        self.addCleanup(override.disable)
        self.raiz = Path(temp.name)

    def archivo(self):
        salida = BytesIO()
        Image.new('RGBA', (2200, 1800), (220, 60, 110, 180)).save(salida, 'PNG')
        return SimpleUploadedFile('producto.png', salida.getvalue(), content_type='image/png')

    def test_alta_conserva_original_genera_tamanos_y_transparencia(self):
        original = self.archivo()
        contenido = original.read()
        original.seek(0)
        foto = ImagenProducto.objects.create(producto=self.remera, imagen=original)
        with foto.imagen.open('rb') as archivo:
            self.assertEqual(archivo.read(), contenido)
        for lado in TAMANOS:
            with foto.imagen.storage.open(nombre_derivada(foto.imagen, lado)) as archivo:
                imagen = Image.open(archivo)
                self.assertEqual(imagen.format, 'WEBP')
                self.assertLessEqual(max(imagen.size), lado)
                self.assertIn('A', imagen.getbands())
        self.assertEqual(generar_derivadas(foto.imagen), 0)
        self.assertIn('-480.webp', url_imagen(foto.imagen, 480))

    def test_comando_simula_por_defecto_y_aplica_sin_modificar_bd(self):
        with mock.patch('productos.imagenes.generar_derivadas'):
            foto = ImagenProducto.objects.create(producto=self.remera, imagen=self.archivo())
        archivos_antes = sorted(str(p) for p in self.raiz.rglob('*') if p.is_file())
        call_command('optimizar_imagenes_productos', stdout=StringIO())
        self.assertEqual(archivos_antes, sorted(str(p) for p in self.raiz.rglob('*') if p.is_file()))
        self.assertEqual(url_imagen(foto.imagen, 480), foto.imagen.url)
        call_command('optimizar_imagenes_productos', aplicar=True, stdout=StringIO())
        foto.refresh_from_db()
        self.assertEqual(foto.imagen.name, 'productos/producto.png')
        self.assertEqual(generar_derivadas(foto.imagen), 0)

    def test_error_de_optimizacion_no_pierde_alta_original(self):
        with mock.patch('productos.imagenes.generar_derivadas', side_effect=OSError('sin espacio')):
            with self.assertLogs('productos.models', level='ERROR'):
                foto = ImagenProducto.objects.create(producto=self.remera, imagen=self.archivo())
        self.assertTrue(foto.imagen.storage.exists(foto.imagen.name))
        self.assertEqual(url_imagen(foto.imagen), foto.imagen.url)

    def test_precarga_conserva_portada_stock_y_variantes_sin_consultas_repetidas(self):
        from home.views import variantes_json
        import json
        ImagenProducto.objects.create(producto=self.remera, imagen='productos/primera.jpg')
        portada = ImagenProducto.objects.create(producto=self.remera, imagen='productos/portada.jpg', es_portada=True)
        producto = Producto.objects.prefetch_related(
            'imagenes', 'variantes__talle', 'variantes__colores', 'variantes__variante_colores__color'
        ).get(pk=self.remera.pk)
        with self.assertNumQueries(0):
            for _ in range(3):
                self.assertEqual(producto.imagen.name, portada.imagen.name)
                self.assertEqual(producto.stock_total, 5)
                self.assertEqual(len(json.loads(variantes_json(producto))), 2)
