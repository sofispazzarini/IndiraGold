import json
import re
import unicodedata
import uuid
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST, require_http_methods
from django.urls import reverse
from django.shortcuts import redirect, get_object_or_404, render
from django.contrib import messages
from django.http import Http404
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from django.core.paginator import Paginator
from django.http import JsonResponse

from .models import (
    Subcategoria, Producto, Talle, Color, Medida,
    Variante, Proveedor, ImagenProducto, Categoria, TipoMedida,
    VarianteColor, CategoriaOrden, CategoriaOrdenProducto, Oferta
)
from pedidos.models import ConfiguracionPago
from .forms import (
    ProductoForm, SubcategoriaForm, CategoriaForm,
    TipoMedidaForm, ProveedorForm, SubcategoriaSoloNombreForm,
    CategoriaOrdenForm
)
from django.db import transaction
from django.db.models import Q, Sum
from decimal import Decimal, InvalidOperation
from django.utils import timezone
from pedidos.templatetags.moneda import pesos_numero
from .stock import repartir_stock_en_colores, sincronizar_stock_variante, usa_stock_por_color
from carritos.utils import (
    get_or_create_cart,
    precio_unitario_vigente,
    get_cart_seconds_left,
    expire_cart_if_needed,
    SESSION_CART_COLORS_KEY,
    _make_cart_item_key,
    _parse_cart_item_key,
    _normalize_hex,
)


COLOR_HEX_BY_NAME = {
    'rojo': '#ff0000',
    'verde': '#00ff00',
    'azul': '#0000ff',
    'negro': '#000000',
    'blanco': '#ffffff',
    'gris': '#808080',
    'rosa': '#ffc0cb',
    'amarillo': '#ffff00',
    'celeste': '#87ceeb',
    'violeta': '#800080',
    'naranja': '#ffa500',
    'marron': '#8b4513',
    'cafe': '#6f4e37',
    'beige': '#d2b48c',
    'turquesa': '#40e0d0',
    'dorado': '#d4af37',
    'plateado': '#c0c0c0',
    'bordo': '#800020',
    'fucsia': '#ff00ff',
    'crema': '#fffdd0',
    'nude': '#e3bc9a',
    'camel': '#c19a6b',
    'suela': '#a0522d',
    'chocolate': '#7b3f00',
    'natural': '#e8dcc4',
    'verde militar': '#4b5320',
    'azul marino': '#000080',
}


def normalizar_hex_color(nombre, codigo_hex=None):
    # Sin acentos: "Marrón" y "marron" son el mismo color
    nombre_limpio = unicodedata.normalize('NFKD', (nombre or '').strip().lower())
    nombre_limpio = ''.join(c for c in nombre_limpio if not unicodedata.combining(c))
    hex_actual = (codigo_hex or '').strip().lower()

    if hex_actual and hex_actual != '#888888':
        return hex_actual

    if nombre_limpio in COLOR_HEX_BY_NAME:
        return COLOR_HEX_BY_NAME[nombre_limpio]

    return hex_actual or '#888888'


def recalcular_stock_producto(producto):
    producto.stock = producto.stock_total
    producto.save(update_fields=['stock'])
    return producto.stock


def producto_debe_regenerar_qr(codigo_original, codigo_nuevo):
    return (codigo_original or '').strip() != (codigo_nuevo or '').strip()


def variante_debe_regenerar_qr(variante, talle_original_id, colores_originales_ids):
    """Solo si cambió el talle (la etiqueta impresa dice otro talle). Agregar o quitar un color no
    regenera los QR de los demás colores: las etiquetas ya pegadas siguen escaneando (los colores
    nuevos reciben su QR al crearse)."""
    return variante.talle_id != talle_original_id


def sincronizar_qrs_variante_color(variante, regenerar_qr=False):
    """Mantiene los registros VarianteColor sincronizados con los colores actuales de la variante.

    Si regenerar_qr=True, reasigna el qr_code de los registros existentes para
    forzar la reimpresión de los QR después de cambios en el producto.
    """
    colores_actuales = list(variante.colores.all())

    registros_actuales = list(VarianteColor.objects.filter(variante=variante).select_related('color'))
    ids_nuevos = {color.id for color in colores_actuales}

    # Si el talle todavía no tenía stock por color, los registros nuevos reciben el stock
    # del talle repartido entre sus colores (antes se creaban en 0 y el producto dejaba de venderse)
    reparto_inicial = (
        repartir_stock_en_colores(variante.stock, colores_actuales)
        if not registros_actuales
        else {}
    )

    para_borrar = [vc for vc in registros_actuales if vc.color_id not in ids_nuevos]
    for vc in para_borrar:
        vc.delete()

    for color in colores_actuales:
        vc, created = VarianteColor.objects.get_or_create(
            variante=variante,
            color=color,
            defaults={'activo': True, 'stock': reparto_inicial.get(color.id, 0)}
        )
        if created or regenerar_qr or not vc.qr_code:
            vc.qr_code = str(uuid.uuid4())
            vc.save(update_fields=['qr_code'])

    for vc in VarianteColor.objects.filter(variante=variante).select_related('color'):
        if regenerar_qr or not vc.qr_code:
            vc.qr_code = str(uuid.uuid4())
            vc.save(update_fields=['qr_code'])

    return VarianteColor.objects.filter(variante=variante, activo=True).select_related('color')

def leer_colores_con_stock(request):
    """Lee los colores del form de talle ("nombre|#hex") con su stock ("stock_color", en el
    mismo orden). Si un color se repite, se suman sus stocks."""
    colores = {}
    datos = request.POST.getlist('colores')
    stocks = request.POST.getlist('stock_color')
    for index, dato in enumerate(datos):
        dato = dato.strip()
        if not dato:
            continue
        if '|' in dato:
            nombre, codigo_hex = dato.split('|', 1)
        else:
            nombre, codigo_hex = dato, '#888888'
        nombre = nombre.strip()
        try:
            stock_color = max(int(stocks[index]), 0) if index < len(stocks) and stocks[index] != '' else 0
        except (TypeError, ValueError):
            stock_color = 0
        clave = nombre.lower()
        if clave in colores:
            colores[clave]['stock'] += stock_color
        else:
            colores[clave] = {'nombre': nombre, 'hex': codigo_hex, 'stock': stock_color}
    return list(colores.values())


def medida_a_decimal(valor):
    """Medida en cm escrita por el admin: "12,5 cm" -> 12.5; vacío -> 0. ValueError si no es un número."""
    texto = (valor or '').strip().lower().replace('cm', '').replace(',', '.').strip()
    if not texto:
        return Decimal('0')
    try:
        numero = Decimal(texto)
    except InvalidOperation:
        raise ValueError(valor)
    if not numero.is_finite() or numero < 0 or numero >= 10000:
        raise ValueError(valor)
    return numero


def error_en_medidas(request):
    """Mensaje si alguna medida del form no es un número válido (se valida antes de guardar nada)."""
    for campo, etiqueta in (('alto', 'Alto'), ('ancho', 'Ancho'), ('largo', 'Largo'), ('tiro', 'Tiro')):
        for valor in request.POST.getlist(campo):
            try:
                medida_a_decimal(valor)
            except ValueError:
                return f'{etiqueta}: "{valor}" no es una medida válida. Usá solo números (ej: 12,5).'
    return None


def obtener_talle(nombre):
    """Talle por nombre sin distinguir mayúsculas ("s" y "S" son el mismo talle)."""
    nombre = (nombre or '').strip() or 'Sin talle'
    return Talle.objects.filter(nombre__iexact=nombre).first() or Talle.objects.create(nombre=nombre)


def color_desde_form(nombre, codigo_hex, producto=None):
    """Color por nombre (sin distinguir mayúsculas). Los colores son compartidos entre productos:
    si ya lo usa otro producto, su tono no se cambia desde acá (antes "Blanco" pasaba a negro en
    toda la tienda). Si es nuevo, o solo lo usa este producto, se guarda el tono elegido."""
    codigo_hex = normalizar_hex_color(nombre, codigo_hex)
    color_obj = Color.objects.filter(nombre__iexact=nombre).first()
    if color_obj is None:
        return Color.objects.create(nombre=nombre, codigo_hex=codigo_hex)
    if codigo_hex == '#888888' or (color_obj.codigo_hex or '').lower() == codigo_hex:
        return color_obj
    compartido = Variante.objects.filter(colores=color_obj)
    if producto is not None:
        compartido = compartido.exclude(producto=producto)
    if (color_obj.codigo_hex or '').lower() in ('', '#888888') or not compartido.exists():
        color_obj.codigo_hex = codigo_hex
        color_obj.save(update_fields=['codigo_hex'])
    return color_obj


def tiene_ventas(producto=None, variante=None):
    """True si el producto o talle aparece en pedidos o ventas presenciales."""
    from pedidos.models import PedidoItem, VentaLocalItem

    if variante is not None:
        return (
            PedidoItem.objects.filter(variante=variante).exists()
            or VentaLocalItem.objects.filter(variante=variante).exists()
        )
    return (
        PedidoItem.objects.filter(variante__producto=producto).exists()
        or VentaLocalItem.objects.filter(producto=producto).exists()
        or VentaLocalItem.objects.filter(variante__producto=producto).exists()
    )


# --- DECORADOR AUXILIAR ---
from config.permisos import admin_required  # noqa: E402 (mismo decorador en todo el panel)

# --- VISTAS PÚBLICAS ---

def detalle_producto(request, producto_id):
    """
    Página pública de detalle de un producto.
    Muestra información completa, variantes, medidas y opción de compra.
    """
    expire_cart_if_needed(request.session)

    producto = get_object_or_404(Producto, id=producto_id, activo=True)
    variantes = producto.variantes.filter(activa=True).select_related('talle').prefetch_related('colores', 'medidas', 'variante_colores__color')

    # Si no hay variantes activas, mostrar que ha sido descontinuado
    if not variantes.exists():
        variantes = []

    # Obtener producto anterior y siguiente (todos los productos activos)
    # Anterior: ID mayor (viene antes en orden -id)
    producto_anterior = (
        Producto.objects
        .filter(activo=True, id__gt=producto.id)
        .order_by('id')
        .only('id', 'nombre')
        .first()
    )
    # Siguiente: ID menor (viene después en orden -id)
    producto_siguiente = (
        Producto.objects
        .filter(activo=True, id__lt=producto.id)
        .order_by('-id')
        .only('id', 'nombre')
        .first()
    )

    # Obtener productos relacionados de la misma subcategoría
    productos_relacionados = (
        Producto.objects
        .filter(subcategoria=producto.subcategoria, activo=True)
        .exclude(id=producto.id)
        .prefetch_related('imagenes')[:4]
    )

    # Construir contexto del carrito
    cart_items = []
    cart_count = 0
    cart_total = 0
    carrito_db = None  # Para calcular tiempo restante

    if request.user.is_authenticated:
        try:
            carrito = get_or_create_cart(request)
            carrito_db = carrito  # Guardar para el timer
            if carrito is None:
                raise Exception("Admin user")
            # El mini-carrito muestra el precio vigente (si cambió una oferta, no el guardado)
            from carritos.utils import refrescar_precios_carrito
            refrescar_precios_carrito(carrito)
            for item_db in carrito.items.all().select_related('variante__producto'):
                color_hex = _normalize_hex(getattr(item_db, 'color_hex', None))
                if not color_hex and item_db.color_nombre:
                    color_hex = _normalize_hex(
                        item_db.variante.colores.filter(nombre__iexact=item_db.color_nombre)
                        .values_list('codigo_hex', flat=True).first()
                    )
                item_key = _make_cart_item_key(item_db.variante.id, item_db.color_nombre, item_db.color_hex)
                cart_items.append({
                    "id": item_db.variante.producto.id,
                    "variante_id": item_db.variante.id,
                    "cart_key": item_key,
                    "nombre": item_db.variante.producto.nombre,
                    "talle": item_db.variante.talle.nombre if item_db.variante.talle else '',
                    "precio": item_db.precio_unitario,
                    "cantidad": item_db.cantidad,
                    "subtotal": item_db.subtotal,
                    "color_nombre": item_db.color_nombre,
                    "color_hex": color_hex,
                })
                cart_count += item_db.cantidad
                cart_total += item_db.subtotal
        except Exception:
            pass
    else:
        cart = request.session.get("carrito")
        cart_colors = request.session.get(SESSION_CART_COLORS_KEY)
        if not isinstance(cart, dict):
            cart = {}
        if not isinstance(cart_colors, dict):
            cart_colors = {}

        variante_ids = set()
        for key in cart.keys():
            vid, _ = _parse_cart_item_key(key)
            if vid:
                variante_ids.add(vid)

        variantes_map = {
            v.id: v for v in Variante.objects.select_related("producto").filter(
                id__in=variante_ids, activa=True, producto__activo=True
            )
        }

        for cart_key, qty in cart.items():
            try:
                qty = int(qty)
                if qty <= 0:
                    continue
                vid, _ = _parse_cart_item_key(cart_key)
                if not vid:
                    continue
                variante = variantes_map.get(vid)
                if not variante:
                    continue

                color_data = cart_colors.get(str(cart_key)) or {}
                if isinstance(color_data, str):
                    color_data = {"nombre": color_data, "hex": None}
                color_nombre = color_data.get("nombre")
                color_hex = _normalize_hex(color_data.get("hex"))
                if not color_hex and color_nombre:
                    color_hex = _normalize_hex(
                        variante.colores.filter(nombre__iexact=color_nombre)
                        .values_list('codigo_hex', flat=True).first()
                    )
                precio = precio_unitario_vigente(variante)
                subtotal = precio * qty

                cart_items.append({
                    "id": variante.producto.id,
                    "variante_id": variante.id,
                    "cart_key": str(cart_key),
                    "nombre": variante.producto.nombre,
                    "talle": variante.talle.nombre if variante.talle else '',
                    "precio": precio,
                    "cantidad": qty,
                    "subtotal": subtotal,
                    "color_nombre": color_nombre,
                    "color_hex": color_hex,
                })
                cart_count += qty
                cart_total += subtotal
            except (TypeError, ValueError):
                continue

    # Calcular cantidades en carrito por variante (y por color) para limitar el máximo
    cart_qty_by_variante = {}
    cart_qty_by_color = {}
    for item in cart_items:
        vid = item.get('variante_id')
        if vid:
            cart_qty_by_variante[vid] = cart_qty_by_variante.get(vid, 0) + item.get('cantidad', 0)
            color_key = (vid, (item.get('color_nombre') or '').strip().lower())
            cart_qty_by_color[color_key] = cart_qty_by_color.get(color_key, 0) + item.get('cantidad', 0)

    def colores_de_variante(variante):
        colores_stock = [vc for vc in variante.variante_colores.all() if vc.activo]
        if colores_stock:
            return [
                {
                    'id': vc.color.id,
                    'nombre': vc.color.nombre,
                    'codigo_hex': normalizar_hex_color(vc.color.nombre, vc.color.codigo_hex),
                    'hex': normalizar_hex_color(vc.color.nombre, vc.color.codigo_hex),
                    'stock': vc.stock,
                    'en_carrito': cart_qty_by_color.get((variante.id, vc.color.nombre.strip().lower()), 0),
                }
                for vc in colores_stock
            ]
        return [
            {
                'id': color.id,
                'nombre': color.nombre,
                'codigo_hex': normalizar_hex_color(color.nombre, color.codigo_hex),
                'hex': normalizar_hex_color(color.nombre, color.codigo_hex),
                'stock': None,
                'en_carrito': 0,
            }
            for color in variante.colores.all()
        ]

    # Obtener planes de cuotas para mostrar en el detalle
    planes_cuotas = []
    monto_cuota = None
    plan_cuotas_mejor = None
    try:
        config_pago = ConfiguracionPago.objects.first()
        if config_pago and config_pago.mercado_pago_activo:
            planes_cuotas = list(config_pago.planes_cuotas.filter(activo=True).order_by('-cuotas'))
            if planes_cuotas:
                plan_cuotas_mejor = next((p for p in planes_cuotas if p.sin_interes), planes_cuotas[0])
                monto_cuota = round(producto.precio_final / plan_cuotas_mejor.cuotas, 2)
    except Exception:
        pass

    variantes_data = []
    for variante in variantes:
        colores = colores_de_variante(variante)
        con_stock_color = [c for c in colores if c['stock'] is not None]
        variantes_data.append({
            'id': variante.id,
            'stock': sum(c['stock'] for c in con_stock_color) if con_stock_color else variante.stock,
            'en_carrito': cart_qty_by_variante.get(variante.id, 0),
            'colores': colores,
        })

    context = {
        'producto': producto,
        'variantes': variantes,
        'variantes_data': variantes_data,
        'productos_relacionados': productos_relacionados,
        'talles_disponibles': [v.talle for v in variantes],
        'producto_anterior': producto_anterior,
        'producto_siguiente': producto_siguiente,
        'cart_items': cart_items,
        'cart_count': cart_count,
        'cart_total': cart_total,
        'cart_expires_in': get_cart_seconds_left(request.session, carrito_db),
        'planes_cuotas': planes_cuotas,
        'monto_cuota': monto_cuota,
        'plan_cuotas_mejor': plan_cuotas_mejor,
    }

    return render(request, 'productos/producto_detalle.html', context)

# --- GESTIÓN DE PRODUCTOS Y NAVEGACIÓN ---

@admin_required
def gestion_productos(request):
    categories = Categoria.objects.filter(activa=True).order_by('nombre')
    return render(request, 'productos/gestion_productos.html', {'categories': categories})

@admin_required
def lista_subcategorias(request, categoria_id):
    # El template lista_subcategorias.html nunca existió: se usa la gestión de subcategorías
    categoria = get_object_or_404(Categoria, id=categoria_id)
    return redirect('productos:gestion_subcategorias', cat_id=categoria.id)

@admin_required
def productos_por_subcategoria(request, subcat_id):
    subcategoria = get_object_or_404(Subcategoria, id=subcat_id)
    categoria = subcategoria.categoria 
    productos = Producto.objects.filter(subcategoria=subcategoria).order_by('-id')
    return render(request, 'productos/productos_por_subcategoria.html', {
        'subcategoria': subcategoria,
        'categoria': categoria,
        'productos': productos
    })

# --- CRUD PRODUCTOS ---

@admin_required
def agregar_producto(request, subcat_id):
    subcategoria = get_object_or_404(Subcategoria, id=subcat_id, activa=True)
    proveedores = Proveedor.objects.all().order_by('nombre')
    categoria_padre = subcategoria.categoria
    if request.method == 'POST':
        form = ProductoForm(request.POST, request.FILES)
        variantes_json = request.POST.get('variantes_json')
        imagenes_galeria = request.FILES.getlist('imagenes')

        # Usar subcategoría del formulario si se cambió
        subcat_form_id = request.POST.get('subcategoria_id')
        if subcat_form_id:
            subcategoria = get_object_or_404(Subcategoria, id=subcat_form_id, activa=True)
            categoria_padre = subcategoria.categoria

        try:
            variantes_list = json.loads(variantes_json) if variantes_json else []
        except (TypeError, ValueError):
            variantes_list = []
        talles_cargados = [((v.get('talle') or '').strip() or 'Sin talle').casefold() for v in variantes_list]
        talles_repetidos = sorted({t for t in talles_cargados if talles_cargados.count(t) > 1})

        if len(imagenes_galeria) > 5:
            messages.error(request, "Máximo 5 imágenes de galería permitidas.")
        elif talles_repetidos:
            messages.error(
                request,
                f"El talle {', '.join(t.upper() for t in talles_repetidos)} está cargado más de una vez. "
                "Cargá cada talle una sola vez (con todos sus colores)."
            )
        elif form.is_valid():
            with transaction.atomic():
                producto = form.save(commit=False)
                producto.subcategoria = subcategoria
                producto.categoria = categoria_padre
                producto.activo = True
                producto.stock = 0
                producto.save()
                for img in imagenes_galeria:
                    ImagenProducto.objects.create(producto=producto, imagen=img)

                if variantes_json:
                    stock_total = 0
                    for v in variantes_list:
                        talle_nombre = (v.get('talle') or '').strip() or 'Sin talle'
                        talle_obj = obtener_talle(talle_nombre)
                        stock_variante = max(int(v.get('stock') or 0), 0)
                        stock_total += stock_variante
                    
                        # 2. Crear la Variante
                        nueva_variante = Variante.objects.create(
                            producto=producto,
                            talle=talle_obj,
                            stock=stock_variante,
                            precio=float(v.get('precio', 0)),
                            qr_code=str(uuid.uuid4())
                        )
                    
                        # 3. VINCULAR COLORES (Importante: es ManyToMany)
                        colores_data = v.get('colores', [])
                        for c in colores_data:
                            nombre_color = c.get('colorNombre') or c.get('colorHex')
                            codigo_hex = normalizar_hex_color(
                                nombre_color,
                                c.get('colorHex') or '#888888'
                            )
                            stock_color = int(c.get('stock', 0))
                            if nombre_color:
                                color_obj = color_desde_form(nombre_color, codigo_hex, producto=nueva_variante.producto)
                                nueva_variante.colores.add(color_obj)
                                vc, creado = VarianteColor.objects.get_or_create(
                                    variante=nueva_variante,
                                    color=color_obj,
                                )
                                # Si el mismo color se cargó dos veces, se suman los stocks
                                vc.stock = max(stock_color, 0) if creado else vc.stock + max(stock_color, 0)
                                vc.save()

                        sincronizar_stock_variante(nueva_variante)
                    
                        # 4. VINCULAR MEDIDAS
                        medidas_data = v.get('medidas', [])
                        for m in medidas_data:
                            # Creamos el objeto medida y lo asociamos a la variante
                            medida_obj = Medida.objects.create(
                                alto=m.get('alto') or 0,
                                ancho=m.get('ancho') or 0,
                                largo=m.get('largo') or 0,
                                tiro=m.get('tiro') or 0
                            )
                            nueva_variante.medidas.add(medida_obj)
                    recalcular_stock_producto(producto)
            
                messages.success(request, 'Producto guardado correctamente.')
                return redirect('productos:productos_por_subcategoria', subcat_id=subcategoria.id)
    else:
        form = ProductoForm()
    todas_categorias = Categoria.objects.filter(activa=True).order_by('nombre')
    todas_subcategorias = Subcategoria.objects.filter(categoria=categoria_padre, activa=True).order_by('nombre')

    # Si el guardado falló, se devuelve lo cargado para no perderlo (ficha, proveedor y talles).
    # Los archivos (fotos y dibujo técnico) no se pueden conservar: se pide volver a adjuntarlos.
    variantes_previas = []
    proveedor_seleccionado = None
    if request.method == 'POST':
        variantes_previas = variantes_list
        proveedor_seleccionado = Proveedor.objects.filter(id=request.POST.get('proveedor') or None).first()
        if request.FILES:
            messages.info(request, 'Volvé a adjuntar las fotos y el dibujo técnico antes de guardar.')

    return render(request, 'productos/agregar_producto.html', {
        'form': form,
        'subcategoria': subcategoria,
        'proveedores': proveedores,
        'categoria': categoria_padre,
        'todas_categorias': todas_categorias,
        'todas_subcategorias': todas_subcategorias,
        'variantes_previas': variantes_previas,
        'proveedor_seleccionado': proveedor_seleccionado,
    })

@admin_required
def editar_producto(request, prod_id):
    producto = get_object_or_404(Producto, id=prod_id)
    
    # 1. SEGURIDAD: Guardamos las relaciones en variables locales.
    # Esto evita el error "RelatedObjectDoesNotExist" al procesar el POST.
    cat_segura = producto.categoria
    subcat_segura = producto.subcategoria
    
    if request.method == 'POST':
        form = ProductoForm(request.POST, request.FILES, instance=producto)
        nuevas_fotos = request.FILES.getlist('fotos_galeria')
        esquema_nuevo = request.FILES.get('imagen_tecnica')
        codigo_original = producto.codigo
        
        if form.is_valid():
            # 2. commit=False para reasignar las relaciones obligatorias
            producto_editado = form.save(commit=False)
            producto_editado.categoria = cat_segura
            producto_editado.subcategoria = subcat_segura
            
            # Si se subió un esquema por el input manual, lo asignamos
            if esquema_nuevo:
                producto_editado.imagen_tecnica = esquema_nuevo
            
            producto_editado.stock = producto.stock_total
            producto_editado.save()
            form.save_m2m()

            # Los talles guardan una copia del precio: mantenerla igual al precio publicado
            producto_editado.variantes.exclude(precio=producto_editado.precio).update(
                precio=producto_editado.precio
            )

            for variante in producto_editado.variantes.all():
                for vc in variante.variante_colores.all():
                    color_stock_key = f'color_stock_{vc.id}'
                    if color_stock_key in request.POST:
                        try:
                            vc.stock = max(int(request.POST.get(color_stock_key) or 0), 0)
                            vc.save(update_fields=['stock'])
                        except ValueError:
                            pass
                # Con colores, el stock del talle es siempre la suma de sus colores (aunque sea 0)
                sincronizar_stock_variante(variante)

            if producto_debe_regenerar_qr(codigo_original, producto_editado.codigo):
                for variante in producto_editado.variantes.all().prefetch_related('colores'):
                    sincronizar_qrs_variante_color(variante, regenerar_qr=True)

            recalcular_stock_producto(producto_editado)
            # 3. Guardado de fotos comerciales (Máximo 5 controlado en HTML)
            for foto in nuevas_fotos:
                ImagenProducto.objects.create(producto=producto_editado, imagen=foto)
            
            messages.success(request, 'Producto actualizado correctamente.')
            return redirect('productos:productos_por_subcategoria', subcat_id=subcat_segura.id)
        
        else:
            # 4. TRADUCCIÓN DE ERRORES AL ESPAÑOL
            traducciones = {
                "Upload a valid image. The file you uploaded was either not an image or a corrupted image.": 
                "Archivo no válido. Por favor, subí una imagen (JPG, PNG, WebP).",
                "This field is required.": "Este campo es obligatorio.",
                "Select a valid choice. That choice is not one of the available choices.": 
                "Selección no válida.",
            }

            for field, errors in form.errors.items():
                for error in errors:
                    msg_orig = str(error)
                    msg_traducido = traducciones.get(msg_orig, msg_orig)
                    nombre_campo = field.replace('_', ' ').capitalize()
                    messages.error(request, f"Error en {nombre_campo}: {msg_traducido}")
    else:
        # Si es GET, cargamos el formulario con los datos actuales
        form = ProductoForm(instance=producto)
    
    return render(request, 'productos/editar_producto.html', {
        'form': form,
        'producto': producto,
        'subcategoria': subcat_segura # Usamos esta variable para el botón "Volver" en el HTML
    })
@admin_required
@require_POST
def eliminar_foto_galeria(request, foto_id):
    """
    Función para eliminar una foto específica de la galería/portada
    """
    foto = get_object_or_404(ImagenProducto, id=foto_id)
    producto_id = foto.producto.id
    foto.delete()
    messages.success(request, "Foto eliminada de la galería.")
    return redirect('productos:editar_producto', prod_id=producto_id)
@admin_required
@require_POST
def eliminar_esquema_tecnico(request, prod_id):
    """
    Borra la imagen técnica del producto y deja el campo vacío.
    """
    producto = get_object_or_404(Producto, id=prod_id)
    
    if producto.imagen_tecnica:
        # Borramos el archivo físico del almacenamiento (opcional pero recomendado)
        producto.imagen_tecnica.delete(save=False) 
        # Limpiamos el campo en la base de datos
        producto.imagen_tecnica = None
        producto.save()
        messages.success(request, "Esquema técnico eliminado correctamente.")
    
    return redirect('productos:editar_producto', prod_id=prod_id)
@admin_required
@require_POST
def eliminar_producto(request, prod_id):
    producto = get_object_or_404(Producto, id=prod_id)
    subcat_id = producto.subcategoria.id if producto.subcategoria else None
    if tiene_ventas(producto=producto):
        # Borrarlo eliminaría ítems de pedidos y ventas ya hechos: se desactiva en su lugar
        producto.activo = False
        producto.save(update_fields=['activo'])
        messages.warning(
            request,
            f'"{producto.nombre}" tiene ventas registradas, así que no se puede borrar sin perder '
            'el historial. Lo desactivamos: ya no aparece en la tienda y podés reactivarlo desde Editar producto.'
        )
    else:
        producto.delete()
        messages.success(request, 'Producto eliminado correctamente.')
    if subcat_id:
        return redirect('productos:productos_por_subcategoria', subcat_id=subcat_id)
    return redirect('productos:gestion_productos')

# --- VARIANTES ---

@admin_required
@require_POST
def eliminar_variante(request, variante_id):
    variante = get_object_or_404(Variante, id=variante_id)
    producto = variante.producto
    producto_id = producto.id
    if tiene_ventas(variante=variante):
        # Borrarlo eliminaría ítems de pedidos y ventas ya hechos: se desactiva en su lugar
        variante.activa = False
        variante.save(update_fields=['activa'])
        recalcular_stock_producto(producto)
        messages.warning(
            request,
            f'El talle {variante.talle.nombre} tiene ventas registradas, así que no se puede borrar sin '
            'perder el historial. Lo desactivamos: ya no se ofrece en la tienda.'
        )
        return redirect('productos:editar_producto', prod_id=producto_id)
    variante.delete()
    recalcular_stock_producto(producto)
    messages.success(request, 'Variante eliminada correctamente.')
    return redirect('productos:editar_producto', prod_id=producto_id)

# --- API AJAX ---

@admin_required
def api_subcategorias(request, categoria_id):
    subcategorias = Subcategoria.objects.filter(categoria_id=categoria_id, activa=True).order_by('nombre')
    data = [{'id': s.id, 'nombre': s.nombre} for s in subcategorias]
    return JsonResponse(data, safe=False)

@admin_required
@require_POST
def api_crear_categoria(request):
    nombre = request.POST.get('nombre', '').strip()
    if not nombre:
        return JsonResponse({'success': False, 'error': 'Ingresá un nombre para la categoría'})
    if Categoria.objects.filter(nombre__iexact=nombre).exists():
        return JsonResponse({'success': False, 'error': f'Ya tenés una categoría llamada "{nombre}". Elegí otro nombre.'})
    categoria = Categoria.objects.create(nombre=nombre, activa=True)
    return JsonResponse({'success': True, 'id': categoria.id, 'nombre': categoria.nombre})

@admin_required
@require_POST
def api_crear_subcategoria(request):
    nombre = request.POST.get('nombre', '').strip()
    categoria_id = request.POST.get('categoria_id')
    if not nombre:
        return JsonResponse({'success': False, 'error': 'Ingresá un nombre para la subcategoría'})
    if not categoria_id:
        return JsonResponse({'success': False, 'error': 'Seleccioná una categoría primero'})
    categoria = get_object_or_404(Categoria, id=categoria_id, activa=True)
    if Subcategoria.objects.filter(nombre__iexact=nombre, categoria=categoria).exists():
        return JsonResponse({'success': False, 'error': f'Ya tenés una subcategoría "{nombre}" en {categoria.nombre}. Elegí otro nombre.'})
    subcategoria = Subcategoria.objects.create(nombre=nombre, categoria=categoria, activa=True)
    return JsonResponse({'success': True, 'id': subcategoria.id, 'nombre': subcategoria.nombre})

# --- CATEGORÍAS Y SUBCATEGORÍAS ---

@admin_required
def agregar_categoria(request):
    if request.method == 'POST':
        form = CategoriaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Categoría agregada.')
            return redirect('productos:gestion_productos')
        else:
            # El motivo real (ej. "Ya existe una categoría con ese nombre.") en vez de un mensaje genérico
            for errores in form.errors.values():
                for error in errores:
                    messages.error(request, error)
            return render(request, 'productos/agregar_categoria.html', {'form': form})
    form = CategoriaForm()
    return render(request, 'productos/agregar_categoria.html', {'form': form})

@admin_required
@require_POST
def eliminar_categoria(request, cat_id):
    categoria = get_object_or_404(Categoria, id=cat_id)
    tiene_productos = Producto.objects.filter(categoria=categoria).exists()
    tiene_subcategorias = Subcategoria.objects.filter(categoria=categoria).exists()
    if tiene_productos or tiene_subcategorias:
        messages.error(request, "No se puede eliminar la categoría porque tiene productos o subcategorías asociadas.")
    else:
        categoria.delete()
        messages.success(request, "Categoría eliminada correctamente.")
    return redirect('productos:gestion_productos')
@admin_required
def agregar_subcategoria(request):
    if request.method == 'POST':
        form = SubcategoriaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Subcategoría agregada.')
        else:
            mensaje = 'Por favor revisa los datos ingresados.'
    form = SubcategoriaForm()
    subcategorias = Subcategoria.objects.select_related('categoria').filter(activa=True).order_by('categoria__nombre', 'nombre')
    return render(request, 'productos/agregar_subcategoria.html', {'form': form, 'subcategorias': subcategorias})

@admin_required
def gestion_subcategorias(request, cat_id):
    categoria = get_object_or_404(Categoria, id=cat_id, activa=True)
    if request.method == 'POST':
        form = SubcategoriaSoloNombreForm(request.POST, categoria=categoria)
        if form.is_valid():
            subcat = form.save(commit=False)
            subcat.categoria = categoria
            subcat.save()
            messages.success(request, 'Subcategoría agregada.')
            form = SubcategoriaSoloNombreForm(categoria=categoria)
        else:
            if 'nombre' in form.errors and 'Ya existe una subcategoría' in str(form.errors['nombre']):
                mensaje = form.errors['nombre'][0]
            else:
                mensaje = 'Por favor revisa los datos ingresados.'
            # Antes el mensaje se calculaba pero no se mostraba: la página recargaba sin aviso
            messages.error(request, mensaje)
    else:
        form = SubcategoriaSoloNombreForm(categoria=categoria)
    subcategorias = categoria.subcategorias.all().order_by('nombre')
    return render(request, 'productos/gestion_subcategorias.html', {'categoria': categoria, 'form': form, 'subcategorias': subcategorias})

@admin_required
@require_POST
def eliminar_subcategoria(request, subcat_id):
    subcategoria = get_object_or_404(Subcategoria, id=subcat_id)
    cantidad_productos = Producto.objects.filter(subcategoria=subcategoria).count()
    if cantidad_productos:
        messages.error(
            request,
            f'No se puede eliminar la subcategoría "{subcategoria.nombre}" porque tiene '
            f'{cantidad_productos} producto(s). Movelos a otra subcategoría o eliminalos primero.'
        )
    else:
        subcategoria.delete()
        messages.success(request, "Subcategoría eliminada.")
    return redirect(request.META.get('HTTP_REFERER', 'productos:gestion_productos'))

# --- PROVEEDORES (RESTURADO) ---

@admin_required
def agregar_proveedor(request):
    mensaje = None
    mensaje_error = False
    edit_form = None
    edit_id = request.GET.get('edit')

    if request.method == "POST" and "edit_id" in request.POST:
        proveedor = get_object_or_404(Proveedor, id=request.POST["edit_id"])
        edit_form = ProveedorForm(request.POST, instance=proveedor)
        if edit_form.is_valid():
            edit_form.save()
            mensaje = "Proveedor actualizado correctamente."
            edit_form = None
            edit_id = None
        else:
            mensaje = "Por favor revisa los datos ingresados."
        form = ProveedorForm()
    elif request.method == "POST" and "delete_id" in request.POST:
        proveedor = get_object_or_404(Proveedor, id=request.POST["delete_id"])
        cantidad_productos = Producto.objects.filter(proveedor=proveedor).count()
        if cantidad_productos:
            mensaje = (
                f'No se puede eliminar el proveedor "{proveedor.nombre}" porque tiene '
                f'{cantidad_productos} producto(s) asociados. Asigná otro proveedor a esos productos primero.'
            )
            mensaje_error = True
        else:
            proveedor.delete()
            mensaje = "Proveedor eliminado correctamente."
        form = ProveedorForm()
    elif request.method == "POST":
        form = ProveedorForm(request.POST)
        if form.is_valid():
            if Proveedor.objects.filter(telefono=form.cleaned_data["telefono"]).exists():
                mensaje = "Ya existe un proveedor con ese teléfono."
            else:
                form.save()
                mensaje = "Proveedor agregado correctamente."
                form = ProveedorForm()
    else:
        form = ProveedorForm()

    if edit_id and not edit_form:
        proveedor = get_object_or_404(Proveedor, id=edit_id)
        edit_form = ProveedorForm(instance=proveedor)

    proveedores_list = Proveedor.objects.all().order_by("-created_at")
    paginator = Paginator(proveedores_list, 10)
    page_number = request.GET.get("page")
    proveedores = paginator.get_page(page_number)

    return render(request, "productos/agregar_proveedor.html", {"form": form, "mensaje": mensaje, "mensaje_error": mensaje_error, "proveedores": proveedores, "edit_form": edit_form, "edit_id": edit_id})


@admin_required
@require_POST
def crear_proveedor_ajax(request):
    form = ProveedorForm(request.POST)
    if not form.is_valid():
        return JsonResponse({
            'success': False,
            'errors': {field: [str(error) for error in errors] for field, errors in form.errors.items()},
        }, status=400)

    telefono = form.cleaned_data["telefono"]
    if Proveedor.objects.filter(telefono=telefono).exists():
        return JsonResponse({
            'success': False,
            'errors': {'telefono': ['Ya existe un proveedor con ese teléfono.']},
        }, status=400)

    proveedor = form.save()
    return JsonResponse({
        'success': True,
        'proveedor': {
            'id': proveedor.id,
            'nombre': proveedor.nombre,
            'telefono': proveedor.telefono,
        }
    })

@admin_required
def editar_proveedor(request, proveedor_id):
    proveedor = get_object_or_404(Proveedor, id=proveedor_id)
    mensaje = None
    if request.method == 'POST':
        form = ProveedorForm(request.POST, instance=proveedor)
        if form.is_valid():
            form.save()
            mensaje = 'Proveedor actualizado correctamente.'
        else:
            mensaje = 'Por favor revisa los datos ingresados.'
    else:
        form = ProveedorForm(instance=proveedor)
    return render(request, 'productos/editar_proveedor.html', {'form': form, 'mensaje': mensaje, 'proveedor': proveedor})

# --- MEDIDAS ---

@admin_required
def gestion_medidas(request):
    mensaje = None
    if request.method == 'POST':
        form = TipoMedidaForm(request.POST)
        if form.is_valid():
            form.save()
            mensaje = 'Medida agregada correctamente.'
            form = TipoMedidaForm()
        else:
            mensaje = ' '.join(error for errores in form.errors.values() for error in errores) or 'Por favor revisa los datos ingresados.'
    else:
        form = TipoMedidaForm()
    medidas = TipoMedida.objects.all().order_by('nombre')
    return render(request, 'productos/gestion_medidas.html', {'form': form, 'mensaje': mensaje, 'medidas': medidas})

# --- AJAX ---

@admin_required
def obtener_detalle_producto_ajax(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id)
    imagenes = [{'url': img.imagen.url} for img in producto.imagenes.all()]
    if not imagenes:
        # El placeholder png nunca existió (404): recuadro gris con ícono, en línea
        imagenes = [{'url': (
            "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='400' height='500' viewBox='0 0 400 500'>"
            "<rect width='400' height='500' fill='%23f3ede4'/><text x='200' y='260' font-family='sans-serif' font-size='28' "
            "fill='%23b8a48a' text-anchor='middle'>Sin foto</text></svg>"
        )}]
    html_ficha_tecnica = render_to_string('productos/_snippet_ficha_tecnica_render.html', {'producto': producto})
    
    return JsonResponse({
        'id': producto.id, 'nombre': producto.nombre, 'codigo': producto.codigo,
        'tipo': producto.tipo, 'precio': pesos_numero(producto.precio), 'stock': producto.stock,
        'activo': producto.activo, 'imagenes': imagenes, 'ficha_tecnica_html': html_ficha_tecnica,
        'url_editar': reverse('productos:editar_producto', args=[producto.id]),
        'url_eliminar': reverse('productos:eliminar_producto', args=[producto.id]),
        'url_publico': reverse('productos:detalle_producto', args=[producto.id]),
    })
@admin_required
@require_POST
def actualizar_variante_ajax(request):
    """
    Vista AJAX para actualizar stock y precio de una variante individualmente.
    """
    try:
        data = json.loads(request.body)
        variante_id = data.get('id')
        nuevo_stock = data.get('stock')
        nuevo_precio = data.get('precio')

        variante = get_object_or_404(Variante, id=variante_id)

        try:
            stock_valor = int(nuevo_stock)
            precio_valor = Decimal(str(nuevo_precio))
        except (TypeError, ValueError, InvalidOperation):
            return JsonResponse({'status': 'error', 'mensaje': 'Stock o precio inválidos.'}, status=400)
        if stock_valor < 0 or precio_valor <= 0:
            return JsonResponse({'status': 'error', 'mensaje': 'El stock no puede ser negativo y el precio tiene que ser mayor a 0.'}, status=400)

        # Actualizamos los campos
        variante.stock = stock_valor
        variante.precio = precio_valor
        variante.save()
        stock_total = recalcular_stock_producto(variante.producto)

        return JsonResponse({'status': 'ok', 'mensaje': 'Variante actualizada.', 'stock_total': stock_total})
    
    except Exception as e:
        return JsonResponse({'status': 'error', 'mensaje': str(e)}, status=400)
from .forms import VarianteForm # Importá el formulario nuevo

from .models import Color, Medida # Chequeá que estén importados arriba

@require_http_methods(["GET"])
def obtener_tabla_medidas_ajax(request, producto_id):
    """
    Endpoint público AJAX que devuelve la tabla de medidas de un producto.
    Para que el visitante pueda ver las medidas correctas antes de comprar.
    """
    try:
        producto = get_object_or_404(Producto, id=producto_id, activo=True)
        variantes = producto.variantes.filter(activa=True).prefetch_related('medidas', 'talle')
        
        if not variantes.exists():
            return JsonResponse({
                'status': 'info',
                'mensaje': 'Este producto no tiene variantes con medidas disponibles.',
                'tabla_html': ''
            })
        
        # Construir la tabla HTML
        filas_medidas = sum(variante.medidas.count() for variante in variantes)
        tabla_html = render_to_string('productos/_tabla_medidas.html', {
            'producto': producto,
            'variantes': variantes,
            'filas_medidas': filas_medidas,
        })
        
        return JsonResponse({
            'status': 'ok',
            'producto_nombre': producto.nombre,
            'tabla_html': tabla_html,
        })
    
    except Http404:
        return JsonResponse({
            'status': 'error',
            'mensaje': 'Este producto ya no está disponible.'
        }, status=404)
    except Exception:
        return JsonResponse({
            'status': 'error',
            'mensaje': 'No pudimos cargar las medidas. Probá de nuevo.'
        }, status=400)


@admin_required
def editar_variante(request, variante_id):
    variante = get_object_or_404(Variante, id=variante_id)
    producto = variante.producto
    talle_original_id = variante.talle_id
    colores_originales_ids = list(variante.colores.values_list('id', flat=True))

    if request.method == 'POST':
        error_medidas = error_en_medidas(request)
        if error_medidas:
            messages.error(request, error_medidas)
            return redirect('productos:editar_variante', variante_id=variante.id)

        # Actualizar talle
        talle_nombre = request.POST.get('talle_nombre', '').strip()
        if talle_nombre:
            if producto.variantes.filter(talle__nombre__iexact=talle_nombre).exclude(id=variante.id).exists():
                messages.error(request, f'El producto ya tiene otro talle {talle_nombre}. Elegí un nombre distinto.')
                return redirect('productos:editar_variante', variante_id=variante.id)
            talle_obj = obtener_talle(talle_nombre)
            variante.talle = talle_obj

        # Actualizar stock
        try:
            variante.stock = max(int(request.POST.get('stock') or 0), 0)
        except (TypeError, ValueError):
            variante.stock = 0
        variante.save()

        # Recalcular stock del producto
        recalcular_stock_producto(producto)

        var_editada = variante

        # 1. CAPTURAR Y GUARDAR COLORES (múltiples, cada uno con su stock)
        colores_form = leer_colores_con_stock(request)
        stock_por_color = {}
        if colores_form:
            colores_objs = []
            for dato_color in colores_form:
                color_obj = color_desde_form(dato_color['nombre'], dato_color['hex'], producto=producto)
                colores_objs.append(color_obj)
                stock_por_color[color_obj.id] = dato_color['stock']
            var_editada.colores.set(colores_objs)
        else:
            var_editada.colores.clear()

        # 2. CAPTURAR Y GUARDAR MEDIDAS (múltiples)
        limpiar_decimal = medida_a_decimal  # ya validadas arriba

        medidas_ids = request.POST.getlist('medida_id')
        altos = request.POST.getlist('alto')
        anchos = request.POST.getlist('ancho')
        largos = request.POST.getlist('largo')
        tiros = request.POST.getlist('tiro')

        medidas_a_mantener = []
        for i, medida_id in enumerate(medidas_ids):
            if medida_id:  # Medida existente
                try:
                    medida = Medida.objects.get(id=medida_id)
                    medida.alto = limpiar_decimal(altos[i])
                    medida.ancho = limpiar_decimal(anchos[i])
                    medida.largo = limpiar_decimal(largos[i])
                    medida.tiro = limpiar_decimal(tiros[i])
                    medida.save()
                    medidas_a_mantener.append(medida)
                except Medida.DoesNotExist:
                    pass
            else:  # Nueva medida
                if altos[i] or anchos[i] or largos[i] or tiros[i]:
                    medida = Medida.objects.create(
                        alto=limpiar_decimal(altos[i]),
                        ancho=limpiar_decimal(anchos[i]),
                        largo=limpiar_decimal(largos[i]),
                        tiro=limpiar_decimal(tiros[i])
                    )
                    medidas_a_mantener.append(medida)

        var_editada.medidas.set(medidas_a_mantener)

        if variante_debe_regenerar_qr(var_editada, talle_original_id, colores_originales_ids):
            sincronizar_qrs_variante_color(var_editada, regenerar_qr=True)
        else:
            sincronizar_qrs_variante_color(var_editada)

        # Stock por color cargado en el form; con colores, el talle queda en la suma
        for vc in VarianteColor.objects.filter(variante=var_editada):
            if vc.color_id in stock_por_color:
                vc.stock = stock_por_color[vc.color_id]
                vc.save(update_fields=['stock'])
        sincronizar_stock_variante(var_editada)

        messages.success(request, f"Talle {variante.talle.nombre} actualizado correctamente.")
        return redirect('productos:editar_producto', prod_id=producto.id)

    form = VarianteForm(instance=variante)
    
    # Pasamos los datos actuales para rellenar los inputs
    if usa_stock_por_color(variante):
        stock_colores = {vc.color_id: vc.stock for vc in VarianteColor.objects.filter(variante=variante)}
    else:
        # Talle con colores pero todavía sin stock por color: se propone el stock del talle
        # repartido entre sus colores (si no, el form muestra 0 y al guardar se pierde el stock)
        stock_colores = repartir_stock_en_colores(variante.stock, variante.colores.all())
    colores_stock = [
        {'color': color, 'stock': stock_colores.get(color.id, 0)}
        for color in variante.colores.all()
    ]

    return render(request, 'productos/editar_variante.html', {
        'form': form,
        'variante': variante,
        'producto': producto,
        'colores_stock': colores_stock,
        'color_actual': variante.colores.first(),
        'medidas': variante.medidas.all()
    })


@admin_required
def agregar_variante(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id)

    if request.method == 'POST':
        talle_nombre = request.POST.get('talle_nombre', '').strip() or 'Sin talle'
        error_form = error_en_medidas(request)
        if not error_form and producto.variantes.filter(talle__nombre__iexact=talle_nombre).exists():
            error_form = f'El producto ya tiene el talle {talle_nombre}. Cambiá el nombre o editalo desde la lista de talles.'
        if error_form:
            messages.error(request, error_form)
            # Se vuelve a mostrar el form con lo cargado (colores, stock y medidas), sin redirect
            medidas_previas = [
                {'alto': alto, 'ancho': ancho, 'largo': largo, 'tiro': tiro}
                for alto, ancho, largo, tiro in zip(
                    request.POST.getlist('alto'), request.POST.getlist('ancho'),
                    request.POST.getlist('largo'), request.POST.getlist('tiro'),
                )
                if alto or ancho or largo or tiro
            ]
            return render(request, 'productos/agregar_variante.html', {
                'producto': producto,
                'previo': {
                    'talle_nombre': talle_nombre,
                    'stock': request.POST.get('stock') or '0',
                    'colores': leer_colores_con_stock(request),
                    'medidas': medidas_previas,
                },
            })
        talle_obj = obtener_talle(talle_nombre)

        try:
            stock_variante = max(int(request.POST.get('stock') or 0), 0)
        except (TypeError, ValueError):
            stock_variante = 0

        nueva_variante = Variante.objects.create(
            producto=producto,
            talle=talle_obj,
            stock=stock_variante,
            precio=producto.precio or 0,
            qr_code=str(uuid.uuid4())
        )

        # Cada color se guarda con su propio stock; el del talle es la suma
        for dato_color in leer_colores_con_stock(request):
            color_obj = color_desde_form(dato_color['nombre'], dato_color['hex'], producto=producto)
            nueva_variante.colores.add(color_obj)
            vc, _ = VarianteColor.objects.get_or_create(
                variante=nueva_variante,
                color=color_obj,
            )
            vc.stock = dato_color['stock']
            vc.activo = True
            vc.save()

        limpiar_decimal = medida_a_decimal  # ya validadas arriba

        medidas_ids = request.POST.getlist('medida_id')
        altos = request.POST.getlist('alto')
        anchos = request.POST.getlist('ancho')
        largos = request.POST.getlist('largo')
        tiros = request.POST.getlist('tiro')

        for i, medida_id in enumerate(medidas_ids):
            if altos[i] or anchos[i] or largos[i] or tiros[i]:
                medida = Medida.objects.create(
                    alto=limpiar_decimal(altos[i]),
                    ancho=limpiar_decimal(anchos[i]),
                    largo=limpiar_decimal(largos[i]),
                    tiro=limpiar_decimal(tiros[i])
                )
                nueva_variante.medidas.add(medida)

        sincronizar_qrs_variante_color(nueva_variante)
        sincronizar_stock_variante(nueva_variante)
        recalcular_stock_producto(producto)

        messages.success(request, f"Talle {talle_nombre} agregado correctamente.")
        return redirect('productos:editar_producto', prod_id=producto.id)

    return render(request, 'productos/agregar_variante.html', {
        'producto': producto,
    })


# --- VISTAS QR ---


# Uso interno (ventas presenciales / QRs): solo admin
@admin_required
def variante_color_qr(request, vc_id):
    """Devuelve la imagen QR de una VarianteColor específica."""
    variante_color = get_object_or_404(VarianteColor, id=vc_id)
    buffer = variante_color.generar_qr_image()
    return HttpResponse(buffer.getvalue(), content_type='image/png')


@admin_required
def producto_qrs_impresion(request, producto_id):
    """Vista de impresión masiva de todos los QRs de un producto."""
    producto = get_object_or_404(Producto, id=producto_id)
    volver_url = reverse('productos:gestion_productos')
    if producto.subcategoria_id:
        volver_url = f"{reverse('productos:productos_por_subcategoria', args=[producto.subcategoria_id])}?preview={producto.id}"

    # Generar VarianteColor automáticamente si no existen y revalidar la sincronización de QR
    variantes = producto.variantes.filter(activa=True).prefetch_related('colores')
    talles_repartidos = []
    for variante in variantes:
        cantidad_colores = variante.colores.count()
        sin_registros = not VarianteColor.objects.filter(variante=variante).exists()
        sincronizar_qrs_variante_color(variante)
        if sin_registros and cantidad_colores > 1 and variante.stock > 0:
            talles_repartidos.append(variante.talle.nombre)

    if talles_repartidos:
        messages.warning(
            request,
            'Se generaron los QR por color. El stock de los talles '
            f"{', '.join(talles_repartidos)} se repartió en partes iguales entre sus colores: "
            'revisalo en Editar producto.'
        )

    variantes_color = VarianteColor.objects.filter(
        variante__producto=producto,
        activo=True
    ).select_related('variante__talle', 'color').order_by('variante__talle__nombre', 'color__nombre')

    return render(request, 'productos/qrs_impresion.html', {
        'producto': producto,
        'variantes_color': variantes_color,
        'volver_url': volver_url,
    })

# Uso interno (ventas presenciales / QRs): solo admin
@admin_required
def buscar_productos(request):

    q = request.GET.get('q', '').strip()
    data = []

    if q:
        variante_color = None
        variante = Variante.objects.filter(
            qr_code=q,
            activa=True,
            stock__gt=0,
            producto__activo=True
        ).select_related('producto', 'talle').first()

        if not variante:
            # Etiqueta QR: IG-<codigo>-<talle>-<color>-<primeros 8 caracteres del qr_code>.
            # Solo se busca por QR si la lectura está completa; un fragmento vacío o parcial
            # (mientras el lector todavía está "tipeando") coincidía con cualquier color.
            if q.upper().startswith('IG-'):
                match = re.search(r'-([0-9a-fA-F]{8})$', q)
                qr_fragment = match.group(1).lower() if match else None
            elif re.fullmatch(r'[0-9a-fA-F-]{8,36}', q):
                qr_fragment = q.lower()
            else:
                qr_fragment = None

            if qr_fragment:
                variante_color = VarianteColor.objects.filter(
                    qr_code__startswith=qr_fragment,
                    activo=True,
                    variante__activa=True,
                    variante__stock__gt=0,
                    variante__producto__activo=True
                ).select_related('variante__producto', 'variante__talle', 'color').first()
            if variante_color:
                variante = variante_color.variante
            elif q.upper().startswith('IG-'):
                # Lectura de QR incompleta o sin stock: no mezclar con la búsqueda por nombre
                return JsonResponse([], safe=False)

        if variante:
            producto = variante.producto
            return JsonResponse([{
                'id': producto.id,
                'nombre': producto.nombre,
                'codigo': producto.codigo,
                'auto_select': True,
                'scanned_variante_id': variante.id,
                'scanned_color': variante_color.color.nombre if variante_color else '',
            }], safe=False)

    productos = Producto.objects.filter(
        (Q(nombre__icontains=q) | Q(codigo__icontains=q)),
        activo=True
    ).annotate(
        stock_disponible=Sum(
            'variantes__stock',
            filter=Q(variantes__activa=True)
        )
    ).filter(
        stock_disponible__gt=0
    ).distinct()[:5]

    for producto in productos:

        data.append({

            'id': producto.id,

            'nombre': producto.nombre,

            'codigo': producto.codigo

        })

    return JsonResponse(data, safe=False)

# Uso interno (ventas presenciales / QRs): solo admin
@admin_required
def obtener_variantes_producto(request, producto_id):
    from decimal import Decimal

    producto = get_object_or_404(
        Producto,
        id=producto_id
    )

    # Calcular descuento si hay oferta activa
    oferta = producto.obtener_oferta_activa()
    descuento = Decimal(oferta.descuento) / Decimal(100) if oferta else Decimal(0)

    variantes = producto.variantes.filter(
        activa=True,
        stock__gt=0
    ).prefetch_related(
        'colores',
        'variante_colores__color',
    )

    data = []

    for variante in variantes:

        colores = []
        colores_con_stock = [vc for vc in variante.variante_colores.all() if vc.activo]

        if colores_con_stock:
            # El talle tiene stock por color: se informa el stock de cada color
            for vc in colores_con_stock:
                colores.append({
                    'nombre': vc.color.nombre,
                    'hex': normalizar_hex_color(vc.color.nombre, vc.color.codigo_hex),
                    'stock': vc.stock,
                })
        else:
            for color in variante.colores.all():
                colores.append({
                    'nombre': color.nombre,
                    'hex': normalizar_hex_color(color.nombre, color.codigo_hex),
                    'stock': None,
                })

        # El precio publicado es el del producto (el del talle solo si el producto no tiene)
        precio_base = producto.precio or variante.precio
        # Aplicar descuento al precio
        precio_final = float(precio_base * (1 - descuento))

        data.append({

            'id': variante.id,

            'talle': variante.talle.nombre,

            'colores': colores,

            'stock': variante.stock,

            'precio': precio_final

        })

    return JsonResponse({
        'variantes': data,
        'stock_total': sum(variante['stock'] for variante in data),
    })


# --- CATEGORÍAS DE ORDEN ---

@admin_required
def gestion_categorias_orden(request):
    categorias = CategoriaOrden.objects.all().order_by('-created_at')
    return render(request, 'productos/gestion_categorias_orden.html', {'categorias': categorias})


@admin_required
def crear_categoria_orden(request):
    if request.method == 'POST':
        form = CategoriaOrdenForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Categoría de orden creada correctamente.')
            return redirect('productos:gestion_categorias_orden')
    else:
        form = CategoriaOrdenForm()
    return render(request, 'productos/crear_categoria_orden.html', {'form': form})


@admin_required
def editar_categoria_orden(request, cat_id):
    categoria = get_object_or_404(CategoriaOrden, id=cat_id)
    if request.method == 'POST':
        form = CategoriaOrdenForm(request.POST, instance=categoria)
        if form.is_valid():
            form.save()
            messages.success(request, 'Categoría de orden actualizada.')
            return redirect('productos:gestion_categorias_orden')
    else:
        form = CategoriaOrdenForm(instance=categoria)
    return render(request, 'productos/crear_categoria_orden.html', {'form': form, 'categoria': categoria})


@admin_required
@require_POST
def eliminar_categoria_orden(request, cat_id):
    categoria = get_object_or_404(CategoriaOrden, id=cat_id)
    categoria.delete()
    messages.success(request, 'Categoría de orden eliminada.')
    return redirect('productos:gestion_categorias_orden')


@admin_required
@require_POST
def toggle_categoria_orden(request, cat_id):
    categoria = get_object_or_404(CategoriaOrden, id=cat_id)
    categoria.activo = not categoria.activo
    categoria.save()
    estado = 'activada' if categoria.activo else 'desactivada'
    messages.success(request, f'Categoría "{categoria.nombre}" {estado}.')
    return redirect('productos:gestion_categorias_orden')


@admin_required
def gestionar_productos_categoria_orden(request, cat_id):
    categoria = get_object_or_404(CategoriaOrden, id=cat_id)
    productos_en_categoria = CategoriaOrdenProducto.objects.filter(
        categoria_orden=categoria
    ).select_related('producto')
    productos_ids = productos_en_categoria.values_list('producto_id', flat=True)
    productos_disponibles = Producto.objects.filter(activo=True).exclude(id__in=productos_ids).order_by('nombre')

    if request.method == 'POST':
        action = request.POST.get('action')
        producto_id = request.POST.get('producto_id')

        if action == 'agregar' and producto_id:
            producto = get_object_or_404(Producto, id=producto_id)
            CategoriaOrdenProducto.objects.get_or_create(
                categoria_orden=categoria,
                producto=producto
            )
            messages.success(request, f'Producto "{producto.nombre}" agregado.')

        elif action == 'quitar' and producto_id:
            CategoriaOrdenProducto.objects.filter(
                categoria_orden=categoria,
                producto_id=producto_id
            ).delete()
            messages.success(request, 'Producto quitado de la categoría.')

        return redirect('productos:gestionar_productos_categoria_orden', cat_id=cat_id)

    return render(request, 'productos/gestionar_productos_categoria_orden.html', {
        'categoria': categoria,
        'productos_en_categoria': productos_en_categoria,
        'productos_disponibles': productos_disponibles,
    })
def obtener_oferta_activa(self):

    oferta_producto = Oferta.objects.filter(
        activa=True,
        es_cupon=False,
        productos=self
    ).first()

    if oferta_producto:
        return oferta_producto

    oferta_categoria = Oferta.objects.filter(
        activa=True,
        es_cupon=False,
        categoria=self.categoria
    ).first()

    if oferta_categoria:
        return oferta_categoria

    oferta_global = Oferta.objects.filter(
        activa=True,
        es_cupon=False,
        aplicar_a_todos=True
    ).first()

    if oferta_global:
        return oferta_global

    return None


@property
def precio_final(self):

    oferta = self.obtener_oferta_activa()

    if not oferta:
        return self.precio

    descuento = (
        Decimal(oferta.descuento) / Decimal(100)
    )

    return self.precio * (1 - descuento)
@admin_required
def admin_ofertas(request):

    ofertas = Oferta.objects.all().order_by('-id')
    productos = Producto.objects.filter(activo=True)
    categorias = Categoria.objects.filter(activa=True).order_by('nombre')

    if request.method == 'POST':

        nombre = request.POST.get('nombre')
        descuento = request.POST.get('descuento')
        tipo_oferta = request.POST.get('tipo_oferta', 'catalogo')
        codigo = request.POST.get('codigo', '').strip().upper()

        try:
            descuento_numero = int(descuento)
        except (TypeError, ValueError):
            messages.error(request, 'El descuento debe ser un numero.')
            return redirect('productos:admin_ofertas')

        if descuento_numero < 1 or descuento_numero > 100:
            messages.error(request, 'El descuento debe estar entre 1 y 100.')
            return redirect('productos:admin_ofertas')

        if tipo_oferta == 'cupon':
            if not codigo:
                messages.error(request, 'Carga un codigo para el cupon.')
                return redirect('productos:admin_ofertas')
            if Oferta.objects.filter(codigo__iexact=codigo).exists():
                messages.error(request, 'Ya existe una oferta con ese codigo.')
                return redirect('productos:admin_ofertas')

            # Procesar límite de usos
            limite_usos = request.POST.get('limite_usos', '').strip()
            limite_usos_valor = None
            if limite_usos:
                try:
                    limite_usos_valor = int(limite_usos)
                    if limite_usos_valor < 1:
                        limite_usos_valor = None
                except (TypeError, ValueError):
                    limite_usos_valor = None

            # Procesar fecha límite
            fecha_fin = request.POST.get('fecha_fin', '').strip()
            fecha_fin_valor = None
            if fecha_fin:
                try:
                    from datetime import datetime
                    from django.utils import timezone
                    # "Hasta el 08/10" incluye todo ese día
                    fecha_fin_valor = timezone.make_aware(
                        datetime.strptime(fecha_fin, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
                    )
                except (TypeError, ValueError):
                    fecha_fin_valor = None

            Oferta.objects.create(
                nombre=nombre,
                descuento=descuento_numero,
                codigo=codigo,
                es_cupon=True,
                activa=True,
                limite_usos=limite_usos_valor,
                fecha_fin=fecha_fin_valor
            )

            messages.success(request, 'Codigo de descuento creado correctamente.')
            return redirect('productos:admin_ofertas')

        alcance = request.POST.get('alcance', 'productos')
        aplicar_a_todos = alcance == 'todos'
        categoria = None

        if alcance == 'categoria':
            categoria_id = request.POST.get('categoria')
            if not str(categoria_id or '').isdigit():
                messages.error(request, 'Elegí la categoría a la que se aplica la oferta.')
                return redirect('productos:admin_ofertas')
            categoria = get_object_or_404(Categoria, id=categoria_id, activa=True)

        oferta = Oferta.objects.create(
            nombre=nombre,
            descuento=descuento_numero,
            aplicar_a_todos=aplicar_a_todos,
            categoria=categoria,
            activa=True
        )

        if alcance == 'productos':
            productos_ids = request.POST.getlist('productos')

            oferta.productos.set(productos_ids)

        return redirect('productos:admin_ofertas')

    context = {
        'ofertas': ofertas,
        'productos': productos,
        'categorias': categorias,
    }

    return render(
        request,
        'productos/admin_ofertas.html',
        context
    )
@admin_required
@require_POST
def toggle_oferta(request, oferta_id):

    oferta = get_object_or_404(
        Oferta,
        id=oferta_id
    )

    oferta.activa = not oferta.activa
    oferta.save()

    return redirect('productos:admin_ofertas')
