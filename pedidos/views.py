from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db import transaction
from django.contrib import messages
from django.db.models import Sum, Count, Avg, Q, F
from datetime import datetime, timedelta
from decimal import Decimal
from .models import Pedido, PedidoItem, VentaLocal, PagoVentaLocal, ConfiguracionEnvio
from carritos.models import Carrito, CarritoItem
from carritos.utils import get_or_create_cart, vincular_carrito_con_usuario
from .models import Pedido, PedidoItem, Gasto, VentaLocal, VentaLocalItem
from .forms import GastoForm, ConfiguracionEnvioForm

from pedidos.forms import GastoForm, ConfiguracionEnvioForm
from .models import Gasto, Pedido, PedidoItem
from carritos.models import Carrito, CarritoItem
from carritos.utils import clear_cart_session, get_or_create_cart, vincular_carrito_con_usuario
from users.models import Cliente, Direccion
from productos.models import Variante
import mercadopago
from django.conf import settings
from django.views.decorators.http import require_POST
from django.core.mail import send_mail
from django.conf import settings
from django.db.models import Q
from django.core.paginator import Paginator
import json

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils.html import escape
print("===== PEDIDOS VIEWS CARGADO =====")
print("TOKEN MP:", settings.MERCADO_PAGO_ACCESS_TOKEN)
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
    q = request.GET.get('q', '')

    if q:

        pedidos = pedidos.filter(

            Q(cliente__user__first_name__icontains=q)

            |

            Q(cliente__user__last_name__icontains=q)

            |

            Q(cliente__user__email__icontains=q)

        )
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
def listado_gastos(request):
    """
    Listado de gastos adicionales del negocio.
    """
    gastos = Gasto.objects.all().order_by('-fecha', '-created_at')

    # Paginación
    paginator = Paginator(gastos, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Total de gastos
    total_gastos = Gasto.objects.aggregate(total=Sum('monto'))['total'] or 0

    context = {
        'page_obj': page_obj,
        'gastos': page_obj.object_list,
        'total_gastos': total_gastos,
    }
    return render(request, 'pedidos/listado_gastos.html', context)


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
            return redirect('pedidos:listado_gastos')
        else:
            messages.error(request, 'Por favor corrija los errores en el formulario.')
    else:
        form = GastoForm(initial={'fecha': datetime.now().date()})

    context = {
        'form': form,
    }
    return render(request, 'pedidos/crear_gasto.html', context)


@admin_required
def eliminar_gasto(request, gasto_id):
    """
    Elimina un gasto registrado.
    """
    gasto = get_object_or_404(Gasto, id=gasto_id)
    if request.method == 'POST':
        descripcion = gasto.descripcion
        gasto.delete()
        messages.success(request, f'Gasto "{descripcion}" eliminado correctamente.')
    return redirect('pedidos:listado_gastos')


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
            pedido.metodo_entrega = request.POST.get('metodo_entrega', pedido.metodo_entrega)
            pedido.codigo_postal = request.POST.get('codigo_postal', pedido.codigo_postal)
            pedido.localidad = request.POST.get('localidad', pedido.localidad)
            pedido.calle_numero = request.POST.get('calle_numero', pedido.calle_numero)

            # Si cambia a domicilio, podrías disparar aquí la lógica del costo
            if pedido.metodo_entrega == 'domicilio':
                # Aquí podrías poner el valor que venga del cálculo de Correo Argentino
                pedido.costo_envio = Decimal(request.POST.get('costo_envio', '0.00'))
            else:
                pedido.costo_envio = Decimal('0.00')
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

@login_required
def checkout_view(request):
    carrito = get_or_create_cart(request)
    # Traemos los items con sus variantes y fotos
    items = carrito.items.all().select_related('variante__producto', 'variante__talle')
    configuracion_envio = ConfiguracionEnvio.actual()
    cliente, _ = Cliente.objects.get_or_create(user=request.user)
    direcciones = cliente.direcciones.all()
    
    subtotal = sum(
        item.subtotal for item in items
    )
    return render(request, 'pedidos/checkout.html', {
        'items': items,
        'subtotal': subtotal,
        'total': subtotal,
        'carrito': carrito,
        'configuracion_envio': configuracion_envio,
        'precio_flex': configuracion_envio.costo_flex,
        'zonas_flex': configuracion_envio.zonas_flex_lista,
        'direcciones': direcciones,
    })
# pedidos/views.py

@login_required
@transaction.atomic
def confirmar_pedido(request):
    # 1. USAR get_or_create_cart para traer los datos reales de la base de datos
    carrito = get_or_create_cart(request)
    items_del_carrito = carrito.items.all().select_related('variante__producto', 'variante__talle')

    # Si el carrito está vacío, redirigimos usando home:home (con los dos puntos)
    if not items_del_carrito.exists():
        messages.error(request, "Tu carrito está vacío.")
        return redirect("home:home") # <-- ACÁ ESTABA EL ERROR DE LA LÍNEA 215

    # 2. Procesamos el pedido (esta es la info que ahora sí va a llegar bien)

    if request.method == 'POST':
        metodo = request.POST.get('metodo_entrega')
        configuracion_envio = ConfiguracionEnvio.actual()
        costo_envio = (
            Decimal(configuracion_envio.costo_flex)
            if metodo == 'flex' and configuracion_envio.flex_activo
            else Decimal('0.00')
        )

        cliente, _ = Cliente.objects.get_or_create(user=request.user)
        subtotal_productos = sum(item.precio_total for item in items_del_carrito)
        direccion = None

        if metodo == 'flex':
            direccion = Direccion.objects.filter(
                id=request.POST.get('direccion_id'),
                cliente=cliente
            ).first()
        elif metodo == 'correo':
            direccion = Direccion.objects.filter(
                id=request.POST.get('direccion_correo_id'),
                cliente=cliente
            ).first()

        # VALIDACIÓN DE STOCK
        variantes_sin_stock = []
        for item in items_del_carrito:
            if item.variante.stock < item.cantidad:
                variantes_sin_stock.append(f"{item.variante.producto.nombre} (Talle: {item.variante.talle.nombre}) - Stock disponible: {item.variante.stock}, intentas: {item.cantidad}")
        if variantes_sin_stock:
            messages.error(request, "No hay stock suficiente para los siguientes productos:\n" + "\n".join(variantes_sin_stock))
            return redirect("pedidos:checkout")

        # Creamos el pedido oficial
        pedido = Pedido.objects.create(
            cliente=cliente,
            total=subtotal_productos + costo_envio,
            costo_envio=costo_envio,
            metodo_entrega=metodo,
            direccion=direccion,
            codigo_postal=direccion.codigo_postal if direccion else request.POST.get('codigo_postal'),
            localidad=direccion.ciudad if direccion else request.POST.get('localidad'),
            calle_numero=f'{direccion.calle} {direccion.numero}' if direccion else request.POST.get('calle_numero'),
            correo=request.POST.get('correo'),
            tipo_correo=request.POST.get('tipo_correo'),
            sucursal_correo=request.POST.get('sucursal_correo'),
            tipo_venta='online',
            estado='pendiente',
        )

        # 3. Movemos los productos al pedido y bajamos el stock
        for item in items_del_carrito:
            PedidoItem.objects.create(
                pedido=pedido,
                variante=item.variante,
                cantidad=item.cantidad,
                precio_unitario=item.variante.precio,
                precio_total=item.cantidad * item.variante.precio
            )
            # Bajamos el stock del talle elegido
            item.variante.stock -= item.cantidad
            item.variante.save()

        # 4. Limpieza final
        carrito.activo = False # Cerramos el carrito actual
        carrito.save()
        clear_cart_session(request.session)

        messages.success(request, f"¡Pedido #{pedido.id} realizado con éxito!")
        return redirect("pedidos:detalle_pedido", pedido_id=pedido.id)

    return redirect("pedidos:checkout")
    # pedidos/views.py

@login_required
def eliminar_item_carrito(request, variante_id):
    from carritos.models import CarritoItem
    
    # 1. Borramos de la Base de Datos
    carrito = get_or_create_cart(request)
    item = get_object_or_404(CarritoItem, carrito=carrito, variante_id=variante_id)
    item.delete()

    # 2. Sincronizamos la sesión solo para el numerito (no para lógica de productos)
    carrito_final = {}
    for item_db in carrito.items.all():
        vid = str(item_db.variante.id)
        carrito_final[vid] = item_db.cantidad
    request.session['carrito'] = carrito_final
    request.session.modified = True

    # Si después de eliminar quedan items, mostrar mensaje de éxito
    if carrito.items.exists():
        messages.success(request, "Producto quitado del resumen.")
        return redirect('pedidos:checkout')
    else:
        # Si no quedan productos, limpiar mensajes previos y mostrar solo el de vacío
        storage = messages.get_messages(request)
        storage.used = True
        messages.info(request, "No quedan productos en tu carrito.")
        return redirect('pedidos:checkout')
sdk = mercadopago.SDK(settings.MERCADO_PAGO_ACCESS_TOKEN)

@login_required
def crear_pago(request):

    carrito = get_or_create_cart(request)

    # Traer items del carrito
    items = carrito.items.all().select_related(
        'variante__producto',
        'variante__talle'
    )

    # Verificar si el carrito está vacío
    if not items.exists():
        messages.error(request, 'Tu carrito está vacío.')
        return redirect('pedidos:checkout')

    # VALIDAR STOCK
    variantes_sin_stock = []

    for item in items:

        if item.variante.stock < item.cantidad:

            talle = (
                item.variante.talle.nombre
                if item.variante.talle
                else "Sin talle"
            )

            variantes_sin_stock.append(
                f"{item.variante.producto.nombre} "
                f"(Talle: {talle}) "
                f"- Disponible: {item.variante.stock}"
            )

    # Si hay productos sin stock
    if variantes_sin_stock:

        messages.error(
            request,
            "No hay stock suficiente para:\n" +
            "\n".join(variantes_sin_stock)
        )

        return redirect('pedidos:checkout')

    # ARMAR PRODUCTOS PARA MP
    productos = []

    for item in items:

        productos.append({
            "title": item.variante.producto.nombre,
            "quantity": item.cantidad,
            "currency_id": "ARS",
            "unit_price": float(item.precio_unitario)
        })
    request.session['metodo_entrega'] = request.POST.get(
        'metodo_entrega',
        'local'
    )

    request.session['codigo_postal'] = request.POST.get(
        'codigo_postal'
    )

    request.session['localidad'] = request.POST.get(
        'localidad'
    )

    request.session['calle_numero'] = request.POST.get(
        'calle_numero'
    )
    request.session['direccion_id'] = request.POST.get('direccion_id')
    request.session['direccion_correo_id'] = request.POST.get('direccion_correo_id')
    request.session['correo'] = request.POST.get('correo')
    request.session['tipo_correo'] = request.POST.get('tipo_correo')
    request.session['sucursal_correo'] = request.POST.get('sucursal_correo')

    configuracion_envio = ConfiguracionEnvio.actual()
    cliente, _ = Cliente.objects.get_or_create(user=request.user)

    if request.session['metodo_entrega'] == 'flex' and not configuracion_envio.flex_activo:
        messages.error(request, 'El Envio Flex no esta disponible en este momento.')
        return redirect('pedidos:checkout')

    if request.session['metodo_entrega'] == 'flex':
        direccion_valida = Direccion.objects.filter(
            id=request.session.get('direccion_id'),
            cliente=cliente
        ).exists()
        if not direccion_valida:
            messages.error(request, 'Selecciona una direccion para Envio Flex.')
            return redirect('pedidos:checkout')

    if request.session['metodo_entrega'] == 'correo':
        direccion_valida = Direccion.objects.filter(
            id=request.session.get('direccion_correo_id'),
            cliente=cliente
        ).exists()
        if not direccion_valida:
            messages.error(request, 'Selecciona una direccion para el envio por correo.')
            return redirect('pedidos:checkout')

    costo_envio = (
        Decimal(configuracion_envio.costo_flex)
        if request.session['metodo_entrega'] == 'flex' and configuracion_envio.flex_activo
        else Decimal('0')
    )

    if costo_envio > 0:
        productos.append({
            "title": "Envio Flex",
            "quantity": 1,
            "currency_id": "ARS",
            "unit_price": float(costo_envio)
        })
    # CREAR PREFERENCIA
    preference_response = sdk.preference().create({
        "items": productos,
        "back_urls": {
            "success": "http://127.0.0.1:8000/pedidos/pago-exitoso/",
            "failure": "http://127.0.0.1:8000/",
            "pending": "http://127.0.0.1:8000/"
        },
        "auto_return": "approved"
    })

    print(preference_response)

    # VALIDAR RESPUESTA
    if preference_response.get("status") != 201:

        messages.error(
            request,
            "No pudimos iniciar el pago online."
        )

        return redirect('pedidos:checkout')

    preference = preference_response.get("response", {})

    init_point = preference.get("init_point")

    if not init_point:

        messages.error(
            request,
            "MercadoPago no devolvió el link de pago."
        )

        return redirect('pedidos:checkout')

    return redirect(init_point)
@login_required
@transaction.atomic
def pago_exitoso(request):

    carrito = get_or_create_cart(request)

    items = carrito.items.all().select_related(
        'variante__producto',
        'variante__talle'
    )

    if not items.exists():

        messages.error(
            request,
            "No hay productos para procesar."
        )

        return redirect('pedidos:checkout')

    cliente, _ = Cliente.objects.get_or_create(
        user=request.user
    )

    subtotal = sum(
        item.precio_total for item in items
    )

    metodo_entrega = request.session.get(
        'metodo_entrega',
        'local'
    )

    configuracion_envio = ConfiguracionEnvio.actual()
    costo_envio = (
        Decimal(configuracion_envio.costo_flex)
        if metodo_entrega == 'flex' and configuracion_envio.flex_activo
        else Decimal('0')
    )
    direccion = None

    if metodo_entrega == 'flex':
        direccion = Direccion.objects.filter(
            id=request.session.get('direccion_id'),
            cliente=cliente
        ).first()
    elif metodo_entrega == 'correo':
        direccion = Direccion.objects.filter(
            id=request.session.get('direccion_correo_id'),
            cliente=cliente
        ).first()

    pedido = Pedido.objects.create(
        cliente=cliente,
        total=subtotal + costo_envio,
        costo_envio=costo_envio,
        metodo_entrega=metodo_entrega,
        direccion=direccion,
        codigo_postal=direccion.codigo_postal if direccion else request.session.get('codigo_postal'),
        localidad=direccion.ciudad if direccion else request.session.get('localidad'),
        calle_numero=f'{direccion.calle} {direccion.numero}' if direccion else request.session.get('calle_numero'),
        correo=request.session.get('correo'),
        tipo_correo=request.session.get('tipo_correo'),
        sucursal_correo=request.session.get('sucursal_correo'),
        tipo_venta='online',
        estado='aceptado',
    )

    # CREAR ITEMS Y DESCONTAR STOCK
    for item in items:

        PedidoItem.objects.create(
            pedido=pedido,
            variante=item.variante,
            cantidad=item.cantidad,
            precio_unitario=item.precio_unitario,
            precio_total=item.precio_total
        )

        item.variante.stock -= item.cantidad
        item.variante.save()

    items_pedido = pedido.items.select_related(
        'variante__producto',
        'variante__talle'
    ).prefetch_related(
        'variante__colores'
    )

    productos_texto = []
    productos_html = []

    for item in items_pedido:
        colores = ', '.join(
            color.nombre
            for color in item.variante.colores.all()
        )
        talle = item.variante.talle.nombre if item.variante.talle else 'Sin talle'
        detalle_color = f' - Color: {colores}' if colores else ''

        productos_texto.append(
            f'- {item.variante.producto.nombre} '
            f'(Talle: {talle}{detalle_color}) '
            f'x{item.cantidad} - ${item.precio_total}'
        )
        productos_html.append(
            '<tr>'
            f'<td style="padding:14px 0;border-bottom:1px solid #efe7dc;">'
            f'<strong style="color:#1f1712;">{escape(item.variante.producto.nombre)}</strong>'
            f'<div style="font-size:13px;color:#786b60;margin-top:4px;">'
            f'Talle {escape(talle)}{escape(detalle_color)}'
            f'</div>'
            f'</td>'
            f'<td align="center" style="padding:14px 12px;border-bottom:1px solid #efe7dc;color:#1f1712;">'
            f'{item.cantidad}'
            f'</td>'
            f'<td align="right" style="padding:14px 0;border-bottom:1px solid #efe7dc;color:#1f1712;font-weight:700;">'
            f'${item.precio_total}'
            f'</td>'
            '</tr>'
        )

    nombre_cliente = pedido.cliente.user.first_name or pedido.cliente.user.username
    cliente_nombre_completo = (
        f'{pedido.cliente.user.first_name} {pedido.cliente.user.last_name}'
    ).strip() or pedido.cliente.user.username
    entrega_label = pedido.get_metodo_entrega_display()
    direccion_envio = 'Retiro en local'

    if pedido.metodo_entrega != 'local':
        direccion_envio = pedido.direccion_info or pedido.calle_numero or 'Direccion no informada'
        if pedido.localidad:
            direccion_envio += f', {pedido.localidad}'
        if pedido.codigo_postal:
            direccion_envio += f' ({pedido.codigo_postal})'

    if pedido.metodo_entrega == 'correo':
        correo_info = ', '.join(
            dato for dato in [
                pedido.correo,
                pedido.tipo_correo,
                pedido.sucursal_correo
            ]
            if dato
        )
        if correo_info:
            direccion_envio += f' - {correo_info}'

    productos_html_markup = ''.join(productos_html)
    productos_texto_markup = chr(10).join(productos_texto)
    admin_email = getattr(settings, 'EMAIL_HOST_USER', None) or getattr(settings, 'DEFAULT_FROM_EMAIL', None)

    html_cliente = f"""
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f6f1eb;font-family:Arial,Helvetica,sans-serif;color:#1f1712;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f6f1eb;padding:32px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;background:#fff;border-radius:18px;overflow:hidden;border:1px solid #eadfce;">
            <tr>
              <td style="background:#1f1712;padding:28px 32px;text-align:center;">
                <div style="font-family:Georgia,serif;font-size:30px;letter-spacing:.04em;color:#d2ad3f;">IndiraGold</div>
                <div style="font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:#eee3cf;margin-top:6px;">Pago aprobado</div>
              </td>
            </tr>
            <tr>
              <td style="padding:34px 34px 12px;">
                <p style="margin:0 0 8px;font-size:15px;color:#786b60;">Hola {escape(nombre_cliente)},</p>
                <h1 style="margin:0;font-family:Georgia,serif;font-size:30px;line-height:1.12;color:#6e0e2e;">Recibimos tu pago</h1>
                <p style="margin:14px 0 0;font-size:15px;line-height:1.6;color:#4e433b;">
                  Tu pedido <strong>#{pedido.id}</strong> fue registrado correctamente y el pago fue aceptado.
                </p>
              </td>
            </tr>
            <tr>
              <td style="padding:8px 34px 18px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#faf7f2;border-radius:14px;">
                  <tr>
                    <td style="padding:16px 18px;font-size:14px;color:#786b60;">Entrega</td>
                    <td align="right" style="padding:16px 18px;font-size:14px;font-weight:700;color:#1f1712;">{escape(entrega_label)}</td>
                  </tr>
                  <tr>
                    <td colspan="2" style="padding:0 18px 16px;font-size:13px;color:#786b60;text-align:right;">{escape(direccion_envio)}</td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:0 34px 8px;">
                <h2 style="margin:0 0 12px;font-family:Georgia,serif;font-size:22px;color:#1f1712;">Productos comprados</h2>
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">
                  <tr>
                    <th align="left" style="padding:0 0 10px;border-bottom:1px solid #d8cbbb;font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:#9b8978;">Producto</th>
                    <th align="center" style="padding:0 12px 10px;border-bottom:1px solid #d8cbbb;font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:#9b8978;">Cant.</th>
                    <th align="right" style="padding:0 0 10px;border-bottom:1px solid #d8cbbb;font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:#9b8978;">Subtotal</th>
                  </tr>
                  {productos_html_markup}
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:22px 34px 34px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#fff8df;border-radius:14px;border:1px solid #ead082;">
                  <tr>
                    <td style="padding:18px 20px;font-size:15px;color:#786b60;">Total abonado</td>
                    <td align="right" style="padding:18px 20px;font-size:22px;font-weight:800;color:#6e0e2e;">${pedido.total}</td>
                  </tr>
                </table>
                <p style="margin:22px 0 0;font-size:14px;line-height:1.6;color:#786b60;">
                  Te vamos a avisar por mail cada avance importante de tu compra.
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""

    html_admin = f"""
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f6f1eb;font-family:Arial,Helvetica,sans-serif;color:#1f1712;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f6f1eb;padding:32px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:680px;background:#fff;border-radius:18px;overflow:hidden;border:1px solid #eadfce;">
            <tr>
              <td style="background:#6e0e2e;padding:26px 32px;text-align:center;">
                <div style="font-family:Georgia,serif;font-size:28px;color:#f5d779;">Nueva compra pagada</div>
                <div style="font-size:12px;color:#f9e9ee;margin-top:7px;">Pedido #{pedido.id}</div>
              </td>
            </tr>
            <tr>
              <td style="padding:30px 34px 14px;">
                <h1 style="margin:0;font-family:Georgia,serif;font-size:28px;color:#1f1712;">{escape(cliente_nombre_completo)}</h1>
                <p style="margin:12px 0 0;font-size:14px;line-height:1.7;color:#4e433b;">
                  Email: <strong>{escape(pedido.cliente.user.email)}</strong><br>
                  DNI: <strong>{escape(pedido.cliente.dni)}</strong><br>
                  Telefono: <strong>{escape(pedido.cliente.telefono)}</strong>
                </p>
              </td>
            </tr>
            <tr>
              <td style="padding:8px 34px 18px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#faf7f2;border-radius:14px;">
                  <tr>
                    <td style="padding:16px 18px;font-size:14px;color:#786b60;">Envio elegido</td>
                    <td align="right" style="padding:16px 18px;font-size:14px;font-weight:700;color:#1f1712;">{escape(entrega_label)}</td>
                  </tr>
                  <tr>
                    <td colspan="2" style="padding:0 18px 16px;font-size:13px;color:#786b60;text-align:right;">{escape(direccion_envio)}</td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:0 34px 8px;">
                <h2 style="margin:0 0 12px;font-family:Georgia,serif;font-size:22px;color:#1f1712;">Productos</h2>
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">
                  <tr>
                    <th align="left" style="padding:0 0 10px;border-bottom:1px solid #d8cbbb;font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:#9b8978;">Producto</th>
                    <th align="center" style="padding:0 12px 10px;border-bottom:1px solid #d8cbbb;font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:#9b8978;">Cant.</th>
                    <th align="right" style="padding:0 0 10px;border-bottom:1px solid #d8cbbb;font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:#9b8978;">Subtotal</th>
                  </tr>
                  {productos_html_markup}
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:22px 34px 34px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#fff8df;border-radius:14px;border:1px solid #ead082;">
                  <tr>
                    <td style="padding:18px 20px;font-size:15px;color:#786b60;">Total cobrado</td>
                    <td align="right" style="padding:18px 20px;font-size:22px;font-weight:800;color:#6e0e2e;">${pedido.total}</td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""

    if pedido.cliente.user.email:
        send_mail(
            subject=f'Pago aprobado - Pedido #{pedido.id}',
            message=(
                f'Hola {nombre_cliente},\n\n'
                f'Tu pago fue aceptado y registramos el pedido #{pedido.id}.\n\n'
                f'Entrega: {entrega_label}\n'
                f'{direccion_envio}\n\n'
                f'Productos:\n{productos_texto_markup}\n\n'
                f'Total abonado: ${pedido.total}\n\n'
                f'Gracias por comprar en IndiraGold.'
            ),
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            recipient_list=[pedido.cliente.user.email],
            fail_silently=True,
            html_message=html_cliente
        )

    if admin_email:
        send_mail(
            subject=f'Nueva compra pagada - Pedido #{pedido.id}',
            message=(
                f'Nueva compra pagada.\n\n'
                f'Pedido: #{pedido.id}\n'
                f'Cliente: {cliente_nombre_completo}\n'
                f'Email: {pedido.cliente.user.email}\n'
                f'DNI: {pedido.cliente.dni}\n'
                f'Telefono: {pedido.cliente.telefono}\n\n'
                f'Envio: {entrega_label}\n'
                f'{direccion_envio}\n\n'
                f'Productos:\n{productos_texto_markup}\n\n'
                f'Total cobrado: ${pedido.total}'
            ),
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            recipient_list=[admin_email],
            fail_silently=True,
            html_message=html_admin
        )

    # VACIAR CARRITO
    carrito.items.all().delete()

    messages.success(
        request,
        "¡Tu pago fue realizado con éxito!"
    )

    return render(
        request,
        'pedidos/pago_exitoso.html',
        {
            'pedido': pedido
        }
    )
    
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

    # Determinar rango de fechas
    if tipo_periodo == 'personalizado' and fecha_inicio_str and fecha_fin_str:

        try:
            fecha_inicio = datetime.strptime(
                fecha_inicio_str,
                '%Y-%m-%d'
            ).date()

            fecha_fin = datetime.strptime(
                fecha_fin_str,
                '%Y-%m-%d'
            ).date()

        except ValueError:

            fecha_inicio = hoy - timedelta(days=30)
            fecha_fin = hoy

    elif tipo_periodo == '7dias':

        fecha_inicio = hoy - timedelta(days=7)
        fecha_fin = hoy

    elif tipo_periodo == '90dias':

        fecha_inicio = hoy - timedelta(days=90)
        fecha_fin = hoy

    else:

        fecha_inicio = hoy - timedelta(days=30)
        fecha_fin = hoy

    # Filtrar pedidos
    pedidos = Pedido.objects.filter(
        created_at__date__gte=fecha_inicio,
        created_at__date__lte=fecha_fin
    )

    # Estadísticas generales
    total_ventas = (
        pedidos.aggregate(Sum('total'))['total__sum']
        or Decimal('0.00')
    )

    cantidad_pedidos = pedidos.count()

    promedio_por_pedido = (
        total_ventas / cantidad_pedidos
        if cantidad_pedidos > 0
        else Decimal('0.00')
    )

    # Pedidos por estado
    pedidos_por_estado = (
        pedidos.values('estado')
        .annotate(
            cantidad=Count('id'),
            total=Sum('total')
        )
        .order_by('-cantidad')
    )

    estados_dict = {
        valor: label
        for valor, label in Pedido.ESTADOS
    }

    for item in pedidos_por_estado:

        item['estado_label'] = estados_dict.get(
            item['estado'],
            item['estado']
        )

    # Productos más vendidos
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

    # Ventas por tipo
    ventas_por_tipo = (
        pedidos.values('tipo_venta')
        .annotate(
            cantidad=Count('id'),
            total=Sum('total')
        )
        .order_by('-cantidad')
    )

    tipos_venta_dict = {
        valor: label
        for valor, label in Pedido.TIPOS_VENTA
    }

    for item in ventas_por_tipo:

        item['tipo_label'] = tipos_venta_dict.get(
            item['tipo_venta'],
            item['tipo_venta']
        )

    # Evolución diaria
    evolucion_diaria = []

    for i in range(31):

        fecha = hoy - timedelta(days=30 - i)

        pedidos_dia = Pedido.objects.filter(
            created_at__date=fecha
        )

        total_dia = (
            pedidos_dia.aggregate(Sum('total'))['total__sum']
            or Decimal('0.00')
        )

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

    return render(
        request,
        'pedidos/estadisticas_ventas.html',
        context
    )
@login_required
def estado_pedido(request, pedido_id):

    pedido = get_object_or_404(
        Pedido,
        id=pedido_id,
        cliente__user=request.user
    )

    if pedido.metodo_entrega == 'local':

        flujo = [
            'pendiente',
            'aceptado',
            'en_preparacion',
            'listo_retirar',
            'entregado'
        ]

    else:

        flujo = [
            'pendiente',
            'aceptado',
            'en_preparacion',
            'preparando_envio',
            'enviado',
            'entregado'
        ]

    nombres = {
        'pendiente': 'Pendiente de confirmación',
        'aceptado': 'Pago aceptado',
        'en_preparacion': 'En preparación',
        'listo_retirar': 'Listo para retirar',
        'preparando_envio': 'Preparando envío',
        'enviado': 'Paquete enviado',
        'entregado': 'Entregado',
    }

    indice_actual = flujo.index(pedido.estado)

    pasos = []

    for i, estado in enumerate(flujo):

        pasos.append({
            'nombre': nombres[estado],
            'descripcion': '',
            'completado': i < indice_actual,
            'actual': i == indice_actual,
        })

    return render(
        request,
        'pedidos/estado_pedido.html',
        {
            'pedido': pedido,
            'pasos': pasos
        }
    )
@login_required
def mis_pedidos(request):

    pedidos = Pedido.objects.filter(
        cliente__user=request.user
    ).order_by('-created_at')

    return render(
        request,
        'pedidos/mis_pedidos.html',
        {
            'pedidos': pedidos
        }
    )
@login_required
@require_POST
def aumentar_cantidad(request, variante_id):

    carrito = get_or_create_cart(request)

    item = get_object_or_404(
        CarritoItem,
        carrito=carrito,
        variante_id=variante_id
    )

    if item.cantidad < item.variante.stock:

        item.cantidad += 1
        item.save()

    else:

        messages.error(
            request,
            'No hay más stock disponible.'
        )

    return redirect('pedidos:checkout')
@login_required
@require_POST
def disminuir_cantidad(request, variante_id):

    carrito = get_or_create_cart(request)

    item = get_object_or_404(
        CarritoItem,
        carrito=carrito,
        variante_id=variante_id
    )

    item.cantidad -= 1

    if item.cantidad <= 0:
        item.delete()

    else:
        item.save()

    return redirect('pedidos:checkout')

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

@admin_required
@require_POST
def actualizar_estado_pedido(request, pedido_id):

    pedido = get_object_or_404(
        Pedido.objects.select_related(
            'cliente',
            'cliente__user'
        ).prefetch_related(
            'items__variante__producto',
            'items__variante__talle',
            'items__variante__colores',
        ),
        id=pedido_id
    )

    nuevo_estado = request.POST.get('estado')
    estado_anterior = pedido.estado

    estados_validos = [
        estado[0]
        for estado in Pedido.ESTADOS
    ]

    if nuevo_estado in estados_validos:

        pedido.estado = nuevo_estado
        pedido.save()

        if estado_anterior != nuevo_estado and pedido.cliente.user.email:
            estados_dict = dict(Pedido.ESTADOS)
            productos = []
            productos_html = []

            for item in pedido.items.all():
                colores = ', '.join(
                    color.nombre
                    for color in item.variante.colores.all()
                )
                talle = item.variante.talle.nombre if item.variante.talle else 'Sin talle'
                detalle_color = f' - Color: {colores}' if colores else ''

                productos.append(
                    f'- {item.variante.producto.nombre} '
                    f'(Talle: {talle}{detalle_color}) '
                    f'x{item.cantidad} - ${item.precio_total}'
                )
                productos_html.append(
                    '<tr>'
                    f'<td style="padding:14px 0;border-bottom:1px solid #efe7dc;">'
                    f'<strong style="color:#1f1712;">{escape(item.variante.producto.nombre)}</strong>'
                    f'<div style="font-size:13px;color:#786b60;margin-top:4px;">'
                    f'Talle {escape(talle)}{escape(detalle_color)}'
                    f'</div>'
                    f'</td>'
                    f'<td align="center" style="padding:14px 12px;border-bottom:1px solid #efe7dc;color:#1f1712;">'
                    f'{item.cantidad}'
                    f'</td>'
                    f'<td align="right" style="padding:14px 0;border-bottom:1px solid #efe7dc;color:#1f1712;font-weight:700;">'
                    f'${item.precio_total}'
                    f'</td>'
                    '</tr>'
                )

            estado_anterior_label = estados_dict.get(estado_anterior, estado_anterior)
            estado_nuevo_label = pedido.get_estado_display()
            nombre_cliente = pedido.cliente.user.first_name or pedido.cliente.user.username
            productos_html_markup = ''.join(productos_html)
            html_message = f"""
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f6f1eb;font-family:Arial,Helvetica,sans-serif;color:#1f1712;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f6f1eb;padding:32px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;background:#fff;border-radius:18px;overflow:hidden;border:1px solid #eadfce;">
            <tr>
              <td style="background:#1f1712;padding:28px 32px;text-align:center;">
                <div style="font-family:Georgia,serif;font-size:30px;letter-spacing:.04em;color:#d2ad3f;">IndiraGold</div>
                <div style="font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:#eee3cf;margin-top:6px;">Actualizacion de pedido</div>
              </td>
            </tr>
            <tr>
              <td style="padding:34px 34px 10px;">
                <p style="margin:0 0 8px;font-size:15px;color:#786b60;">Hola {escape(nombre_cliente)},</p>
                <h1 style="margin:0;font-family:Georgia,serif;font-size:30px;line-height:1.12;color:#6e0e2e;">Tu compra cambio de estado</h1>
                <p style="margin:14px 0 0;font-size:15px;line-height:1.6;color:#4e433b;">
                  Te avisamos que actualizamos el estado del pedido <strong>#{pedido.id}</strong>.
                </p>
              </td>
            </tr>
            <tr>
              <td style="padding:18px 34px 8px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                  <tr>
                    <td style="width:50%;padding:14px;background:#faf7f2;border:1px solid #efe7dc;border-radius:14px 0 0 14px;">
                      <div style="font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:#9b8978;">Antes</div>
                      <div style="font-size:15px;font-weight:700;color:#6e0e2e;margin-top:6px;">{escape(estado_anterior_label)}</div>
                    </td>
                    <td style="width:50%;padding:14px;background:#fff8df;border:1px solid #ead082;border-left:0;border-radius:0 14px 14px 0;">
                      <div style="font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:#9b7a18;">Ahora</div>
                      <div style="font-size:15px;font-weight:700;color:#6e0e2e;margin-top:6px;">{escape(estado_nuevo_label)}</div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:24px 34px 8px;">
                <h2 style="margin:0 0 12px;font-family:Georgia,serif;font-size:22px;color:#1f1712;">Productos comprados</h2>
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">
                  <tr>
                    <th align="left" style="padding:0 0 10px;border-bottom:1px solid #d8cbbb;font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:#9b8978;">Producto</th>
                    <th align="center" style="padding:0 12px 10px;border-bottom:1px solid #d8cbbb;font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:#9b8978;">Cant.</th>
                    <th align="right" style="padding:0 0 10px;border-bottom:1px solid #d8cbbb;font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:#9b8978;">Subtotal</th>
                  </tr>
                  {productos_html_markup}
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:22px 34px 34px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#faf7f2;border-radius:14px;">
                  <tr>
                    <td style="padding:18px 20px;font-size:15px;color:#786b60;">Total del pedido</td>
                    <td align="right" style="padding:18px 20px;font-size:22px;font-weight:800;color:#6e0e2e;">${pedido.total}</td>
                  </tr>
                </table>
                <p style="margin:22px 0 0;font-size:14px;line-height:1.6;color:#786b60;">
                  Gracias por comprar en IndiraGold. Te vamos a seguir avisando cada avance importante de tu pedido.
                </p>
              </td>
            </tr>
          </table>
          <div style="max-width:640px;margin-top:16px;font-size:12px;color:#9b8978;text-align:center;">
            IndiraGold
          </div>
        </td>
      </tr>
    </table>
  </body>
</html>
"""

            send_mail(
                subject=f'Actualizacion de tu pedido #{pedido.id}',
                message=(
                    f'Hola {nombre_cliente},\n\n'
                    f'Te avisamos que el estado de tu compra cambio.\n\n'
                    f'Pedido: #{pedido.id}\n'
                    f'Estado anterior: {estado_anterior_label}\n'
                    f'Estado nuevo: {estado_nuevo_label}\n\n'
                    f'Productos comprados:\n'
                    f'{chr(10).join(productos)}\n\n'
                    f'Total del pedido: ${pedido.total}\n\n'
                    f'Gracias por comprar en IndiraGold.'
                ),
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                recipient_list=[pedido.cliente.user.email],
                fail_silently=True,
                html_message=html_message
            )

        messages.success(
            request,
            f'Estado del pedido #{pedido.id} actualizado.'
        )

        return redirect('pedidos:gestion_pedidos')

    return redirect('pedidos:gestion_pedidos')


@admin_required
def ventas_presenciales(request):

    ventas = VentaLocal.objects.select_related(
        'cliente',
        'cliente__user'
    ).prefetch_related('items').order_by('-created_at')

    # FILTROS

    q = request.GET.get('q', '')
    dia = request.GET.get('dia', '')
    mes = request.GET.get('mes', '')
    anio = request.GET.get('anio', '')

    if q:

        ventas = ventas.filter(

            Q(cliente__user__first_name__icontains=q)

            |

            Q(cliente__user__last_name__icontains=q)

            |

            Q(cliente__user__email__icontains=q)

        )

    if dia:

        ventas = ventas.filter(
            created_at__day=dia
        )

    if mes:

        ventas = ventas.filter(
            created_at__month=mes
        )

    if anio:

        ventas = ventas.filter(
            created_at__year=anio
        )

    # PAGINACIÓN

    paginator = Paginator(
        ventas,
        10
    )

    page_number = request.GET.get('page')

    page_obj = paginator.get_page(
        page_number
    )

    return render(
        request,
        'pedidos/ventas_presenciales.html',
        {
            'ventas': page_obj.object_list,
            'page_obj': page_obj,
            'q': q,
            'dia': dia,
            'mes': mes,
            'anio': anio,
        }
    )
@require_POST
@admin_required
@transaction.atomic
def registrar_venta_local(request):

    data = json.loads(request.body)

    cliente_id = data.get('cliente_id')

    productos = data.get('productos')

    if not cliente_id or not productos:

        return JsonResponse({

            'success': False

        })

    cliente = Cliente.objects.get(
        user_id=cliente_id
    )

    total = 0

    monto_pagado = Decimal(
        str(data.get('monto_pagado', 0))
    )

    venta = VentaLocal.objects.create(

        cliente=cliente,

        total=0,

        monto_pagado=0,

        saldo_pendiente=0,

        estado_pago='PAGADO'
    )

    for item in productos:

        variante = Variante.objects.get(
            id=item['variante_id']
        )

        cantidad = int(item['cantidad'])

        subtotal = (
            variante.precio * cantidad
        )

        VentaLocalItem.objects.create(

            venta=venta,

            producto=variante.producto,

            variante=variante,

            color=item['color'],

            cantidad=cantidad,

            precio_unitario=variante.precio,

            subtotal=subtotal

        )

        # DESCONTAR STOCK VARIANTE

        variante.stock -= cantidad

        variante.save()

        # DESCONTAR STOCK PRODUCTO

        producto = variante.producto

        producto.stock -= cantidad

        producto.save()

        total += subtotal

    venta.total = total
    saldo_pendiente = total - monto_pagado

    if saldo_pendiente > 0:
        estado_pago = 'PARCIAL'
    else:
        estado_pago = 'PAGADO'

    venta.total = total
    venta.monto_pagado = monto_pagado
    venta.saldo_pendiente = saldo_pendiente
    venta.estado_pago = estado_pago

    venta.save()
    if monto_pagado > 0:

        PagoVentaLocal.objects.create(

            venta=venta,

            monto=monto_pagado
        )

    return JsonResponse({

        'success': True

    })
def detalle_venta_local(request, venta_id):

    venta = get_object_or_404(
        VentaLocal,
        id=venta_id
    )

    items = venta.items.all()

    data = {

        'cliente': (
            f'{venta.cliente.user.first_name} '
            f'{venta.cliente.user.last_name}'
        ),

        'fecha': venta.created_at.strftime(
            '%d/%m/%Y %H:%M'
        ),

        'total': float(venta.total),
        'pagado': float(venta.monto_pagado),

        'pendiente': float(venta.saldo_pendiente),

        'estado': venta.estado_pago,
        'productos': []

    }

    for item in items:

        data['productos'].append({

            'producto': item.producto.nombre,

            'talle': item.variante.talle.nombre,

            'color': item.color,

            'cantidad': item.cantidad,

            'subtotal': float(item.subtotal)

        })

    return JsonResponse(data)
@require_POST
@admin_required
def registrar_pago_venta(request, venta_id):

    venta = get_object_or_404(
        VentaLocal,
        id=venta_id
    )

    data = json.loads(request.body)

    monto = Decimal(
        str(data.get('monto', 0))
    )

    venta.monto_pagado += monto

    venta.saldo_pendiente = (
        venta.total - venta.monto_pagado
    )

    if venta.saldo_pendiente <= 0:

        venta.saldo_pendiente = 0

        venta.estado_pago = 'PAGADO'

    venta.save()

    PagoVentaLocal.objects.create(

        venta=venta,

        monto=monto
    )

    items = venta.items.all()

    html = f"""
    <div class="mb-3">

        <div class="d-flex justify-content-between">

            <span>Total</span>

            <span class="fw-bold">
                ${venta.total}
            </span>

        </div>

        <div class="d-flex justify-content-between">

            <span>Pagado</span>

            <span class="fw-bold text-success">
                ${venta.monto_pagado}
            </span>

        </div>

        <div class="d-flex justify-content-between">

            <span>Pendiente</span>

            <span class="fw-bold text-danger">
                ${venta.saldo_pendiente}
            </span>

        </div>

    </div>
    """

    return JsonResponse({

        'success': True,

        'html': html,

        'estado': venta.estado_pago
    })
@admin_required
def configurar_envios(request):
    configuracion = ConfiguracionEnvio.actual()

    if request.method == 'POST':
        form = ConfiguracionEnvioForm(request.POST, instance=configuracion)
        if form.is_valid():
            configuracion = form.save(commit=False)
            configuracion.flex_activo = True
            configuracion.save()
            messages.success(request, 'Configuración de envíos actualizada correctamente.')
            return redirect('pedidos:configurar_envios')
    else:
        form = ConfiguracionEnvioForm(instance=configuracion)

    return render(request, 'pedidos/configurar_envios.html', {
        'form': form,
        'configuracion': configuracion,
        'zonas_flex': configuracion.zonas_flex_lista,
    })
