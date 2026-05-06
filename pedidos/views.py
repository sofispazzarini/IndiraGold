from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db import transaction
from django.contrib import messages
from decimal import Decimal
from .models import Pedido, PedidoItem
from users.models import Cliente
from productos.models import Variante


# Decorador para verificar que es administrador
def admin_required(view_func):
    return login_required(login_url="/users/login/")(user_passes_test(lambda u: u.is_superuser, login_url="/users/login/")(view_func))


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


@admin_required
def historial_cliente(request, cliente_id):
    """
    Muestra el historial de pedidos de un cliente (solo accesible por administradores).
    """
    cliente = get_object_or_404(Cliente, pk=cliente_id)
    pedidos_qs = (
        Pedido.objects.filter(cliente=cliente)
        .select_related('cliente')
        .order_by('-created_at')
    )

    # Paginación
    paginator = Paginator(pedidos_qs, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'cliente': cliente,
        'page_obj': page_obj,
        'pedidos': page_obj.object_list,
    }

    return render(request, 'pedidos/historial_cliente.html', context)


@admin_required
def detalle_pedido(request, pedido_id):
    """
    Muestra el detalle completo de un pedido.
    """
    pedido = get_object_or_404(
        Pedido.objects.select_related('cliente', 'cliente__user').prefetch_related(
            'items__variante__producto',
            'items__variante__talle',
            'items__variante__colores',
        ),
        pk=pedido_id,
    )
    pago = getattr(pedido, 'pago', None)

    context = {
        'pedido': pedido,
        'pago': pago,
        'items': pedido.items.all(),
    }
    return render(request, 'pedidos/detalle_pedido.html', context)


@admin_required
def editar_pedido(request, pedido_id):
    """
    Edita un pedido (solo si no está finalizado).
    """
    pedido = get_object_or_404(Pedido, pk=pedido_id)
    
    # Estados que impiden edición
    estados_no_editables = ['entregado', 'cancelado']
    if pedido.estado in estados_no_editables:
        messages.error(request, f"No se pueden editar pedidos en estado '{pedido.get_estado_display()}'.")
        return redirect('pedidos:detalle_pedido', pedido_id=pedido.id)
    
    if request.method == 'POST':
        with transaction.atomic():
            # Procesar eliminación de items
            items_a_eliminar = request.POST.getlist('eliminar_item')
            for item_id in items_a_eliminar:
                try:
                    item = PedidoItem.objects.get(id=item_id, pedido=pedido)
                    item.delete()
                except PedidoItem.DoesNotExist:
                    pass
            
            # Procesar cambios de cantidad
            items = PedidoItem.objects.filter(pedido=pedido)
            total_nuevo = Decimal('0.00')
            
            for item in items:
                cantidad_key = f'cantidad_{item.id}'
                if cantidad_key in request.POST:
                    try:
                        nueva_cantidad = int(request.POST[cantidad_key])
                        if nueva_cantidad > 0:
                            item.cantidad = nueva_cantidad
                            item.precio_total = item.precio_unitario * nueva_cantidad
                            item.save()
                            total_nuevo += item.precio_total
                        else:
                            item.delete()
                    except (ValueError, TypeError):
                        total_nuevo += item.precio_total
                else:
                    total_nuevo += item.precio_total
            
            # Agregar nuevo item si se proporciona
            variante_id = request.POST.get('nueva_variante_id')
            cantidad_nueva = request.POST.get('nueva_cantidad')
            
            if variante_id and cantidad_nueva:
                try:
                    variante = Variante.objects.get(id=variante_id)
                    cantidad_nueva_int = int(cantidad_nueva)
                    if cantidad_nueva_int > 0:
                        precio_unitario = variante.precio or variante.producto.precio
                        precio_total = precio_unitario * cantidad_nueva_int
                        PedidoItem.objects.create(
                            pedido=pedido,
                            variante=variante,
                            cantidad=cantidad_nueva_int,
                            precio_unitario=precio_unitario,
                            precio_total=precio_total,
                        )
                        total_nuevo += precio_total
                except (Variante.DoesNotExist, ValueError, TypeError):
                    pass
            
            # Actualizar dirección
            direccion_info = request.POST.get('direccion_info', '').strip()
            if direccion_info:
                pedido.direccion_info = direccion_info
            
            # Actualizar estado
            nuevo_estado = request.POST.get('estado', pedido.estado)
            if nuevo_estado in dict(Pedido.ESTADOS):
                pedido.estado = nuevo_estado
            
            # Guardar el pedido con el total recalculado
            pedido.total = total_nuevo
            pedido.save()
            
            messages.success(request, 'Pedido actualizado correctamente.')
            return redirect('pedidos:detalle_pedido', pedido_id=pedido.id)
    
    # GET: mostrar form
    variantes_disponibles = Variante.objects.filter(activa=True, stock__gt=0).select_related('producto', 'talle')
    items = pedido.items.all().select_related('variante__producto', 'variante__talle')
    
    context = {
        'pedido': pedido,
        'items': items,
        'variantes_disponibles': variantes_disponibles,
        'estados_no_editables': ['entregado', 'cancelado'],
    }
    return render(request, 'pedidos/editar_pedido.html', context)
