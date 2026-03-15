from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from productos.models import Categoria, Proveedor, Producto
from decimal import Decimal
from carritos.utils import SESSION_CART_STARTED_AT_KEY


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

	def test_eliminar_producto_lo_quita_del_carrito_y_recalcula(self):
		agregar_url = reverse("carritos:agregar_producto")
		eliminar_url = reverse("carritos:eliminar_producto")

		self.client.post(agregar_url, {"producto_id": self.producto.id, "next": "/home/"})
		res = self.client.post(eliminar_url, {"producto_id": self.producto.id, "next": "/home/"})
		self.assertEqual(res.status_code, 200)

		session = self.client.session
		self.assertNotIn(str(self.producto.id), session.get("carrito", {}))

		# Al renderizar home_publico.html, el total y count deben quedar en 0
		self.assertIsNotNone(res.context)
		self.assertEqual(res.context["cart_count"], 0)
		self.assertIn(res.context["cart_total"], (0, Decimal("0")))

	def test_carrito_expirado_se_limpia_y_se_reinicia_al_agregar(self):
		url = reverse("carritos:agregar_producto")
		session = self.client.session
		session["carrito"] = {str(self.producto.id): 1}
		session[SESSION_CART_STARTED_AT_KEY] = int(timezone.now().timestamp()) - 3700
		session.save()

		res = self.client.post(url, {"producto_id": self.producto.id, "next": "/home/"})
		self.assertEqual(res.status_code, 200)

		session = self.client.session
		self.assertEqual(session["carrito"].get(str(self.producto.id)), 1)
		self.assertIn(SESSION_CART_STARTED_AT_KEY, session)

	def test_expirar_carrito_endpoint_vacia_carrito(self):
		session = self.client.session
		session["carrito"] = {str(self.producto.id): 1}
		session[SESSION_CART_STARTED_AT_KEY] = int(timezone.now().timestamp())
		session.save()

		url = reverse("carritos:expirar_carrito")
		res = self.client.post(url, {"next": "/home/"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
		self.assertEqual(res.status_code, 200)

		session = self.client.session
		self.assertEqual(session.get("carrito", {}), {})
		self.assertNotIn(SESSION_CART_STARTED_AT_KEY, session)
