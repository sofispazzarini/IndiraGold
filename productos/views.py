from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from .models import Producto
from .forms import ProductoForm

# 1. READ (Lista de todos los productos)
class ProductoListView(ListView):
    model = Producto
    template_name = 'preview_productos.html'
    context_object_name = 'productos'

# 2. READ (Detalle de un producto - Refactorizamos la que tenías a Clase)
class ProductoDetailView(DetailView):
    model = Producto
    template_name = 'detalle_producto.html'
    context_object_name = 'producto'

    def get_queryset(self):
        return (
            Producto.objects
            .select_related('categoria')
            .prefetch_related('variantes__talle', 'variantes__medida')
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        producto = ctx['producto']

        tabla_medidas = []
        seen_talles = set()

        variantes = (
            producto.variantes
            .filter(activa=True, medida__isnull=False)
            .select_related('talle', 'medida')
            .order_by('talle__nombre', 'medida_id')
        )

        for variante in variantes:
            if variante.talle_id in seen_talles:
                continue

            medida = variante.medida
            tabla_medidas.append({
                'talle': variante.talle.nombre,
                'alto': medida.alto,
                'ancho': medida.ancho,
                'largo': medida.largo,
                'tiro': medida.tiro,
            })
            seen_talles.add(variante.talle_id)

        ctx['tabla_medidas'] = tabla_medidas
        return ctx

# 3. CREATE (Crear producto)
class ProductoCreateView(CreateView):
    model = Producto
    form_class = ProductoForm
    template_name = 'producto_form.html'
    success_url = reverse_lazy('productos:lista') # Redirige a la lista al terminar

# 4. UPDATE (Actualizar producto)
class ProductoUpdateView(UpdateView):
    model = Producto
    form_class = ProductoForm
    template_name = 'producto_form.html' # Reutilizamos el template de creación
    success_url = reverse_lazy('productos:lista')

# 5. DELETE (Eliminar producto)
class ProductoDeleteView(DeleteView):
    model = Producto
    template_name = 'confirm_delete.html'
    success_url = reverse_lazy('productos:lista')