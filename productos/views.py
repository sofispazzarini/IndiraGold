import json
import uuid
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.shortcuts import redirect, get_object_or_404, render
from django.contrib import messages
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.core.paginator import Paginator

from .models import (
    Subcategoria, Producto, Talle, Color, Medida, 
    Variante, Proveedor, ImagenProducto, Categoria, TipoMedida
)
from .forms import (
    ProductoForm, SubcategoriaForm, CategoriaForm, 
    TipoMedidaForm, ProveedorForm, SubcategoriaSoloNombreForm
)

# --- DECORADOR AUXILIAR ---
def admin_required(view_func):
    return login_required(user_passes_test(lambda u: u.is_superuser)(view_func))

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
        
        if len(imagenes_galeria) > 5:
            messages.error(request, "Máximo 5 imágenes de galería permitidas.")
        elif form.is_valid():
            producto = form.save(commit=False)
            producto.subcategoria = subcategoria
            producto.categoria = categoria_padre
            producto.activo = True
            producto.save()
            for img in imagenes_galeria:
                ImagenProducto.objects.create(producto=producto, imagen=img)

            if variantes_json:
                variantes_list = json.loads(variantes_json)
                for v in variantes_list:
                    talle_obj, _ = Talle.objects.get_or_create(nombre=v.get('talle').strip())
                    
                    # 2. Crear la Variante
                    nueva_variante = Variante.objects.create(
                        producto=producto,
                        talle=talle_obj,
                        stock=int(v.get('stock', 0)),
                        precio=float(v.get('precio', 0)),
                        qr_code=str(uuid.uuid4())
                    )
                    
                    # 3. VINCULAR COLORES (Importante: es ManyToMany)
                    colores_data = v.get('colores', [])
                    for c in colores_data:
                        nombre_color = c.get('colorNombre') or c.get('colorHex')
                        if nombre_color:
                            color_obj, _ = Color.objects.get_or_create(nombre=nombre_color)
                            nueva_variante.colores.add(color_obj)
                    
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
            
            messages.success(request, 'Producto guardado correctamente.')
            return redirect('productos:productos_por_subcategoria', subcat_id=subcat_id)
    else:
        form = ProductoForm()
    return render(request, 'productos/agregar_producto.html', 
    {'form': form, 'subcategoria': subcategoria, 'proveedores': proveedores,'categoria': categoria_padre,})

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
        
        if form.is_valid():
            # 2. commit=False para reasignar las relaciones obligatorias
            producto_editado = form.save(commit=False)
            producto_editado.categoria = cat_segura
            producto_editado.subcategoria = subcat_segura
            
            # Si se subió un esquema por el input manual, lo asignamos
            if esquema_nuevo:
                producto_editado.imagen_tecnica = esquema_nuevo
            
            producto_editado.save()
            form.save_m2m()
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
    producto_id = variante.producto.id
    variante.delete()
    messages.success(request, 'Variante eliminada correctamente.')
    return redirect('productos:editar_producto', prod_id=producto_id)

# --- CATEGORÍAS Y SUBCATEGORÍAS ---

@admin_required
def agregar_categoria(request):
    if request.method == 'POST':
        form = CategoriaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Categoría agregada.')
        else:
            mensaje = 'Por favor revisa los datos ingresados.'
    form = CategoriaForm()
    categorias = Categoria.objects.filter(activa=True).order_by('nombre')
    return render(request, 'productos/agregar_categoria.html', {'form': form, 'categorias': categorias})

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

        return JsonResponse({'status': 'ok', 'mensaje': 'Variante actualizada.'})
    
    except Exception as e:
        return JsonResponse({'status': 'error', 'mensaje': str(e)}, status=400)
from .forms import VarianteForm # Importá el formulario nuevo

from .models import Color, Medida # Chequeá que estén importados arriba

@admin_required
def editar_variante(request, variante_id):
    variante = get_object_or_404(Variante, id=variante_id)
    producto = variante.producto
    
    if request.method == 'POST':
        form = VarianteForm(request.POST, instance=variante)
        if form.is_valid():
            var_editada = form.save()

            # 1. CAPTURAR Y GUARDAR TODOS LOS COLORES
            colores_nombres = request.POST.getlist('colores[]')
            colores_objs = []
            for nombre in colores_nombres:
                nombre = nombre.strip()
                if nombre:
                    color_obj, _ = Color.objects.get_or_create(nombre=nombre)
                    colores_objs.append(color_obj)
            var_editada.colores.set(colores_objs)

            # 2. CAPTURAR Y GUARDAR TODAS LAS MEDIDAS
            altos = request.POST.getlist('alto[]')
            anchos = request.POST.getlist('ancho[]')
            largos = request.POST.getlist('largo[]')
            tiros = request.POST.getlist('tiro[]')
            medidas_objs = []
            for i in range(len(altos)):
                # Si al menos un campo está completo
                if altos[i] or anchos[i] or largos[i] or tiros[i]:
                    medida = Medida()
                    medida.alto = altos[i] if altos[i] else 0
                    medida.ancho = anchos[i] if anchos[i] else 0
                    medida.largo = largos[i] if largos[i] else 0
                    medida.tiro = tiros[i] if tiros[i] else 0
                    medida.save()
                    medidas_objs.append(medida)
            var_editada.medidas.set(medidas_objs)

            messages.success(request, f"Talle {variante.talle.nombre} actualizado correctamente.")
            return redirect('productos:editar_producto', prod_id=producto.id)
    else:
        form = VarianteForm(instance=variante)
    
    # Pasamos los datos actuales para rellenar los inputs
    return render(request, 'productos/editar_variante.html', {
        'form': form,
        'variante': variante,
        'producto': producto,
        'color_actual': variante.colores.first(),
        'medida_actual': variante.medidas.first()
    })