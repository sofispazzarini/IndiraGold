"""Verifica páginas reales renderizadas con Django en Chrome headless.

Ejecutar desde la raíz: python tests/verificar_promociones_responsive.py
Requiere Playwright y Chrome instalado (o INDIRA_CHROME con la ruta al ejecutable).
Usa SQLite en memoria, no inicia un servidor ni modifica la base local.
"""
import json
import mimetypes
import os
from pathlib import Path
import sys
import tempfile
from decimal import Decimal

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
os.environ['DB_ENGINE'] = 'django.db.backends.sqlite3'
os.environ['DB_NAME'] = ':memory:'
os.environ['MERCADO_PAGO_ACCESS_TOKEN'] = 'TEST-pruebas-responsive'

import django
django.setup()
from django.conf import settings
settings.ALLOWED_HOSTS = ['testserver', 'indira.test']
settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
from django.core.management import call_command
from django.contrib.staticfiles import finders
from django.test import Client
from django.urls import reverse
from pedidos.tests import DatosStockMixin
from pedidos.models import ConfiguracionPago
from productos.models import CategoriaOrden, CategoriaOrdenProducto, Oferta
from playwright.sync_api import sync_playwright

call_command('migrate', verbosity=0, interactive=False)
datos = DatosStockMixin()
datos.crear_datos()
datos.talle_l.nombre = 'S'
datos.talle_l.save(update_fields=['nombre'])
datos.remera.precio = Decimal('50000.00')
datos.remera.save()
datos.remera_m.precio = Decimal('123.00')
datos.remera_m.save(update_fields=['precio'])
for nombre in ['Destacados', 'Novedades']:
    seccion = CategoriaOrden.objects.create(nombre=nombre)
    CategoriaOrdenProducto.objects.create(categoria_orden=seccion, producto=datos.remera)
    CategoriaOrdenProducto.objects.create(categoria_orden=seccion, producto=datos.bota)
Oferta.objects.create(nombre='Oferta', descuento=10, aplicar_a_todos=True)
config = ConfiguracionPago.actual()
cliente = Client()
detalle_url = reverse('productos:detalle_producto', args=[datos.remera.pk])
resultados = []
capturas = Path(tempfile.mkdtemp(prefix='indiragold_promociones_'))
casos = []
for transferencia, efectivo in [(10, 15), (10, 0), (0, 15), (0, 0)]:
    config.descuento_transferencia_porcentaje = transferencia
    config.descuento_efectivo_porcentaje = efectivo
    config.save()
    casos.append((transferencia, efectivo, {
        '/': cliente.get('/').content.decode(),
        detalle_url: cliente.get(detalle_url).content.decode(),
    }))
chrome = os.environ.get('INDIRA_CHROME', r'C:\Program Files\Google\Chrome\Application\chrome.exe')

with sync_playwright() as pw:
    navegador = pw.chromium.launch(executable_path=chrome, headless=True)
    pagina = navegador.new_page()
    errores = []
    pagina.on('pageerror', lambda error: errores.append(str(error)))
    pagina.add_init_script("sessionStorage.setItem('welcomeModalShown', 'true')")
    paginas = {}
    def servir(route):
        from urllib.parse import urlsplit
        url = urlsplit(route.request.url)
        if url.netloc != 'indira.test':
            route.abort()
        elif url.path.startswith('/static/'):
            archivo = finders.find(url.path[len('/static/'):])
            if archivo:
                route.fulfill(body=Path(archivo).read_bytes(), content_type=mimetypes.guess_type(archivo)[0] or 'application/octet-stream')
            else:
                route.fulfill(status=404)
        else:
            route.fulfill(body=paginas.get(url.path, ''), content_type='text/html')
    pagina.route('**/*', servir)
    for transferencia, efectivo, paginas in casos:
        for ancho in [320, 375, 414, 768, 1024, 1440]:
            pagina.set_viewport_size({'width': ancho, 'height': 1000})
            for ruta in ['/', detalle_url]:
                pagina.goto('http://indira.test' + ruta, wait_until='load')
                pagina.wait_for_timeout(100)
                cantidad = int(transferencia > 0) + int(efectivo > 0)
                if ruta == '/':
                    # El modal usa los mismos checkboxes y el filtro OR del catálogo.
                    pagina.evaluate('mostrarWelcome()')
                    modal = pagina.locator('#welcomeModal')
                    talle_m = modal.locator(f'[data-talle-id="{datos.talle_m.pk}"]')
                    talle_s = modal.locator(f'[data-talle-id="{datos.talle_l.pk}"]')
                    talle_m.click()
                    assert modal.is_visible()
                    assert talle_m.get_attribute('aria-pressed') == 'true'
                    talle_s.click()
                    assert talle_m.get_attribute('aria-pressed') == 'true'
                    assert talle_s.get_attribute('aria-pressed') == 'true'
                    assert pagina.locator('#talleFilter input:checked').count() == 2
                    assert pagina.locator('#productsGrid .product-card:visible').count() == 2
                    talle_m.click()
                    assert talle_m.get_attribute('aria-pressed') == 'false'
                    assert talle_s.get_attribute('aria-pressed') == 'true'
                    assert pagina.locator('#productsGrid .product-card:visible').count() == 1
                    talle_m.click()
                    assert modal.evaluate('(el) => el.scrollWidth <= el.clientWidth')
                    assert modal.locator('.welcome-modal').evaluate('(el) => el.scrollWidth <= el.clientWidth')
                    if transferencia == 10 and efectivo == 15 and ancho in [320, 1440]:
                        modal.locator('.welcome-modal').screenshot(path=str(capturas / f'{ancho}_bienvenida.png'))
                    modal.get_by_role('button', name='Ver productos', exact=True).click()
                    assert not modal.is_visible()
                    pagina.locator('#talleFilter summary').click()
                    pagina.locator(f'#talleFilter input[value="{datos.talle_m.pk}"]').uncheck()
                    pagina.keyboard.press('Escape')
                    pagina.evaluate('mostrarWelcome()')
                    assert talle_m.get_attribute('aria-pressed') == 'false'
                    assert talle_s.get_attribute('aria-pressed') == 'true'
                    modal.get_by_role('button', name='Ver todo el catálogo', exact=True).click()
                    assert pagina.locator('#talleFilter input:checked').count() == 0
                    assert pagina.locator('#productsGrid .product-card:visible').count() == 2
                    pagina.evaluate('mostrarWelcome()')
                    modal.get_by_role('button', name='Ver productos', exact=True).click()
                    assert pagina.locator('#productsGrid .product-card:visible').count() == 2
                    # Elegir o limpiar talles no modifica categoría, color ni búsqueda.
                    pagina.locator('#searchInput').fill('Remera')
                    pagina.evaluate("""([categoria, color]) => {
                        filterCat(document.querySelectorAll('.cat-pill')[1], categoria);
                        selectColor(color, 'Rojo', '#ff0000');
                        mostrarWelcome();
                    }""", [str(datos.categoria.pk), str(datos.rojo.pk)])
                    talle_s.click()
                    modal.get_by_role('button', name='Ver productos', exact=True).click()
                    assert pagina.evaluate('[activeCategory, selectedColor, searchTerm]') == [str(datos.categoria.pk), str(datos.rojo.pk), 'remera']
                    pagina.evaluate('mostrarWelcome()')
                    modal.get_by_role('button', name='Ver todo el catálogo', exact=True).click()
                    assert pagina.evaluate('[activeCategory, selectedColor, searchTerm]') == [str(datos.categoria.pk), str(datos.rojo.pk), 'remera']
                    pagina.evaluate('limpiarFiltros()')
                    assert pagina.locator('.product-card').count() == 8
                    if cantidad:
                        assert pagina.locator('.product-card .descuentos-pago').count() == 8
                    pagina.locator('#searchInput').fill('Remera')
                    assert pagina.locator('#productsGrid .product-card:visible').count() == 1
                    if cantidad:
                        assert pagina.locator('#productsGrid .product-card:visible .descuentos-pago__oferta').count() == cantidad
                    pagina.get_by_role('button', name='Limpiar filtros', exact=True).click()
                    assert pagina.locator('#productsGrid .product-card:visible').count() == 2
                    pagina.locator('#talleFilter summary').click()
                    pagina.locator(f'#talleFilter input[value="{datos.talle_m.pk}"]').check()
                    pagina.locator(f'#talleFilter input[value="{datos.talle_l.pk}"]').check()
                    assert pagina.locator('#productsGrid .product-card:visible').count() == 2
                    pagina.keyboard.press('Escape')
                    pagina.locator('#productsGrid .product-card__btn').first.click()
                    assert pagina.locator('#modalCantidad').is_visible()
                    pagina.keyboard.press('Escape')
                else:
                    assert pagina.locator('.descuentos-pago--detalle .descuentos-pago__oferta').count() == cantidad
                    if cantidad:
                        assert pagina.locator('.descuentos-pago--detalle').bounding_box()['y'] < pagina.locator('#btnAgregarCarrito').bounding_box()['y']
                    # Cambiar talle no toma la copia vieja del precio de Variante.
                    talles = pagina.locator('.variantes-section .talle-btn')
                    for i in range(talles.count()):
                        talles.nth(i).click()
                        if transferencia:
                            assert '$40.500' in pagina.locator('.descuentos-pago--detalle').inner_text()
                if transferencia == 10 and efectivo == 15 and ancho in [320, 1440]:
                    objetivo = pagina.locator('#productsGrid .product-card').first if ruta == '/' else pagina.locator('.detalle-info')
                    objetivo.screenshot(path=str(capturas / f'{ancho}_{"catalogo" if ruta == "/" else "detalle"}.png'))
                assert 'Precio orientativo sin envío' not in pagina.locator('body').inner_text()
                assert pagina.locator('.descuentos-pago__nota').count() == 0
                problemas = pagina.evaluate("""() => {
                    const errores = [];
                    if (document.documentElement.scrollWidth > innerWidth + 1) errores.push('desborde de página');
                    for (const el of document.querySelectorAll('.descuentos-pago, .descuentos-pago__oferta, .descuentos-pago__precio')) {
                        if (!el.getClientRects().length) continue;
                        if (el.scrollWidth > el.clientWidth + 1) errores.push('desborde en ' + el.className);
                        const padre = el.closest('.product-card, .relacionado-card, .detalle-info');
                        if (padre) {
                            const a = el.getBoundingClientRect(), b = padre.getBoundingClientRect();
                            if (a.left < b.left - 1 || a.right > b.right + 1) errores.push('promoción fuera de tarjeta');
                        }
                    }
                    const botones = [...document.querySelectorAll('#productsGrid .product-card__footer')].filter(e=>e.getClientRects().length);
                    for (let i=1; i<botones.length; i++) {
                        const a=botones[i-1].closest('.product-card').getBoundingClientRect(), b=botones[i].closest('.product-card').getBoundingClientRect();
                        if (Math.abs(a.top-b.top)<1 && Math.abs(a.bottom-b.bottom)>1) errores.push('tarjetas desalineadas');
                    }
                    return errores;
                }""")
                assert not problemas, (ancho, ruta, transferencia, efectivo, problemas)
                assert not errores, errores
                resultados.append({'ancho': ancho, 'pagina': ruta, 'transferencia': transferencia, 'efectivo': efectivo})
    navegador.close()
print(json.dumps({'verificaciones_responsive': len(resultados), 'errores': errores, 'capturas': str(capturas)}, ensure_ascii=False))
