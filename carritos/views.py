from __future__ import annotations
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest
from django.shortcuts import render, redirect
from django.urls import resolve, reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from carritos.utils import vincular_carrito_con_usuario, get_or_create_cart

from productos.models import Categoria
from productos.models import Producto
from productos.models import Talle, Color
from pedidos.models import Pedido, PedidoItem
from users.models import Cliente
from .utils import (
	clear_cart_session,
	expire_cart_if_needed,
	get_cart_seconds_left,
	set_cart_started_at_if_missing,
	SESSION_CART_COLORS_KEY,
	SESSION_CART_ITEM_KEY_SEPARATOR,
	_normalize_hex,
	_normalize_color_token,
	_make_cart_item_key,
	_parse_cart_item_key,
)

SESSION_CART_KEY = "carrito"


def _resolve_item_color_hex(item) -> str | None:
	"""Resolve a usable hex color from persisted item fields."""
	color_hex = _normalize_hex(getattr(item, 'color_hex', None))
	if color_hex:
		return color_hex

	color_nombre = getattr(item, 'color_nombre', None)
	color_hex = _normalize_hex(color_nombre)
	if color_hex:
		return color_hex

	if color_nombre:
		return _normalize_hex(
			item.variante.colores.filter(nombre__iexact=color_nombre).values_list('codigo_hex', flat=True).first()
		)

	return None


def _get_session_cart(session) -> dict[str, int]:
	cart = session.get("carrito")
	if not isinstance(cart, dict):
		cart = {}

	normalized: dict[str, int] = {}
	for key, value in cart.items():
		try:
			normalized[str(key)] = max(0, int(value))
		except (TypeError, ValueError):
			continue
	return normalized


def _is_ajax(request: HttpRequest) -> bool:
	return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _render_cart_fragment(request: HttpRequest):
	ctx = _build_home_context(request)
	return render(request, "carritos/_cart_fragment.html", ctx)


@require_POST
def agregar_producto(request):
	variante_id = request.POST.get("variante_id") or request.POST.get("id")
	cantidad = request.POST.get("cantidad", "1")
	color_nombre = (request.POST.get("color_nombre") or "").strip()
	next_url = request.POST.get("next") or request.GET.get("next")

	if not next_url:
		next_url = reverse("home:home")

	if expire_cart_if_needed(request.session):
		messages.info(request, "Tu carrito expiró luego de 1 hora y fue reiniciado.")

	# Validaciones básicas
	try:
		variante_id_int = int(variante_id)
		cantidad_int = int(cantidad)

		if cantidad_int < 1:
			raise ValueError("La cantidad debe ser mayor a 0")

	except (TypeError, ValueError):
		messages.error(request, "Cantidad inválida.")

		if _is_ajax(request):
			return _render_cart_fragment(request)

		return _render_next(request, next_url)

	# Buscar variante
	try:
		from productos.models import Variante

		variante = Variante.objects.select_related("producto").get(
			pk=variante_id_int,
			activa=True
		)
		colores_variante = list(variante.colores.all())
		colores_validos = {color.nombre.lower(): color for color in colores_variante}
		color_hex = None
		if color_nombre:
			color_obj = colores_validos.get(color_nombre.lower())
			if color_obj:
				color_nombre = color_obj.nombre
				color_hex = color_obj.codigo_hex
			else:
				color_nombre = ''
		elif len(colores_variante) == 1:
			color_nombre = colores_variante[0].nombre
			color_hex = colores_variante[0].codigo_hex

		# Normalizar formato HEX (asegurar leading '#')
		if color_hex:
			color_hex = color_hex.strip()
			if color_hex and not color_hex.startswith('#'):
				color_hex = f"#{color_hex}"

		producto = variante.producto

	except Variante.DoesNotExist:
		messages.error(request, "Producto no encontrado.")

		if _is_ajax(request):
			return _render_cart_fragment(request)

		return _render_next(request, next_url)

	# Validar stock de variante
	if variante.stock <= 0:
		messages.error(request, "Este producto no tiene stock.")

		if _is_ajax(request):
			return _render_cart_fragment(request)

		return _render_next(request, next_url)

	# Carrito actual
	cart = _get_session_cart(request.session)

	key = _make_cart_item_key(variante.id, color_nombre=color_nombre, color_hex=color_hex)

	# Sumar TODAS las cantidades de esta variante (sin importar el color)
	total_variante_qty = 0
	for cart_key, qty in cart.items():
		vid, _ = _parse_cart_item_key(cart_key)
		if vid == variante.id:
			total_variante_qty += qty

	current_qty_this_key = int(cart.get(key, 0))
	new_qty_this_key = current_qty_this_key + cantidad_int
	new_total_qty = total_variante_qty + cantidad_int

	# Validar stock suficiente (considerando TODAS las entradas de esta variante)
	if new_total_qty > variante.stock:
		disponibles = variante.stock - total_variante_qty
		if disponibles <= 0:
			messages.error(request, f"Ya tenés el máximo disponible en tu carrito ({variante.stock} unidades)")
		else:
			messages.error(request, f"Solo podés agregar {disponibles} más (hay {variante.stock} en stock)")

		if _is_ajax(request):
			return _render_cart_fragment(request)

		return _render_next(request, next_url)

	# =========================
	# USUARIO AUTENTICADO
	# =========================
	if request.user.is_authenticated:

		try:
			carrito = get_or_create_cart(request)

			from .models import CarritoItem
			from decimal import Decimal
			from django.utils import timezone
			from datetime import timedelta

			# Si el carrito estaba vacío, reiniciar el cronómetro
			carrito_estaba_vacio = carrito.items.count() == 0
			if carrito_estaba_vacio:
				carrito.expires_at = timezone.now() + timedelta(hours=1)
				carrito.save()

			# Calcular precio con descuento si hay oferta activa
			precio_base = variante.precio or producto.precio
			oferta = producto.obtener_oferta_activa()
			if oferta:
				descuento = Decimal(oferta.descuento) / Decimal(100)
				precio_con_descuento = precio_base * (1 - descuento)
			else:
				precio_con_descuento = precio_base

			item = carrito.items.filter(
				variante=variante,
				color_nombre=color_nombre or None,
				color_hex=color_hex or None,
			).first()
			if not item:
				item = CarritoItem.objects.create(
					carrito=carrito,
					variante=variante,
					color_nombre=color_nombre or None,
					color_hex=color_hex or None,
					cantidad=0,
					precio_unitario=precio_con_descuento,
					precio_total=0,
				)

			item.cantidad = new_qty_this_key
			item.precio_unitario = precio_con_descuento
			item.precio_total = item.cantidad * item.precio_unitario
			item.color_nombre = color_nombre or item.color_nombre
			item.color_hex = color_hex or item.color_hex
			item.save()

			# Sincronizar sesión con BD
			carrito_final = {}

			for item_db in carrito.items.all():
				item_key = _make_cart_item_key(item_db.variante.id, item_db.color_nombre, item_db.color_hex)
				carrito_final[item_key] = item_db.cantidad

			request.session['carrito'] = carrito_final
			colores_final = {}
			for item_db in carrito.items.all():
				item_key = _make_cart_item_key(item_db.variante.id, item_db.color_nombre, item_db.color_hex)
				colores_final[item_key] = {
					"nombre": item_db.color_nombre,
					"hex": item_db.color_hex,
				}
			request.session[SESSION_CART_COLORS_KEY] = colores_final
			request.session.modified = True

		except Exception as e:
			messages.error(request, f"Error al agregar al carrito: {str(e)}")

			if _is_ajax(request):
				return _render_cart_fragment(request)

			return _render_next(request, next_url)

	# =========================
	# USUARIO INVITADO
	# =========================
	else:
		# Si el carrito estaba vacío, reiniciar el cronómetro
		carrito_estaba_vacio = len(cart) == 0 or sum(cart.values()) == 0

		cart[key] = new_qty_this_key
		cart_colors = request.session.get(SESSION_CART_COLORS_KEY)
		if not isinstance(cart_colors, dict):
			cart_colors = {}
		cart_colors[key] = {
			"nombre": color_nombre or None,
			"hex": color_hex or None,
		}

		if carrito_estaba_vacio:
			# Reiniciar cronómetro cuando se agrega el primer producto
			from .utils import SESSION_CART_STARTED_AT_KEY
			request.session[SESSION_CART_STARTED_AT_KEY] = int(timezone.now().timestamp())
		else:
			set_cart_started_at_if_missing(request.session)

		request.session["carrito"] = cart
		request.session[SESSION_CART_COLORS_KEY] = cart_colors
		request.session.modified = True

	messages.success(
		request,
		f"{producto.nombre} x{cantidad_int} agregado al carrito."
	)

	if _is_ajax(request):
		return _render_cart_fragment(request)

	return _render_next(request, next_url)

@require_POST
def eliminar_producto(request):
	cart_key = request.POST.get("cart_key") or request.POST.get("variante_id") or request.POST.get("id")
	next_url = request.POST.get("next") or request.GET.get("next")
	if not next_url:
		next_url = reverse("home:home")

	try:
		variante_id_int, color_token = _parse_cart_item_key(cart_key)
		if not variante_id_int:
			raise ValueError("Producto inválido")
	except (TypeError, ValueError):
		messages.error(request, "Producto inválido.")
		if _is_ajax(request):
			return _render_cart_fragment(request)
		return _render_next(request, next_url)

	# Si el usuario está autenticado, eliminar de BD
	if request.user.is_authenticated:
		try:
			from .models import CarritoItem
			carrito = get_or_create_cart(request)

			# Buscar items que coincidan con la clave del carrito
			# Primero intentar encontrar por cart_key exacto comparando con los items de BD
			items_a_eliminar = None
			for item_db in carrito.items.filter(variante__id=variante_id_int):
				item_key = _make_cart_item_key(item_db.variante.id, item_db.color_nombre, item_db.color_hex)
				if item_key == cart_key:
					items_a_eliminar = carrito.items.filter(pk=item_db.pk)
					break

			# Fallback: si no encontró por cart_key, buscar solo por variante_id
			if items_a_eliminar is None:
				items_a_eliminar = carrito.items.filter(variante__id=variante_id_int)
			
			if items_a_eliminar.exists():
				items_a_eliminar.delete()
				# Actualizar sesión: sumar cantidades por producto_id
				carrito_final = {}
				for item_db in carrito.items.all():
					item_key = _make_cart_item_key(item_db.variante.id, item_db.color_nombre, item_db.color_hex)
					carrito_final[item_key] = item_db.cantidad
				request.session['carrito'] = carrito_final
				request.session[SESSION_CART_COLORS_KEY] = {
					_make_cart_item_key(item_db.variante.id, item_db.color_nombre, item_db.color_hex): {
						"nombre": item_db.color_nombre,
						"hex": item_db.color_hex,
					}
					for item_db in carrito.items.all()
				}
				request.session.modified = True

				# Si el carrito quedó vacío, limpiar el timer
				if carrito.items.count() == 0:
					clear_cart_session(request.session)

				messages.success(request, "Producto eliminado del carrito.")
			else:
				messages.info(request, "Ese producto no está en tu carrito.")
		except Exception as e:
			messages.error(request, f"Error al eliminar: {str(e)}")
	else:
		# Usuario invitado: eliminar de sesión
		cart = _get_session_cart(request.session)
		key = str(cart_key)

		if key in cart:
			del cart[key]
			cart_colors = request.session.get(SESSION_CART_COLORS_KEY)
			if isinstance(cart_colors, dict):
				cart_colors.pop(key, None)
				request.session[SESSION_CART_COLORS_KEY] = cart_colors
			if cart:
				request.session["carrito"] = cart
				request.session.modified = True
			else:
				clear_cart_session(request.session)
			messages.success(request, "Producto eliminado del carrito.")
		else:
			messages.info(request, "Ese producto no está en tu carrito.")

	if _is_ajax(request):
		return _render_cart_fragment(request)

	return _render_next(request, next_url)


@require_POST
def expirar_carrito(request):
	next_url = request.POST.get("next") or request.GET.get("next") or reverse("home:home")
	clear_cart_session(request.session)
	messages.info(request, "El tiempo del carrito expiró y los productos fueron eliminados.")

	if _is_ajax(request):
		return _render_cart_fragment(request)
	return _render_next(request, next_url)


@login_required(login_url="/users/login/")
@require_POST
def confirmar_compra(request):
	next_url = request.POST.get("next") or reverse("home:home")
	if expire_cart_if_needed(request.session):
		messages.info(request, "Tu carrito expiró luego de 1 hora y fue reiniciado.")
		return redirect(next_url)

	cart = _get_session_cart(request.session)
	if not cart:
		messages.error(request, "Tu carrito está vacío.")
		return redirect(next_url)

	cliente = getattr(request.user, "cliente", None)
	if cliente is None:
		messages.error(request, "Tu usuario no tiene un perfil de cliente asociado.")
		return redirect(next_url)

	items_a_crear = []
	total = 0
	cart_colors = request.session.get(SESSION_CART_COLORS_KEY)
	if not isinstance(cart_colors, dict):
		cart_colors = {}

	for cart_key, cantidad in cart.items():
		variante_id, _color_token = _parse_cart_item_key(cart_key)
		if not variante_id:
			continue

		variante = Producto.objects.none()
		variante = (
			Producto.objects.filter(variantes__id=variante_id, activo=True)
			.select_related()
			.first()
		)
		if not variante:
			messages.error(request, "Uno de los productos del carrito ya no está disponible.")
			return redirect(next_url)

		variante_obj = variante.variantes.filter(id=variante_id, activa=True).first()
		if not variante_obj:
			messages.error(request, f"El producto {variante.nombre} no tiene esa variante activa para confirmar la compra.")
			return redirect(next_url)

		if variante_obj.stock < cantidad:
			messages.error(request, f"Stock insuficiente para la variante de {variante.nombre}. Disponible: {variante_obj.stock}.")
			return redirect(next_url)

		color_data = cart_colors.get(str(cart_key), {})
		if isinstance(color_data, str):
			color_data = {"nombre": color_data, "hex": None}
		precio_unitario = variante_obj.precio or variante.precio
		precio_total = precio_unitario * cantidad
		items_a_crear.append((variante_obj, cantidad, precio_unitario, precio_total, variante, color_data.get("nombre")))
		total += precio_total

	with transaction.atomic():
		pedido = Pedido.objects.create(
			cliente=cliente,
			total=total,
			tipo_venta='online',
			estado='pendiente',
		)

		for variante, cantidad, precio_unitario, precio_total, producto, color_nombre in items_a_crear:
			PedidoItem.objects.create(
				pedido=pedido,
				variante=variante,
				color_nombre=color_nombre,
				cantidad=cantidad,
				precio_unitario=precio_unitario,
				precio_total=precio_total,
			)
			producto.stock -= cantidad
			producto.save(update_fields=["stock"])
			variante.stock -= cantidad
			variante.save(update_fields=["stock"])

	clear_cart_session(request.session)
	messages.success(request, f"Compra confirmada. Pedido #{pedido.id} registrado correctamente.")
	if request.user.is_superuser:
		return redirect("pedidos:detalle_pedido", pedido_id=pedido.id)
	return redirect("users:dashboard_cliente")


def _render_next(request, next_url: str):
	"""Renderiza una página de destino (sin JSON) luego del POST.

	Soporta:
	- Home pública (home:home)
	- Detalle de producto (productos:producto_detail)

	Si `next_url` no se puede resolver, vuelve a home.
	"""
	# Nos quedamos sólo con el path (evita URLs absolutas)
	path = next_url.split("?", 1)[0]
	if not path.startswith("/"):
		path = reverse("home:home")

	try:
		match = resolve(path)
	except Exception:
		match = None

	if match and match.view_name == "productos:producto_detail":
		pk = match.kwargs.get("pk")
		producto = (
			Producto.objects
			.filter(pk=pk, activo=True)
			.prefetch_related("variantes__talle", "variantes__medida")
			.first()
		)
		ctx = _build_producto_detail_context(producto)
		return render(request, "detalle_producto.html", ctx)

	# Default: home pública
	ctx = _build_home_context(request)
	return render(request, "home_publico.html", ctx)


def _build_producto_detail_context(producto: Producto | None):
	if not producto:
		return {"producto": None, "tabla_medidas": []}

	tabla_medidas = []
	seen_talles = set()

	variantes = (
		producto.variantes
		.filter(activa=True, medida__isnull=False)
		.select_related("talle", "medida")
		.order_by("talle__nombre", "medida_id")
	)

	for variante in variantes:
		if variante.talle_id in seen_talles:
			continue

		medida = variante.medida
		tabla_medidas.append(
			{
				"talle": variante.talle.nombre,
				"alto": medida.alto,
				"ancho": medida.ancho,
				"largo": medida.largo,
				"tiro": medida.tiro,
			}
		)
		seen_talles.add(variante.talle_id)

	return {
		"producto": producto,
		"tabla_medidas": tabla_medidas,
	}


def _build_home_context(request):
	expire_cart_if_needed(request.session)

	productos = Producto.objects.filter(activo=True).prefetch_related('variantes__talle', 'variantes__colores')

	for producto in productos:
		variantes_data = []
		for v in producto.variantes.filter(activa=True).select_related('talle').prefetch_related('colores'):
			variantes_data.append({
				'id': v.id,
				'talle': v.talle.nombre,
				'stock': v.stock,
				'colores': [
					{
						'nombre': color.nombre,
						'codigo_hex': color.codigo_hex or '#888888',
					}
					for color in v.colores.all()
				],
			})
		producto.variantes_json = json.dumps(variantes_data)

	productos_destacados = productos.order_by("-created_at")[:8]
	# Fallback simple: si por algún motivo no hay destacados, reutilizamos los primeros del catálogo
	if not productos_destacados:
		productos_destacados = productos[:8]
	categorias = Categoria.objects.all()
	talles = (
		Talle.objects.filter(variante__activa=True, variante__stock__gt=0, variante__producto__activo=True)
		.distinct()
		.order_by("nombre")
	)
	colores = (
		Color.objects.filter(variante__activa=True, variante__stock__gt=0, variante__producto__activo=True)
		.distinct()
		.order_by("nombre")
	)

	items = []
	total_qty = 0
	total_price = 0
	carrito_db = None  # Para calcular tiempo restante

	# Si el usuario está autenticado, SIEMPRE obtener desde BD
	if request.user.is_authenticated:
		try:
			carrito = get_or_create_cart(request)
			carrito_db = carrito  # Guardar referencia para el timer
			if carrito is not None:
				for item_db in carrito.items.all().select_related('variante__producto'):
					color_hex = _resolve_item_color_hex(item_db)
					item_key = _make_cart_item_key(item_db.variante.id, item_db.color_nombre, item_db.color_hex)
					items.append({
						"id": item_db.variante.producto.id,
						"variante_id": item_db.variante.id,
						"cart_key": item_key,
						"nombre": item_db.variante.producto.nombre,
						"precio": item_db.precio_unitario,
						"cantidad": item_db.cantidad,
						"subtotal": item_db.precio_total,
						"color_nombre": item_db.color_nombre,
						"color_hex": color_hex,
					})
					total_qty += item_db.cantidad
					total_price += item_db.precio_total

				# Sincronizar sesión con BD para consistencia
				carrito_sincronizado = {}
				colores_sincronizados = {}
				for item_db in carrito.items.all():
					item_key = _make_cart_item_key(item_db.variante.id, item_db.color_nombre, item_db.color_hex)
					carrito_sincronizado[item_key] = item_db.cantidad
					colores_sincronizados[item_key] = {
						"nombre": item_db.color_nombre,
						"hex": item_db.color_hex,
					}
				request.session['carrito'] = carrito_sincronizado
				request.session[SESSION_CART_COLORS_KEY] = colores_sincronizados
				request.session.modified = True
		except Exception as e:
			# Si hay error, continuar sin items
			pass
	else:
		# Usuario invitado: obtener desde sesión
		from productos.models import Variante

		cart = request.session.get("carrito")
		cart_colors = request.session.get(SESSION_CART_COLORS_KEY)
		if not isinstance(cart, dict):
			cart = {}
		if not isinstance(cart_colors, dict):
			cart_colors = {}

		quantities: dict[str, int] = {}
		variante_ids: set[int] = set()

		for key, value in cart.items():
			try:
				variante_id, _color_token = _parse_cart_item_key(key)
				qty = int(value)
			except (TypeError, ValueError):
				continue

			if variante_id and qty > 0:
				quantities[key] = qty
				variante_ids.add(variante_id)

		variantes = Variante.objects.select_related("producto").filter(
			id__in=variante_ids,
			activa=True,
			producto__activo=True
		)

		variantes_by_id = {
			v.id: v for v in variantes
		}

		for cart_key, qty in quantities.items():
			variante_id, _color_token = _parse_cart_item_key(cart_key)
			if not variante_id:
				continue
			variante = variantes_by_id.get(variante_id)

			if not variante:
				continue

			color_data = cart_colors.get(str(cart_key)) or {}
			if isinstance(color_data, str):
				color_data = {"nombre": color_data, "hex": None}
			color_nombre = color_data.get("nombre")
			color_hex = _normalize_hex(color_data.get("hex"))
			if not color_hex and color_nombre:
				color_hex = _normalize_hex(
					variante.colores.filter(nombre__iexact=color_nombre).values_list('codigo_hex', flat=True).first()
				)
			precio = variante.precio or variante.producto.precio
			subtotal = precio * qty

			items.append({
				"id": variante.producto.id,
				"variante_id": variante.id,
				"cart_key": str(cart_key),
				"nombre": variante.producto.nombre,
				"precio": precio,
				"cantidad": qty,
				"subtotal": subtotal,
				"color_nombre": color_nombre,
				"color_hex": color_hex,
			})

			total_qty += qty
			total_price += subtotal
	return {
		"productos": productos,
		"productos_destacados": productos_destacados,
		"categorias": categorias,
		"talles": talles,
		"colores": colores,
		"cart_items": items,
		"cart_count": total_qty,
		"cart_total": total_price,
		"cart_expires_in": get_cart_seconds_left(request.session, carrito_db),
	}


@require_POST
def sumar_producto(request):
	cart_key = request.POST.get("cart_key") or request.POST.get("variante_id")
	next_url = request.POST.get("next") or request.GET.get("next")

	try:
		variante_id_int, _color_token = _parse_cart_item_key(cart_key)
		if not variante_id_int:
			raise ValueError("Producto inválido")
	except (TypeError, ValueError):
		messages.error(request, "Producto inválido.")
		return redirect(next_url)

	if request.user.is_authenticated:
		carrito = get_or_create_cart(request)
		color_data = request.session.get(SESSION_CART_COLORS_KEY, {}).get(str(cart_key), {})
		if isinstance(color_data, str):
			color_data = {"nombre": color_data, "hex": None}
		color_nombre = color_data.get("nombre")
		color_hex = color_data.get("hex")

		item = carrito.items.filter(
			variante_id=variante_id_int,
			color_nombre=color_nombre or None,
			color_hex=color_hex or None,
		).first()

		if item:
			item.cantidad += 1
			item.save()
		else:
			from productos.models import Variante

			variante = Variante.objects.filter(id=variante_id_int).first()
			if variante:
				carrito.items.create(
					variante_id=variante_id_int,
					cantidad=1,
					color_nombre=color_nombre,
					color_hex=color_hex,
					precio_unitario=variante.precio,
					precio_total=variante.precio,
				)

		# Sincronizar sesión con BD
		carrito_final = {}
		colores_final = {}
		for item_db in carrito.items.all():
			item_key = _make_cart_item_key(item_db.variante.id, item_db.color_nombre, item_db.color_hex)
			carrito_final[item_key] = item_db.cantidad
			colores_final[item_key] = {
				"nombre": item_db.color_nombre,
				"hex": item_db.color_hex,
			}
		request.session['carrito'] = carrito_final
		request.session[SESSION_CART_COLORS_KEY] = colores_final
		request.session.modified = True

		messages.success(request, "Cantidad actualizada.")
		return redirect(next_url or reverse("home:home"))
	else:
		cart = _get_session_cart(request.session)
		key = str(cart_key)

		cart[key] = cart.get(key, 0) + 1
		request.session["carrito"] = cart
		request.session.modified = True

		return redirect(next_url or reverse("home:home"))


@require_POST
def restar_producto(request):
	cart_key = request.POST.get("cart_key") or request.POST.get("variante_id")
	next_url = request.POST.get("next") or request.GET.get("next")

	try:
		variante_id_int, _color_token = _parse_cart_item_key(cart_key)
		if not variante_id_int:
			raise ValueError("Producto inválido")
	except (TypeError, ValueError):
		messages.error(request, "Producto inválido.")
		return redirect(next_url or reverse("home:home"))

	if request.user.is_authenticated:
		carrito = get_or_create_cart(request)
		color_data = request.session.get(SESSION_CART_COLORS_KEY, {}).get(str(cart_key), {})
		if isinstance(color_data, str):
			color_data = {"nombre": color_data, "hex": None}
		color_nombre = color_data.get("nombre")
		color_hex = color_data.get("hex")

		item = carrito.items.filter(
			variante_id=variante_id_int,
			color_nombre=color_nombre or None,
			color_hex=color_hex or None,
		).first()

		if item:
			if item.cantidad > 1:
				item.cantidad -= 1
				item.save()
			else:
				item.delete()

		# Sincronizar sesión con BD
		carrito_final = {}
		colores_final = {}
		for item_db in carrito.items.all():
			item_key = _make_cart_item_key(item_db.variante.id, item_db.color_nombre, item_db.color_hex)
			carrito_final[item_key] = item_db.cantidad
			colores_final[item_key] = {
				"nombre": item_db.color_nombre,
				"hex": item_db.color_hex,
			}
		request.session['carrito'] = carrito_final
		request.session[SESSION_CART_COLORS_KEY] = colores_final
		request.session.modified = True

		messages.success(request, "Cantidad actualizada.")
		return redirect(next_url or reverse("home:home"))
	else:
		cart = _get_session_cart(request.session)
		key = str(cart_key)

		if key in cart:
			if cart[key] > 1:
				cart[key] -= 1
			else:
				del cart[key]
		request.session["carrito"] = cart
		request.session.modified = True

		return redirect(next_url or reverse("home:home"))


@require_POST
def restaurar_carrito(request):
    """
    Restaura el carrito desde localStorage backup.
    Recibe JSON: { "items": [{"variante_id": 123, "cantidad": 2, "color_nombre": "Negro"}, ...] }
    Retorna cart fragment HTML.
    """
    if request.user.is_authenticated:
        return _render_cart_fragment(request)

    try:
        data = json.loads(request.body)
        items = data.get('items', [])

        if not isinstance(items, list) or not items:
            return _render_cart_fragment(request)

    except (json.JSONDecodeError, TypeError):
        return _render_cart_fragment(request)

    from productos.models import Variante

    expire_cart_if_needed(request.session)

    cart = {}
    cart_colors = {}

    variante_ids = []
    items_by_id = {}

    for item in items:
        try:
            vid = int(item.get('variante_id', 0))
            qty = int(item.get('cantidad', 0))
            color = item.get('color_nombre') or ''
            cart_key = item.get('cart_key') or ''

            if vid > 0 and qty > 0:
                variante_ids.append(vid)
                items_by_id[vid] = {'cantidad': qty, 'color_nombre': color.strip(), 'cart_key': cart_key.strip()}
        except (TypeError, ValueError):
            continue

    if not variante_ids:
        return _render_cart_fragment(request)

    valid_variantes = Variante.objects.filter(
        id__in=variante_ids,
        activa=True,
        producto__activo=True
    ).values('id', 'stock')

    valid_by_id = {v['id']: v for v in valid_variantes}

    for vid, item_data in items_by_id.items():
        if vid not in valid_by_id:
            continue

        variante = valid_by_id[vid]
        qty = min(item_data['cantidad'], variante['stock'])

        if qty > 0:
            color_nombre = item_data['color_nombre'] or None
            saved_cart_key = item_data.get('cart_key')
            if saved_cart_key:
                item_key = saved_cart_key
            else:
                item_key = _make_cart_item_key(vid, color_nombre=color_nombre)
            cart[item_key] = qty
            cart_colors[item_key] = {
                "nombre": color_nombre,
                "hex": None,
            }

    if cart:
        set_cart_started_at_if_missing(request.session)
        request.session['carrito'] = cart
        request.session[SESSION_CART_COLORS_KEY] = cart_colors
        request.session.modified = True

    return _render_cart_fragment(request)
