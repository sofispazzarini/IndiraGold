from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from .models import Pedido


# Decorador para verificar que es administrador
def admin_required(view_func):
    return login_required(user_passes_test(lambda u: u.is_superuser)(view_func))


@admin_required
def gestion_pedidos(request):
    """
    Listado de pedidos realizados con filtro opcional por estado.
    """
    pedidos = Pedido.objects.all().order_by('-created_at')
    
    # Filtrar por estado si se proporciona
    estado = request.GET.get('estado', '')
    if estado:
        pedidos = pedidos.filter(estado=estado)
    
    # Paginación
    paginator = Paginator(pedidos, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Estados disponibles para el filtro
    estados_disponibles = Pedido.ESTADOS
    
    context = {
        'page_obj': page_obj,
        'pedidos': page_obj.object_list,
        'estado_filtro': estado,
        'estados': estados_disponibles,
    }
    
    return render(request, 'pedidos/gestion_pedidos.html', context)
