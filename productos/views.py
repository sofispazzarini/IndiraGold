from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from .forms import ProductoForm, SubcategoriaForm, CategoriaForm, TipoMedidaForm, ProveedorForm
from .models import Subcategoria, Producto, Categoria, TipoMedida, Proveedor
from django.core.paginator import Paginator

# Vista para agregar proveedor
@login_required
@user_passes_test(lambda u: u.is_superuser)
def agregar_proveedor(request):
	mensaje = None
	edit_form = None
	edit_id = request.GET.get('edit')
	form = None
	delete_id = request.GET.get('delete')
	proveedor_a_eliminar = None
	if delete_id:
		try:
			proveedor_a_eliminar = Proveedor.objects.get(id=delete_id)
		except Proveedor.DoesNotExist:
			proveedor_a_eliminar = None
	if request.method == 'POST' and 'edit_id' in request.POST:
		proveedor = get_object_or_404(Proveedor, id=request.POST['edit_id'])
		edit_form = ProveedorForm(request.POST, instance=proveedor)
		if edit_form.is_valid():
			edit_form.save()
			mensaje = 'Proveedor actualizado correctamente.'
			edit_form = None
			edit_id = None
		else:
			mensaje = 'Por favor revisa los datos ingresados.'
		form = ProveedorForm()
	elif request.method == 'POST' and 'delete_id' in request.POST:
		proveedor = get_object_or_404(Proveedor, id=request.POST['delete_id'])
		proveedor.delete()
		mensaje = 'Proveedor eliminado correctamente.'
		form = ProveedorForm()
		delete_id = None
	elif request.method == 'POST':
		form = ProveedorForm(request.POST)
		if form.is_valid():
			telefono = form.cleaned_data['telefono']
			if Proveedor.objects.filter(telefono=telefono).exists():
				mensaje = 'Ya existe un proveedor con ese teléfono.'
			else:
				form.save()
				mensaje = 'Proveedor agregado correctamente.'
				form = ProveedorForm()
		else:
			mensaje = 'Por favor revisa los datos ingresados.'
	else:
		form = ProveedorForm()
	if edit_id and not edit_form:
		proveedor = get_object_or_404(Proveedor, id=edit_id)
		edit_form = ProveedorForm(instance=proveedor)
	proveedores_list = Proveedor.objects.all().order_by('-created_at')
	paginator = Paginator(proveedores_list, 10)
	page_number = request.GET.get('page')
	proveedores = paginator.get_page(page_number)
	return render(request, 'productos/agregar_proveedor.html', {
		'form': form,
		'mensaje': mensaje,
		'proveedores': proveedores,
		'edit_form': edit_form,
		'edit_id': edit_id,
		'delete_id': delete_id,
		'proveedor_a_eliminar': proveedor_a_eliminar
	})

# Vista para editar proveedor
@login_required
@user_passes_test(lambda u: u.is_superuser)
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



# Vista para gestionar tipos de medida globales
@login_required
@user_passes_test(lambda u: u.is_superuser)
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
from django.shortcuts import get_object_or_404, redirect, render

# Formularios y modelos

from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ProductoForm, SubcategoriaForm, CategoriaForm, TipoMedidaForm, ProveedorForm
from .models import Subcategoria, Producto, Categoria, TipoMedida, Proveedor

# Vista para gestionar subcategorías de una categoría
@login_required
@user_passes_test(lambda u: u.is_superuser)
def gestion_subcategorias(request, cat_id):
	categoria = get_object_or_404(Categoria, id=cat_id, activa=True)
	mensaje = None
	from .forms import SubcategoriaSoloNombreForm
	if request.method == 'POST':
		form = SubcategoriaSoloNombreForm(request.POST)
		if form.is_valid():
			subcat = form.save(commit=False)
			subcat.categoria = categoria
			subcat.save()
			mensaje = 'Subcategoría agregada correctamente.'
			form = SubcategoriaSoloNombreForm()
		else:
			mensaje = 'Por favor revisa los datos ingresados.'
	else:
		form = SubcategoriaSoloNombreForm()
	subcategorias = categoria.subcategorias.all().order_by('nombre')
	return render(request, 'productos/gestion_subcategorias.html', {
		'categoria': categoria,
		'form': form,
		'mensaje': mensaje,
		'subcategorias': subcategorias
	})
 # Vista para agregar producto desde una subcategoría
@login_required
@user_passes_test(lambda u: u.is_superuser)
def agregar_producto(request, subcat_id):
	subcategoria = get_object_or_404(Subcategoria, id=subcat_id, activa=True)
	if request.method == 'POST':
		form = ProductoForm(request.POST)
		if form.is_valid():
			producto = form.save(commit=False)
			producto.subcategoria = subcategoria
			producto.categoria = subcategoria.categoria
			producto.save()
			return redirect('productos_por_subcategoria', subcat_id=subcat_id)
	else:
		form = ProductoForm(initial={'subcategoria': subcategoria, 'categoria': subcategoria.categoria})
	return render(request, 'productos/agregar_producto.html', {'form': form, 'subcategoria': subcategoria})
from .forms import SubcategoriaForm
from .models import Subcategoria, Producto
from django.shortcuts import get_object_or_404, redirect
# Vista para mostrar productos de una subcategoría y permitir agregar nuevos
@login_required
@user_passes_test(lambda u: u.is_superuser)
def productos_por_subcategoria(request, subcat_id):
	subcategoria = get_object_or_404(Subcategoria, id=subcat_id, activa=True)
	productos = Producto.objects.filter(categoria=subcategoria.categoria, activo=True)
	# Filtrar productos que pertenezcan a la subcategoría si hay relación directa
	# Si Producto tiene FK a Subcategoria, usar: Producto.objects.filter(subcategoria=subcategoria, activo=True)
	return render(request, 'productos/productos_por_subcategoria.html', {
		'subcategoria': subcategoria,
		'productos': productos
	})
# Vista para agregar subcategoría y mostrar subcategorías
@login_required
@user_passes_test(lambda u: u.is_superuser)
def agregar_subcategoria(request):
	mensaje = None
	if request.method == 'POST':
		form = SubcategoriaForm(request.POST)
		if form.is_valid():
			form.save()
			mensaje = 'Subcategoría agregada correctamente.'
			form = SubcategoriaForm()
		else:
			mensaje = 'Por favor revisa los datos ingresados.'
	else:
		form = SubcategoriaForm()
	subcategorias = Subcategoria.objects.select_related('categoria').filter(activa=True).order_by('categoria__nombre', 'nombre')
	return render(request, 'productos/agregar_subcategoria.html', {'form': form, 'mensaje': mensaje, 'subcategorias': subcategorias})

from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render
from .forms import CategoriaForm
from .models import Categoria

@login_required
@user_passes_test(lambda u: u.is_superuser)
def agregar_categoria(request):
	mensaje = None
	if request.method == 'POST':
		form = CategoriaForm(request.POST)
		if form.is_valid():
			form.save()
			mensaje = 'Categoría agregada correctamente.'
			form = CategoriaForm()
		else:
			mensaje = 'Por favor revisa los datos ingresados.'
	else:
		form = CategoriaForm()
	categorias = Categoria.objects.filter(activa=True).order_by('nombre')
	return render(request, 'productos/agregar_categoria.html', {'form': form, 'mensaje': mensaje, 'categorias': categorias})
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render
# Vista para gestión de productos (solo admin)
@login_required
@user_passes_test(lambda u: u.is_superuser)
def gestion_productos(request):
	from .models import Categoria
	categories = Categoria.objects.filter(activa=True).order_by('nombre')
	return render(request, 'productos/gestion_productos.html', {'categories': categories})
from django.shortcuts import render

# Create your views here.
