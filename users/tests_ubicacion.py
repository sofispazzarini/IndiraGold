"""Registro: la cuenta se crea con la ubicación confirmada en el mapa (verificada automáticamente o
confirmada a mano por el usuario) y nunca sin ella."""
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from users.models import Direccion


class ConfirmarUbicacionRegistroTests(TestCase):
    def setUp(self):
        sesion = self.client.session
        sesion['registro_data'] = {
            'nombre': 'Ana', 'apellido': 'Pérez', 'email': 'ana@example.test', 'dni': '30111222',
            'telefono': '2215550000', 'etiqueta': 'Casa', 'calle': '423 bis', 'numero': '2150',
            # Localidad escrita a mano (no elegida de la lista): se guarda tal cual
            'ciudad': 'Villa Elisa', 'provincia': 'Buenos Aires', 'codigo_postal': '1894', 'referencia': '',
            'password_hash': make_password('ClaveSegura123'),
        }
        sesion['email_verificado'] = True
        sesion.save()
        self.url = reverse('users:confirmar_direccion')

    def confirmar(self, **datos):
        return self.client.post(self.url, datos)

    def test_sin_coordenadas_no_crea_la_cuenta(self):
        respuesta = self.confirmar()
        self.assertRedirects(respuesta, self.url, fetch_redirect_response=False)
        self.assertFalse(User.objects.filter(username='30111222').exists())
        self.assertContains(self.client.get(self.url), 'Confirmá la ubicación en el mapa')

    def test_manual_sin_marcar_la_confirmacion_no_crea_la_cuenta(self):
        self.confirmar(latitud='-34.865000', longitud='-58.084000', ubicacion_origen='manual')
        self.assertFalse(User.objects.filter(username='30111222').exists())

    def test_coordenadas_fuera_de_argentina_se_rechazan(self):
        self.confirmar(latitud='40.4', longitud='-3.7', ubicacion_origen='automatica')
        self.assertFalse(User.objects.filter(username='30111222').exists())

    def test_manual_confirmada_guarda_las_coordenadas_del_marcador(self):
        self.confirmar(latitud='-34.8651234', longitud='-58.0843758', ubicacion_origen='manual', confirmo_ubicacion='1')
        direccion = Direccion.objects.get(cliente__dni='30111222')
        self.assertEqual(direccion.latitud, Decimal('-34.865123'))
        self.assertEqual(direccion.longitud, Decimal('-58.084376'))
        self.assertEqual(direccion.ubicacion_origen, Direccion.UBICACION_MANUAL)
        # La calle se capitaliza como en el resto del registro; la localidad queda como se escribió
        self.assertEqual((direccion.calle, direccion.numero, direccion.ciudad), ('423 Bis', '2150', 'Villa Elisa'))

    def test_verificada_automaticamente(self):
        self.confirmar(latitud='-34.86', longitud='-58.08', ubicacion_origen='automatica')
        direccion = Direccion.objects.get(cliente__dni='30111222')
        self.assertEqual(direccion.ubicacion_origen, Direccion.UBICACION_AUTOMATICA)

    def test_la_pantalla_valida_en_el_mapa_y_usa_localidades(self):
        contenido = self.client.get(self.url).content.decode()
        self.assertIn('id="btn-confirmar-ubicacion" disabled', contenido)
        self.assertIn('name="confirmo_ubicacion"', contenido)
        self.assertIn('georef/api/localidades', contenido)
        self.assertNotIn('d[0].lat', contenido)


class CampoCiudadLocalidadesTests(TestCase):
    def test_registro_consulta_localidades_y_no_municipios(self):
        contenido = self.client.get(reverse('users:registro')).content.decode()
        self.assertIn('georef/api/localidades', contenido)
        self.assertNotIn('georef/api/municipios', contenido)
        self.assertIn('iniciarCiudadTomSelect', contenido)
