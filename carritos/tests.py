from django.test import TestCase
from django.urls import reverse

from productos.models import Categoria, Proveedor, Producto


class AgregarProductoCarritoTests(TestCase):
	def setUp(self):
		self.categoria = Categoria.objects.create(nombre="Cat")
		self.proveedor = Proveedor.objects.create(nombre="Prov", telefono="123")
		self.producto = Producto.objects.create(
			codigo="P-001",
			nombre="Producto 1",
			tipo="Tipo",
			tela="Tela",
			descripcion="Desc",
			precio="10.00",
			stock=1,
			categoria=self.categoria,
			proveedor=self.proveedor,
			activo=True,
		)

	def test_agregar_producto_con_stock_lo_incorpora_en_sesion(self):
		url = reverse("carritos:agregar_producto")
		res = self.client.post(url, {"producto_id": self.producto.id, "next": "/home/"})
		self.assertEqual(res.status_code, 200)

		session = self.client.session
		self.assertIn("carrito", session)
		self.assertEqual(session["carrito"].get(str(self.producto.id)), 1)

	def test_agregar_producto_sin_stock_no_incrementa(self):
		url = reverse("carritos:agregar_producto")
		self.client.post(url, {"producto_id": self.producto.id, "next": "/home/"})
		res = self.client.post(url, {"producto_id": self.producto.id, "next": "/home/"})
		self.assertEqual(res.status_code, 200)
		session = self.client.session
		self.assertEqual(session["carrito"].get(str(self.producto.id)), 1)
