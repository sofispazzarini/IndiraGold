from __future__ import annotations

from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import render
from django.urls import resolve, reverse
from django.views.decorators.http import require_POST

from productos.models import Categoria
from productos.models import Producto
from productos.models import Talle, Color
from .utils import clear_cart_session, expire_cart_if_needed, get_cart_seconds_left, set_cart_started_at_if_missing


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
	producto_id = request.POST.get("producto_id") or request.POST.get("id")
	next_url = request.POST.get("next") or request.GET.get("next")
	if not next_url:
		next_url = reverse("home:home")

	if expire_cart_if_needed(request.session):
		messages.info(request, "Tu carrito expiró luego de 1 hora y fue reiniciado.")

	try:
		producto_id_int = int(producto_id)
	except (TypeError, ValueError):
		messages.error(request, "Producto inválido.")
		if _is_ajax(request):
			return _render_cart_fragment(request)
		return _render_next(request, next_url)

	try:
		producto = Producto.objects.get(pk=producto_id_int, activo=True)
	except Producto.DoesNotExist:
		messages.error(request, "Producto no encontrado.")
		if _is_ajax(request):
			return _render_cart_fragment(request)
		return _render_next(request, next_url)

	if producto.stock <= 0:
		messages.error(request, "Este producto no tiene stock.")
		if _is_ajax(request):
			return _render_cart_fragment(request)
		return _render_next(request, next_url)

	cart = _get_session_cart(request.session)
	key = str(producto.id)
	current_qty = int(cart.get(key, 0))
	new_qty = current_qty + 1

	if new_qty > producto.stock:
		messages.error(request, "Stock insuficiente para agregar otra unidad.")
		if _is_ajax(request):
			return _render_cart_fragment(request)
		return _render_next(request, next_url)

	cart[key] = new_qty
	set_cart_started_at_if_missing(request.session)
	request.session["carrito"] = cart
	request.session.modified = True

	messages.success(request, f"{producto.nombre} agregado al carrito.")
	if _is_ajax(request):
		return _render_cart_fragment(request)
	return _render_next(request, next_url)


@require_POST
def eliminar_producto(request):
	producto_id = request.POST.get("producto_id") or request.POST.get("id")
	next_url = request.POST.get("next") or request.GET.get("next")
	if not next_url:
		next_url = reverse("home:home")

	try:
		producto_id_int = int(producto_id)
	except (TypeError, ValueError):
		messages.error(request, "Producto inválido.")
		if _is_ajax(request):
			return _render_cart_fragment(request)
		return _render_next(request, next_url)

	cart = _get_session_cart(request.session)
	key = str(producto_id_int)

	if key in cart:
		del cart[key]
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
		producto = Producto.objects.filter(pk=pk, activo=True).first()
		if not producto:
			producto = None
		return render(request, "detalle_producto.html", {"producto": producto})

	# Default: home pública
	ctx = _build_home_context(request)
	return render(request, "home_publico.html", ctx)


def _build_home_context(request):
	expire_cart_if_needed(request.session)

	productos = Producto.objects.filter(activo=True).prefetch_related('variantes__talle', 'variantes__color')
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

	cart = request.session.get("carrito")
	if not isinstance(cart, dict):
		cart = {}

	quantities: dict[int, int] = {}
	for key, value in cart.items():
		try:
			pid = int(key)
			qty = int(value)
		except (TypeError, ValueError):
			continue
		if qty > 0:
			quantities[pid] = qty

	productos_by_id = {
		p.id: p for p in Producto.objects.filter(id__in=quantities.keys(), activo=True)
	}

	items = []
	total_qty = 0
	total_price = 0
	for pid, qty in quantities.items():
		p = productos_by_id.get(pid)
		if not p:
			continue
		subtotal = p.precio * qty
		items.append(
			{
				"id": p.id,
				"nombre": p.nombre,
				"precio": p.precio,
				"cantidad": qty,
				"subtotal": subtotal,
			}
		)
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
