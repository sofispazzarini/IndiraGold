"""El aviso de "falta un color con stock" del formulario de productos es parte de la página (no un alert
del navegador). El comportamiento en pantalla se revisa en el navegador; acá se verifica el markup."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from productos.models import Categoria, Subcategoria


class AvisoColoresVarianteTests(TestCase):
    def test_el_formulario_usa_el_aviso_integrado(self):
        admin = User.objects.create_superuser(username='99999999', password='x', email='admin@example.test')
        self.client.force_login(admin)
        subcategoria = Subcategoria.objects.create(nombre='Remeras', categoria=Categoria.objects.create(nombre='Ropa'))
        respuesta = self.client.get(reverse('productos:agregar_producto', args=[subcategoria.id]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'id="avisoColoresVariante"')
        self.assertContains(respuesta, 'id="seccionColoresVariante"')
        self.assertContains(respuesta, 'mostrarAvisoColores(talle)')
        self.assertNotContains(respuesta, "alert('Sumá al menos un color con stock")
