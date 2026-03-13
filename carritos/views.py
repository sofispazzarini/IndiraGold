from __future__ import annotations

from django.contrib import messages
from django.shortcuts import render
from django.urls import resolve, reverse
from django.views.decorators.http import require_POST

from productos.models import Categoria
from productos.models import Producto


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


@require_POST
def agregar_producto(request):
	producto_id = request.POST.get("producto_id") or request.POST.get("id")
	next_url = request.POST.get("next") or request.GET.get("next")
	if not next_url:
		next_url = reverse("home:home")

	try:
		producto_id_int = int(producto_id)
	except (TypeError, ValueError):
		messages.error(request, "Producto inválido.")
		return _render_next(request, next_url)

	try:
		producto = Producto.objects.get(pk=producto_id_int, activo=True)
	except Producto.DoesNotExist:
		messages.error(request, "Producto no encontrado.")
		return _render_next(request, next_url)

	if producto.stock <= 0:
		messages.error(request, "Este producto no tiene stock.")
		return _render_next(request, next_url)

	cart = _get_session_cart(request.session)
	key = str(producto.id)
	current_qty = int(cart.get(key, 0))
	new_qty = current_qty + 1

	if new_qty > producto.stock:
		messages.error(request, "Stock insuficiente para agregar otra unidad.")
		return _render_next(request, next_url)

	cart[key] = new_qty
	request.session["carrito"] = cart
	request.session.modified = True

	messages.success(request, f"{producto.nombre} agregado al carrito.")
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
		return _render_next(request, next_url)

	cart = _get_session_cart(request.session)
	key = str(producto_id_int)

	if key in cart:
		del cart[key]
		request.session["carrito"] = cart
		request.session.modified = True
		messages.success(request, "Producto eliminado del carrito.")
	else:
		messages.info(request, "Ese producto no está en tu carrito.")

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
	productos = Producto.objects.filter(activo=True)
	categorias = Categoria.objects.all()

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
		"categorias": categorias,
		"cart_items": items,
		"cart_count": total_qty,
		"cart_total": total_price,
	}
