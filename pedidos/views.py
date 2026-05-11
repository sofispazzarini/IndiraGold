from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db import transaction
from django.contrib import messages
from django.db.models import Sum, Count, Avg, Q, F
from datetime import datetime, timedelta
from decimal import Decimal
from .models import Pedido, PedidoItem, Gasto
from .forms import GastoForm
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
def crear_gasto(request):
    """
    Permite al administrador registrar un gasto adicional.
    Criterio: el admin ingresa monto y descripción y se guarda el gasto.
    """
    if request.method == 'POST':
        form = GastoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Gasto registrado correctamente.')
            return redirect('pedidos:gestion_pedidos')
        else:
            messages.error(request, 'Por favor corrija los errores en el formulario.')
    else:
        form = GastoForm(initial={'fecha': datetime.now().date()})

    context = {
        'form': form,
    }
    return render(request, 'pedidos/crear_gasto.html', context)


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


@admin_required
def estadisticas_ventas(request):
    """
    Muestra estadísticas de ventas con filtrado por período.
    """
    hoy = datetime.now().date()
    
    # Parámetros de filtro
    tipo_periodo = request.GET.get('tipo_periodo', '30dias')
    fecha_inicio_str = request.GET.get('fecha_inicio', '')
    fecha_fin_str = request.GET.get('fecha_fin', '')
    
    # Determinar rango de fechas según el período seleccionado
    if tipo_periodo == 'personalizado' and fecha_inicio_str and fecha_fin_str:
        try:
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
            fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
        except ValueError:
            fecha_inicio = hoy - timedelta(days=30)
            fecha_fin = hoy
    elif tipo_periodo == '7dias':
        fecha_inicio = hoy - timedelta(days=7)
        fecha_fin = hoy
    elif tipo_periodo == '90dias':
        fecha_inicio = hoy - timedelta(days=90)
        fecha_fin = hoy
    else:  # 30dias por defecto
        fecha_inicio = hoy - timedelta(days=30)
        fecha_fin = hoy
    
    # Filtrar pedidos por rango de fechas
    pedidos = Pedido.objects.filter(
        created_at__date__gte=fecha_inicio,
        created_at__date__lte=fecha_fin
    )
    
    # ESTADÍSTICAS GENERALES
    total_ventas = pedidos.aggregate(Sum('total'))['total__sum'] or Decimal('0.00')
    cantidad_pedidos = pedidos.count()
    promedio_por_pedido = total_ventas / cantidad_pedidos if cantidad_pedidos > 0 else Decimal('0.00')
    
    # ESTADÍSTICAS POR ESTADO
    pedidos_por_estado = pedidos.values('estado').annotate(
        cantidad=Count('id'),
        total=Sum('total')
    ).order_by('-cantidad')
    
    # Mapear estados a sus labels
    estados_dict = {valor: label for valor, label in Pedido.ESTADOS}
    for item in pedidos_por_estado:
        item['estado_label'] = estados_dict.get(item['estado'], item['estado'])
    
    # PRODUCTOS MÁS VENDIDOS
    productos_top = (
        PedidoItem.objects
        .filter(pedido__in=pedidos)
        .values('variante__producto__nombre')
        .annotate(
            cantidad_total=Sum('cantidad'),
            ingresos=Sum('precio_total'),
            precio_promedio=Avg('precio_unitario')
        )
        .order_by('-cantidad_total')[:6]
    )
    
    # TIPOS DE VENTA
    ventas_por_tipo = pedidos.values('tipo_venta').annotate(
        cantidad=Count('id'),
        total=Sum('total')
    ).order_by('-cantidad')
    
    tipos_venta_dict = {valor: label for valor, label in Pedido.TIPOS_VENTA}
    for item in ventas_por_tipo:
        item['tipo_label'] = tipos_venta_dict.get(item['tipo_venta'], item['tipo_venta'])
    
    # EVOLUCIÓN DIARIA DE VENTAS (últimos 30 días)
    evolucion_diaria = []
    for i in range(31):
        fecha = hoy - timedelta(days=30 - i)
        pedidos_dia = Pedido.objects.filter(created_at__date=fecha)
        total_dia = pedidos_dia.aggregate(Sum('total'))['total__sum'] or Decimal('0.00')
        cantidad_dia = pedidos_dia.count()
        evolucion_diaria.append({
            'fecha': fecha.strftime('%d/%m/%Y'),
            'cantidad': cantidad_dia,
            'total': total_dia,
        })
    
    context = {
        'total_ventas': total_ventas,
        'cantidad_pedidos': cantidad_pedidos,
        'promedio_por_pedido': promedio_por_pedido,
        'pedidos_por_estado': pedidos_por_estado,
        'productos_top': productos_top,
        'ventas_por_tipo': ventas_por_tipo,
        'evolucion_diaria': evolucion_diaria,
        'tipo_periodo': tipo_periodo,
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        'fecha_inicio_str': fecha_inicio.strftime('%Y-%m-%d'),
        'fecha_fin_str': fecha_fin.strftime('%Y-%m-%d'),
    }
    return render(request, 'pedidos/estadisticas_ventas.html', context)
