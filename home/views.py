from django.views.generic import TemplateView
from productos.models import Producto, Categoria

class HomePublicaView(TemplateView):
    template_name = 'home_publico.html'
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['productos'] = Producto.objects.filter(activo=True)
        ctx['categorias'] = Categoria.objects.all()

        cart = self.request.session.get('carrito')
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
            p.id: p
            for p in Producto.objects.filter(id__in=quantities.keys(), activo=True)
        }

        items = []
        total_qty = 0
        total_price = 0
        for pid, qty in quantities.items():
            p = productos_by_id.get(pid)
            if not p:
                continue
            subtotal = p.precio * qty
            items.append({
                'id': p.id,
                'nombre': p.nombre,
                'precio': p.precio,
                'cantidad': qty,
                'subtotal': subtotal,
            })
            total_qty += qty
            total_price += subtotal

        ctx['cart_items'] = items
        ctx['cart_count'] = total_qty
        ctx['cart_total'] = total_price
        return ctx