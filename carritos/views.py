from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest
from django.shortcuts import render, redirect
from django.urls import resolve, reverse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
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
)


def _get_session_cart(session) -> dict[str, int]:
	cart = session.get("carrito")
	if not isinstance(cart, dict):
		cart = {}

	normalized: dict[str, int] = {}
	for key, value in cart.items():
		try:
			normalized[str(int(key))] = max(0, int(value))
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
		colores_validos = {color.nombre.lower(): color.nombre for color in colores_variante}
		if color_nombre:
			color_nombre = colores_validos.get(color_nombre.lower(), '')
		elif len(colores_variante) == 1:
			color_nombre = colores_variante[0].nombre

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

	# IMPORTANTE: ahora usamos variante.id
	key = str(variante.id)

	current_qty = int(cart.get(key, 0))
	new_qty = current_qty + cantidad_int

	# Validar stock suficiente
	if new_qty > variante.stock:
		messages.error(
			request,
			f"Stock insuficiente. Disponibles: {variante.stock}, intentas: {new_qty}"
		)

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

			item, created = CarritoItem.objects.get_or_create(
				carrito=carrito,
				variante=variante,
				defaults={
					'cantidad': 0,
					'precio_unitario': variante.precio or producto.precio,
					'precio_total': 0
				}
			)

			item.cantidad = new_qty
			item.precio_unitario = variante.precio or producto.precio
			item.precio_total = item.cantidad * item.precio_unitario
			item.color_nombre = color_nombre or item.color_nombre
			item.save()

			# Sincronizar sesión con BD
			carrito_final = {}

			for item_db in carrito.items.all():
				carrito_final[str(item_db.variante.id)] = item_db.cantidad

			request.session['carrito'] = carrito_final
			colores_final = {}
			for item_db in carrito.items.all():
				if item_db.color_nombre:
					colores_final[str(item_db.variante.id)] = item_db.color_nombre
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
		cart[key] = new_qty
		cart_colors = request.session.get(SESSION_CART_COLORS_KEY)
		if not isinstance(cart_colors, dict):
			cart_colors = {}
		if color_nombre:
			cart_colors[key] = color_nombre

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
	variante_id = request.POST.get("variante_id") or request.POST.get("id")
	next_url = request.POST.get("next") or request.GET.get("next")
	if not next_url:
		next_url = reverse("home:home")

	try:
		variante_id_int = int(variante_id)
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
			
			# Buscar items de este producto en el carrito
			items_a_eliminar = carrito.items.filter(
				variante__id=variante_id_int
			)
			
			if items_a_eliminar.exists():
				items_a_eliminar.delete()
				# Actualizar sesión: sumar cantidades por producto_id
				carrito_final = {}
				for item_db in carrito.items.all():
					pid = str(item_db.variante.producto.id)
					carrito_final[pid] = carrito_final.get(pid, 0) + item_db.cantidad
				request.session['carrito'] = carrito_final
				request.session[SESSION_CART_COLORS_KEY] = {
					str(item_db.variante.id): item_db.color_nombre
					for item_db in carrito.items.all()
					if item_db.color_nombre
				}
				request.session.modified = True
				messages.success(request, "Producto eliminado del carrito.")
			else:
				messages.info(request, "Ese producto no está en tu carrito.")
		except Exception as e:
			messages.error(request, f"Error al eliminar: {str(e)}")
	else:
		# Usuario invitado: eliminar de sesión
		cart = _get_session_cart(request.session)
		key = str(variante_id_int)

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

	productos = Producto.objects.filter(id__in=cart.keys(), activo=True).prefetch_related("variantes__talle", "variantes__colores")
	productos_by_id = {producto.id: producto for producto in productos}

	items_a_crear = []
	total = 0
	cart_colors = request.session.get(SESSION_CART_COLORS_KEY)
	if not isinstance(cart_colors, dict):
		cart_colors = {}

	for producto_id, cantidad in cart.items():
		producto = productos_by_id.get(int(producto_id))
		if not producto:
			messages.error(request, "Uno de los productos del carrito ya no está disponible.")
			return redirect(next_url)

		if producto.stock < cantidad:
			messages.error(request, f"Stock insuficiente para {producto.nombre}. Disponible: {producto.stock}.")
			return redirect(next_url)

		variante = producto.variantes.filter(activa=True).order_by("id").first()
		if not variante:
			messages.error(request, f"El producto {producto.nombre} no tiene variantes activas para confirmar la compra.")
			return redirect(next_url)

		# Validar stock de la variante
		if variante.stock < cantidad:
			messages.error(request, f"Stock insuficiente para la variante de {producto.nombre}. Disponible: {variante.stock}.")
			return redirect(next_url)

		precio_unitario = variante.precio or producto.precio
		precio_total = precio_unitario * cantidad
		items_a_crear.append((variante, cantidad, precio_unitario, precio_total, producto, cart_colors.get(str(variante.id))))
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

	# Si el usuario está autenticado, SIEMPRE obtener desde BD
	if request.user.is_authenticated:
		try:
			carrito = get_or_create_cart(request)
			for item_db in carrito.items.all().select_related('variante__producto'):
				items.append({
					"id": item_db.variante.producto.id,  # Usar ID del producto para eliminar
					"variante_id": item_db.variante.id,
					"nombre": item_db.variante.producto.nombre,
					"precio": item_db.precio_unitario,
					"cantidad": item_db.cantidad,
					"subtotal": item_db.precio_total,
					"color_nombre": item_db.color_nombre,
				})
				total_qty += item_db.cantidad
				total_price += item_db.precio_total
			
			# Sincronizar sesión con BD para consistencia
			carrito_sincronizado = {}
			colores_sincronizados = {}
			for item_db in carrito.items.all():
				carrito_sincronizado[str(item_db.variante.id)] = item_db.cantidad
				if item_db.color_nombre:
					colores_sincronizados[str(item_db.variante.id)] = item_db.color_nombre
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

		quantities: dict[int, int] = {}

		for key, value in cart.items():
			try:
				variante_id = int(key)
				qty = int(value)
			except (TypeError, ValueError):
				continue

			if qty > 0:
				quantities[variante_id] = qty

		variantes = Variante.objects.select_related("producto").filter(
			id__in=quantities.keys(),
			activa=True,
			producto__activo=True
		)

		variantes_by_id = {
			v.id: v for v in variantes
		}

		for variante_id, qty in quantities.items():
			variante = variantes_by_id.get(variante_id)

			if not variante:
				continue

			precio = variante.precio or variante.producto.precio
			subtotal = precio * qty

			items.append({
				"id": variante.producto.id,
				"variante_id": variante.id,
				"nombre": variante.producto.nombre,
				"precio": precio,
				"cantidad": qty,
				"subtotal": subtotal,
				"color_nombre": cart_colors.get(str(variante.id)),
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
		"cart_expires_in": get_cart_seconds_left(request.session),
	}
from django.views.decorators.http import require_POST
from django.shortcuts import redirect

@require_POST
def sumar_producto(request):
    variante_id = request.POST.get("variante_id")
    next_url = request.POST.get("next") or request.GET.get("next")

    try:
        variante_id_int = int(variante_id)
    except (TypeError, ValueError):
        messages.error(request, "Producto inválido.")
        return redirect(next_url)

    if request.user.is_authenticated:
        carrito = get_or_create_cart(request)

        item = carrito.items.filter(variante_id=variante_id_int).first()

        if item:
            item.cantidad += 1
            item.save()
        else:
            carrito.items.create(variante_id=variante_id_int, cantidad=1)

        messages.success(request, "Cantidad actualizada.")
    else:
        cart = _get_session_cart(request.session)
        key = str(variante_id_int)

        cart[key] = cart.get(key, 0) + 1
        request.session["carrito"] = cart
        request.session.modified = True

    if _is_ajax(request):
        return _render_cart_fragment(request)

    return redirect(next_url)
