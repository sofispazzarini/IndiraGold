import json
import uuid
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST, require_http_methods
from django.urls import reverse
from django.shortcuts import redirect, get_object_or_404, render
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from django.core.paginator import Paginator
from django.http import JsonResponse

from .models import (
    Subcategoria, Producto, Talle, Color, Medida,
    Variante, Proveedor, ImagenProducto, Categoria, TipoMedida,
    VarianteColor, CategoriaOrden, CategoriaOrdenProducto, Oferta
)
from .forms import (
    ProductoForm, SubcategoriaForm, CategoriaForm,
    TipoMedidaForm, ProveedorForm, SubcategoriaSoloNombreForm,
    CategoriaOrdenForm
)
from django.db.models import Q, Sum
from decimal import Decimal
from django.utils import timezone


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
    'marron': '#a52a2a',
    'café': '#a52a2a',
    'beige': '#d2b48c',
    'turquesa': '#40e0d0',
}


def normalizar_hex_color(nombre, codigo_hex=None):
    nombre_limpio = (nombre or '').strip().lower()
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
    colores_nuevos_ids = set(variante.colores.values_list('id', flat=True))
    return variante.talle_id != talle_original_id or colores_nuevos_ids != set(colores_originales_ids)


def sincronizar_qrs_variante_color(variante, regenerar_qr=False):
    """Mantiene los registros VarianteColor sincronizados con los colores actuales de la variante.

    Si regenerar_qr=True, reasigna el qr_code de los registros existentes para
    forzar la reimpresión de los QR después de cambios en el producto.
    """
    colores_actuales = list(variante.colores.all())

    registros_actuales = list(VarianteColor.objects.filter(variante=variante).select_related('color'))
    ids_nuevos = {color.id for color in colores_actuales}

    para_borrar = [vc for vc in registros_actuales if vc.color_id not in ids_nuevos]
    for vc in para_borrar:
        vc.delete()

    for color in colores_actuales:
        vc, created = VarianteColor.objects.get_or_create(
            variante=variante,
            color=color,
            defaults={'activo': True}
        )
        if created or regenerar_qr or not vc.qr_code:
            vc.qr_code = str(uuid.uuid4())
            vc.save(update_fields=['qr_code'])

    for vc in VarianteColor.objects.filter(variante=variante).select_related('color'):
        if regenerar_qr or not vc.qr_code:
            vc.qr_code = str(uuid.uuid4())
            vc.save(update_fields=['qr_code'])

    return VarianteColor.objects.filter(variante=variante, activo=True).select_related('color')

# --- DECORADOR AUXILIAR ---
def admin_required(view_func):
    return login_required(user_passes_test(lambda u: u.is_superuser)(view_func))

# --- VISTAS PÚBLICAS ---

def detalle_producto(request, producto_id):
    """
    Página pública de detalle de un producto.
    Muestra información completa, variantes, medidas y opción de compra.
    """
    producto = get_object_or_404(Producto, id=producto_id, activo=True)
    variantes = producto.variantes.filter(activa=True).select_related('talle').prefetch_related('colores', 'medidas')
    
    # Si no hay variantes activas, mostrar que ha sido descontinuado
    if not variantes.exists():
        variantes = []
    
    # Obtener productos relacionados de la misma subcategoría
    productos_relacionados = (
        Producto.objects
        .filter(subcategoria=producto.subcategoria, activo=True)
        .exclude(id=producto.id)
        .prefetch_related('imagenes')[:4]
    )
    
    context = {
        'producto': producto,
        'variantes': variantes,
        'variantes_data': [
            {
                'id': variante.id,
                'stock': variante.stock,
                'colores': [
                    {
                        'id': color.id,
                        'nombre': color.nombre,
                        'codigo_hex': normalizar_hex_color(color.nombre, color.codigo_hex),
                        'hex': normalizar_hex_color(color.nombre, color.codigo_hex),
                    }
                    for color in variante.colores.all()
                ],
            }
            for variante in variantes
        ],
        'productos_relacionados': productos_relacionados,
        'talles_disponibles': [v.talle for v in variantes],
    }
    
    return render(request, 'productos/producto_detalle.html', context)

# --- GESTIÓN DE PRODUCTOS Y NAVEGACIÓN ---

@admin_required
def gestion_productos(request):
    categories = Categoria.objects.filter(activa=True).order_by('nombre')
    return render(request, 'productos/gestion_productos.html', {'categories': categories})

@admin_required
def lista_subcategorias(request, categoria_id):
    categoria = get_object_or_404(Categoria, id=categoria_id)
    subcategorias = Subcategoria.objects.filter(categoria=categoria, activa=True)
    return render(request, 'productos/lista_subcategorias.html', {
        'categoria': categoria,
        'subcategorias': subcategorias
    })

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

        if len(imagenes_galeria) > 5:
            messages.error(request, "Máximo 5 imágenes de galería permitidas.")
        elif form.is_valid():
            producto = form.save(commit=False)
            producto.subcategoria = subcategoria
            producto.categoria = categoria_padre
            producto.activo = True
            producto.stock = 0
            producto.save()
            for img in imagenes_galeria:
                ImagenProducto.objects.create(producto=producto, imagen=img)

            if variantes_json:
                variantes_list = json.loads(variantes_json)
                stock_total = 0
                for v in variantes_list:
                    talle_nombre = (v.get('talle') or '').strip() or 'Sin talle'
                    talle_obj, _ = Talle.objects.get_or_create(nombre=talle_nombre)
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
                        if nombre_color:
                            color_obj, created = Color.objects.get_or_create(
                                nombre=nombre_color,
                                defaults={'codigo_hex': codigo_hex}
                            )
                            if not created and color_obj.codigo_hex != codigo_hex:
                                color_obj.codigo_hex = codigo_hex
                                color_obj.save()
                            nueva_variante.colores.add(color_obj)
                            VarianteColor.objects.get_or_create(
                                variante=nueva_variante,
                                color=color_obj,
                            )
                    
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
                producto.stock = stock_total
                producto.save(update_fields=['stock'])
            
            messages.success(request, 'Producto guardado correctamente.')
            return redirect('productos:productos_por_subcategoria', subcat_id=subcategoria.id)
    else:
        form = ProductoForm()
    todas_categorias = Categoria.objects.filter(activa=True).order_by('nombre')
    todas_subcategorias = Subcategoria.objects.filter(categoria=categoria_padre, activa=True).order_by('nombre')
    return render(request, 'productos/agregar_producto.html', {
        'form': form,
        'subcategoria': subcategoria,
        'proveedores': proveedores,
        'categoria': categoria_padre,
        'todas_categorias': todas_categorias,
        'todas_subcategorias': todas_subcategorias,
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

            for variante in producto_editado.variantes.all():
                stock_key = f'variante_stock_{variante.id}'
                if stock_key in request.POST:
                    try:
                        variante.stock = max(int(request.POST.get(stock_key) or 0), 0)
                        variante.save(update_fields=['stock'])
                    except ValueError:
                        messages.error(request, f"Stock inválido para {variante.talle.nombre}.")

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
def eliminar_producto(request, prod_id):
    producto = get_object_or_404(Producto, id=prod_id)
    subcat_id = producto.subcategoria.id if producto.subcategoria else None
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
            messages.error(request, 'Por favor revisa los datos ingresados.')
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
    else:
        form = SubcategoriaSoloNombreForm(categoria=categoria)
    subcategorias = categoria.subcategorias.all().order_by('nombre')
    return render(request, 'productos/gestion_subcategorias.html', {'categoria': categoria, 'form': form, 'subcategorias': subcategorias})

@admin_required
@require_POST
def eliminar_subcategoria(request, subcat_id):
    subcategoria = get_object_or_404(Subcategoria, id=subcat_id)
    subcategoria.delete()
    messages.success(request, "Subcategoría eliminada.")
    return redirect(request.META.get('HTTP_REFERER', 'productos:gestion_productos'))

# --- PROVEEDORES (RESTURADO) ---

@admin_required
def agregar_proveedor(request):
    mensaje = None
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

    return render(request, "productos/agregar_proveedor.html", {"form": form, "mensaje": mensaje, "proveedores": proveedores, "edit_form": edit_form, "edit_id": edit_id})


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
            mensaje = 'Por favor revisa los datos ingresados.'
    else:
        form = TipoMedidaForm()
    medidas = TipoMedida.objects.all().order_by('nombre')
    return render(request, 'productos/gestion_medidas.html', {'form': form, 'mensaje': mensaje, 'medidas': medidas})

# --- AJAX ---

@admin_required
def obtener_detalle_producto_ajax(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id)
    imagenes = [{'url': img.imagen.url} for img in producto.imagenes.all()]
    if not imagenes: imagenes = [{'url': '/static/images/placeholder-product.png'}]
    html_ficha_tecnica = render_to_string('productos/_snippet_ficha_tecnica_render.html', {'producto': producto})
    
    return JsonResponse({
        'id': producto.id, 'nombre': producto.nombre, 'codigo': producto.codigo,
        'tipo': producto.tipo, 'precio': f"{producto.precio:,.2f}", 'stock': producto.stock,
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
        
        # Actualizamos los campos
        variante.stock = int(nuevo_stock)
        variante.precio = float(nuevo_precio)
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
    
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'mensaje': str(e)
        }, status=400)


@admin_required
def editar_variante(request, variante_id):
    variante = get_object_or_404(Variante, id=variante_id)
    producto = variante.producto
    talle_original_id = variante.talle_id
    colores_originales_ids = list(variante.colores.values_list('id', flat=True))

    if request.method == 'POST':
        # Actualizar talle
        talle_nombre = request.POST.get('talle_nombre', '').strip()
        if talle_nombre:
            talle_obj, _ = Talle.objects.get_or_create(nombre=talle_nombre)
            variante.talle = talle_obj

        # Actualizar stock
        stock = request.POST.get('stock', '0')
        variante.stock = int(stock) if stock else 0
        variante.save()

        # Recalcular stock del producto
        recalcular_stock_producto(producto)

        var_editada = variante

        # 1. CAPTURAR Y GUARDAR COLORES (múltiples)
        colores_datos = request.POST.getlist('colores')
        if colores_datos:
            colores_objs = []
            for dato in colores_datos:
                dato = dato.strip()
                if dato:
                    # Formato: "nombre|#hex" o solo "nombre"
                    if '|' in dato:
                        nombre, codigo_hex = dato.split('|', 1)
                    else:
                        nombre = dato
                        codigo_hex = '#888888'
                    color_obj, created = Color.objects.get_or_create(
                        nombre=nombre,
                        defaults={'codigo_hex': codigo_hex}
                    )
                    if not created and color_obj.codigo_hex != codigo_hex:
                        color_obj.codigo_hex = codigo_hex
                        color_obj.save()
                    colores_objs.append(color_obj)
            var_editada.colores.set(colores_objs)
        else:
            var_editada.colores.clear()

        # 2. CAPTURAR Y GUARDAR MEDIDAS (múltiples)
        def limpiar_decimal(valor):
            """Convierte comas a puntos y maneja valores vacíos"""
            if not valor:
                return 0
            return valor.replace(',', '.')

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

        messages.success(request, f"Talle {variante.talle.nombre} actualizado correctamente.")
        return redirect('productos:editar_producto', prod_id=producto.id)

    form = VarianteForm(instance=variante)
    
    # Pasamos los datos actuales para rellenar los inputs
    return render(request, 'productos/editar_variante.html', {
        'form': form,
        'variante': variante,
        'producto': producto,
        'color_actual': variante.colores.first(),
        'medidas': variante.medidas.all()
    })


# --- VISTAS QR ---

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
    for variante in variantes:
        sincronizar_qrs_variante_color(variante)

    variantes_color = VarianteColor.objects.filter(
        variante__producto=producto,
        activo=True
    ).select_related('variante__talle', 'color').order_by('variante__talle__nombre', 'color__nombre')

    return render(request, 'productos/qrs_impresion.html', {
        'producto': producto,
        'variantes_color': variantes_color,
        'volver_url': volver_url,
    })
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
            qr_fragment = q.split('-')[-1] if q.upper().startswith('IG-') else q
            variante_color = VarianteColor.objects.filter(
                qr_code__startswith=qr_fragment,
                activo=True,
                variante__activa=True,
                variante__stock__gt=0,
                variante__producto__activo=True
            ).select_related('variante__producto', 'variante__talle', 'color').first()
            if variante_color:
                variante = variante_color.variante

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
        'colores'
    )

    data = []

    for variante in variantes:

        colores = []

        for color in variante.colores.all():
            colores.append({
                'nombre': color.nombre,
                'hex': color.codigo_hex
            })

        # Usar precio de variante o del producto si es 0
        precio_base = variante.precio if variante.precio > 0 else producto.precio
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
@login_required
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

            Oferta.objects.create(
                nombre=nombre,
                descuento=descuento_numero,
                codigo=codigo,
                es_cupon=True,
                activa=True
            )

            messages.success(request, 'Codigo de descuento creado correctamente.')
            return redirect('productos:admin_ofertas')

        alcance = request.POST.get('alcance', 'productos')
        aplicar_a_todos = alcance == 'todos'
        categoria = None

        if alcance == 'categoria':
            categoria_id = request.POST.get('categoria')
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
@login_required
def toggle_oferta(request, oferta_id):

    oferta = get_object_or_404(
        Oferta,
        id=oferta_id
    )

    oferta.activa = not oferta.activa
    oferta.save()

    return redirect('productos:admin_ofertas')
