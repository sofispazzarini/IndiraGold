from django.views.generic import TemplateView
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render, get_object_or_404
from productos.models import Producto, Categoria, Talle, Color
from carritos.utils import clear_cart_session, expire_cart_if_needed, get_cart_seconds_left
from consultas.models import TemaConsulta
from .models import SlideCarrousel
from .forms import SlideCarrouselForm

class HomePublicaView(TemplateView):
    template_name = 'home_publico.html'
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        expire_cart_if_needed(self.request.session)

        productos = Producto.objects.filter(activo=True).prefetch_related('variantes__talle', 'variantes__colores')
        productos_destacados = productos.order_by('-created_at')[:8]
        if not productos_destacados:
            productos_destacados = productos[:8]

        talles = (
            Talle.objects.filter(variante__activa=True, variante__stock__gt=0, variante__producto__activo=True)
            .distinct()
            .order_by('nombre')
        )
        colores = (
            Color.objects.filter(variante__activa=True, variante__stock__gt=0, variante__producto__activo=True)
            .distinct()
            .order_by('nombre')
        )

        ctx['productos'] = productos
        ctx['productos_destacados'] = productos_destacados
        ctx['categorias'] = Categoria.objects.all()
        ctx['talles'] = talles
        ctx['colores'] = colores

        cart = self.request.session.get('carrito')
        if not isinstance(cart, dict):
            cart = {}
            clear_cart_session(self.request.session)

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
        ctx['cart_expires_in'] = get_cart_seconds_left(self.request.session)
        temas_con_faqs = TemaConsulta.objects.filter(
            activo=True,
            consultas__activa=True
        ).prefetch_related('consultas').distinct()
        ctx['temas_consulta'] = temas_con_faqs

        ctx['slides_carrousel'] = SlideCarrousel.objects.filter(activo=True)
        return ctx


# === GESTIÓN CARROUSEL ===

@staff_member_required
def gestion_carrousel(request):
    slides = SlideCarrousel.objects.all()
    return render(request, 'home/gestion_carrousel.html', {'slides': slides})


@staff_member_required
def crear_slide(request):
    if request.method == 'POST':
        form = SlideCarrouselForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Slide creado exitosamente.')
            return redirect('home:gestion_carrousel')
    else:
        form = SlideCarrouselForm()
    return render(request, 'home/crear_slide.html', {'form': form})


@staff_member_required
def editar_slide(request, slide_id):
    slide = get_object_or_404(SlideCarrousel, id=slide_id)
    if request.method == 'POST':
        form = SlideCarrouselForm(request.POST, request.FILES, instance=slide)
        if form.is_valid():
            form.save()
            messages.success(request, 'Slide actualizado exitosamente.')
            return redirect('home:gestion_carrousel')
    else:
        form = SlideCarrouselForm(instance=slide)
    return render(request, 'home/crear_slide.html', {'form': form, 'slide': slide})


@staff_member_required
def eliminar_slide(request, slide_id):
    slide = get_object_or_404(SlideCarrousel, id=slide_id)
    if request.method == 'POST':
        slide.imagen.delete(save=False)
        slide.delete()
        messages.success(request, 'Slide eliminado.')
    return redirect('home:gestion_carrousel')


@staff_member_required
def toggle_slide(request, slide_id):
    slide = get_object_or_404(SlideCarrousel, id=slide_id)
    if request.method == 'POST':
        slide.activo = not slide.activo
        slide.save()
        estado = 'activado' if slide.activo else 'desactivado'
        messages.success(request, f'Slide {estado}.')
    return redirect('home:gestion_carrousel')