from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import User

from productos.models import Categoria, Proveedor, Producto, Talle, Variante
from users.models import Cliente
from pedidos.models import Pedido, PedidoItem
from decimal import Decimal
from carritos.utils import SESSION_CART_STARTED_AT_KEY


class AgregarProductoCarritoTests(TestCase):
	def setUp(self):
		self.categoria = Categoria.objects.create(nombre="Cat")
		self.proveedor = Proveedor.objects.create(nombre="Prov", telefono="123")
		self.talle = Talle.objects.create(nombre="M")
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
		self.variante = Variante.objects.create(
			producto=self.producto,
			talle=self.talle,
			stock=1,
			precio="10.00",
			activa=True,
			qr_code="QR-001",
		)
		self.user = User.objects.create_user(username="12345678", password="testpass123", first_name="Cliente")
		self.cliente = Cliente.objects.create(user=self.user, dni="12345678", telefono="123456")

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

	def test_confirmar_compra_crea_pedido_y_detalle_para_cliente_logueado(self):
		self.client.force_login(self.user)
		session = self.client.session
		session["carrito"] = {str(self.producto.id): 1}
		session.save()

		url = reverse("carritos:confirmar_compra")
		res = self.client.post(url, {"next": "/home/"})
		self.assertEqual(res.status_code, 302)
		self.assertTrue(Pedido.objects.filter(cliente=self.cliente).exists())
		pedido = Pedido.objects.get(cliente=self.cliente)
		self.assertEqual(pedido.items.count(), 1)
		self.assertEqual(PedidoItem.objects.get(pedido=pedido).cantidad, 1)
		self.assertEqual(self.client.session.get("carrito", {}), {})

	def test_confirmar_compra_sin_login_redirige_a_login(self):
		url = reverse("carritos:confirmar_compra")
		res = self.client.post(url, {"next": "/home/"})
		self.assertEqual(res.status_code, 302)
		self.assertIn("/users/login/", res.url)
