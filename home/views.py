# home/views.py
import json
from PIL import Image
from django.views.generic import TemplateView
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render, get_object_or_404
from productos.models import Producto, Categoria, Talle, Color, CategoriaOrden, Variante, Oferta
from carritos.utils import (
    clear_cart_session,
    expire_cart_if_needed,
    get_cart_seconds_left,
    get_or_create_cart,
    SESSION_CART_COLORS_KEY,
)
from consultas.models import TemaConsulta
from .models import SlideCarrousel, ConfiguracionHero
from .forms import SlideCarrouselForm

class HomePublicaView(TemplateView):
    template_name = 'home_publico.html'
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        expire_cart_if_needed(self.request.session)

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
        oferta_global_activa = Oferta.objects.filter(
            activa=True,
            aplicar_a_todos=True
        ).exists()

        if oferta_global_activa:

            productos_oferta = productos.filter(
                activo=True
            )

        else:

            productos_oferta = productos.filter(
                ofertas__activa=True
            ).distinct()
        ctx['productos'] = productos
        ctx['categorias'] = Categoria.objects.all()
        ctx['talles'] = talles
        ctx['colores'] = colores
        oferta_global_activa = Oferta.objects.filter(
            activa=True,
            aplicar_a_todos=True
        ).exists()

        if oferta_global_activa:

            productos_oferta = productos.filter(
                activo=True
            )

        else:

            productos_oferta = productos.filter(
                ofertas__activa=True
            ).distinct()

        ctx['productos_oferta'] = productos_oferta
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

        if self.request.user.is_authenticated:
            try:
                from carritos.utils import _make_cart_item_key, SESSION_CART_COLORS_KEY
                from carritos.views import _resolve_item_color_hex

                carrito = get_or_create_cart(self.request)
                for item_db in carrito.items.all().select_related('variante__producto'):
                    color_hex = _resolve_item_color_hex(item_db)
                    item_key = _make_cart_item_key(item_db.variante.id, item_db.color_nombre, item_db.color_hex)
                    items.append({
                        'id': item_db.variante.producto.id,
                        'variante_id': item_db.variante.id,
                        'cart_key': item_key,
                        'nombre': item_db.variante.producto.nombre,
                        'precio': item_db.precio_unitario,
                        'cantidad': item_db.cantidad,
                        'subtotal': item_db.precio_total,
                        'color_nombre': item_db.color_nombre,
                        'color_hex': color_hex,
                    })
                    total_qty += item_db.cantidad
                    total_price += item_db.precio_total

                # Sincronizar sesión con formato correcto
                carrito_sincronizado = {}
                colores_sincronizados = {}
                for item_db in carrito.items.all():
                    item_key = _make_cart_item_key(item_db.variante.id, item_db.color_nombre, item_db.color_hex)
                    carrito_sincronizado[item_key] = item_db.cantidad
                    colores_sincronizados[item_key] = {
                        "nombre": item_db.color_nombre,
                        "hex": item_db.color_hex,
                    }
                self.request.session['carrito'] = carrito_sincronizado
                self.request.session[SESSION_CART_COLORS_KEY] = colores_sincronizados
                self.request.session.modified = True
            except Exception:
                pass
        else:
            from carritos.utils import _parse_cart_item_key, _normalize_hex, SESSION_CART_COLORS_KEY as COLORS_KEY

            cart = self.request.session.get('carrito')
            cart_colors = self.request.session.get(COLORS_KEY)
            if not isinstance(cart, dict):
                cart = {}
                clear_cart_session(self.request.session)
            if not isinstance(cart_colors, dict):
                cart_colors = {}

            # Parsear claves y agrupar por variante_id
            cart_data = {}  # {cart_key: (variante_id, qty, color_data)}
            variante_ids = set()
            for cart_key, value in cart.items():
                try:
                    variante_id, _color_token = _parse_cart_item_key(cart_key)
                    if not variante_id:
                        continue
                    qty = int(value)
                    if qty <= 0:
                        continue
                    color_data = cart_colors.get(str(cart_key)) or {}
                    if isinstance(color_data, str):
                        color_data = {"nombre": color_data, "hex": None}
                    cart_data[cart_key] = (variante_id, qty, color_data)
                    variante_ids.add(variante_id)
                except (TypeError, ValueError):
                    continue

            variantes = Variante.objects.select_related('producto').filter(
                id__in=variante_ids,
                activa=True,
                producto__activo=True
            )
            variantes_by_id = {v.id: v for v in variantes}

            for cart_key, (variante_id, qty, color_data) in cart_data.items():
                variante = variantes_by_id.get(variante_id)
                if not variante:
                    continue
                precio = variante.precio or variante.producto.precio
                subtotal = precio * qty
                color_nombre = color_data.get("nombre")
                color_hex = _normalize_hex(color_data.get("hex"))
                items.append({
                    'id': variante.producto.id,
                    'variante_id': variante.id,
                    'cart_key': cart_key,
                    'nombre': variante.producto.nombre,
                    'precio': precio,
                    'cantidad': qty,
                    'subtotal': subtotal,
                    'color_nombre': color_nombre,
                    'color_hex': color_hex,
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
        ctx['hero'] = ConfiguracionHero.actual()

        categorias_orden = CategoriaOrden.objects.filter(activo=True).prefetch_related(
            'categoriaordenproducto_set__producto__imagenes'
        )
        ctx['categorias_orden'] = categorias_orden
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


@staff_member_required
def configurar_hero(request):
    hero = ConfiguracionHero.actual()

    if request.method == 'POST':
        hero.eyebrow = request.POST.get('eyebrow', hero.eyebrow)
        hero.titulo_linea1 = request.POST.get('titulo_linea1', hero.titulo_linea1)
        hero.titulo_linea2 = request.POST.get('titulo_linea2', hero.titulo_linea2)
        hero.subtitulo = request.POST.get('subtitulo', hero.subtitulo)
        hero.texto_cta = request.POST.get('texto_cta', hero.texto_cta)
        hero.link_cta = request.POST.get('link_cta', hero.link_cta)
        hero.color_fondo = request.POST.get('color_fondo', hero.color_fondo)
        hero.color_texto = request.POST.get('color_texto', hero.color_texto)
        hero.color_acento = request.POST.get('color_acento', hero.color_acento)
        hero.fuente_titulo = request.POST.get('fuente_titulo', hero.fuente_titulo)
        hero.activo = 'activo' in request.POST

        # Manejar imagen de fondo
        if 'eliminar_imagen' in request.POST and hero.imagen_fondo:
            hero.imagen_fondo.delete(save=False)
            hero.imagen_fondo = None
        elif 'imagen_fondo' in request.FILES:
            imagen = request.FILES['imagen_fondo']
            try:
                img = Image.open(imagen)
                img.verify()
                imagen.seek(0)
                if hero.imagen_fondo:
                    hero.imagen_fondo.delete(save=False)
                hero.imagen_fondo = imagen
            except Exception:
                messages.error(request, 'No se pudo agregar la imagen. Asegurate de subir un archivo de imagen válido (JPG, PNG, etc).')
                return redirect('home:configurar_hero')

        hero.save()
        messages.success(request, 'Configuración del Hero actualizada.')
        return redirect('home:configurar_hero')

    return render(request, 'home/configurar_hero.html', {'hero': hero})