from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db import transaction
from django.contrib import messages
from django.db.models import Sum, Count, Avg, Q, F
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from .models import (
    Pedido,
    PedidoItem,
    Pago,
    PagoPedido,
    EnvioPedido,
    VentaLocal,
    PagoVentaLocal,
    ConfiguracionEnvio,
    ConfiguracionPago,
    PlanCuotasMercadoPago,
    OpcionEnvioFlex,
    Cambio,
    NotaCredito,
    NotaCreditoItem,
)
from carritos.models import Carrito, CarritoItem
from carritos.utils import get_or_create_cart, vincular_carrito_con_usuario
from .models import Pedido, PedidoItem, Gasto, VentaLocal, VentaLocalItem
from .forms import GastoForm, ConfiguracionEnvioForm, ConfiguracionPagoForm

from pedidos.forms import GastoForm, ConfiguracionEnvioForm, ConfiguracionPagoForm
from .models import Gasto, Pedido, PedidoItem
from carritos.models import Carrito, CarritoItem
from carritos.utils import clear_cart_session, get_or_create_cart, vincular_carrito_con_usuario, get_cart_seconds_left, refrescar_precios_carrito, precio_unitario_vigente
from users.models import Cliente, Direccion, direcciones_sin_duplicados
from productos.models import Variante, Oferta
from productos.stock import descontar_stock, reponer_stock, stock_disponible, validar_stock
import mercadopago
from django.conf import settings
from config.contacto import whatsapp_numero, whatsapp_numero_visible
from django.views.decorators.http import require_POST
from django.core.mail import send_mail
from django.conf import settings
from django.db.models import Q
from django.core.paginator import Paginator
import json
import unicodedata
from urllib.parse import quote
import uuid
import base64
import io
import qrcode

from django.http import Http404, JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils.html import escape
from django.utils import timezone
from .servicios_envio import ErrorEnvio, calcular_paquete_envio, cotizar_correo_argentino
print("===== PEDIDOS VIEWS CARGADO =====")
print("TOKEN MP:", settings.MERCADO_PAGO_ACCESS_TOKEN)
# Decorador para verificar que es administrador
def admin_required(view_func):
    return login_required(login_url="/users/login/")(user_passes_test(lambda u: u.is_superuser, login_url="/users/login/")(view_func))


def formato_pesos(valor):
    return f"${int(valor):,}".replace(",", ".")


def leer_monto(valor):
    """Convierte un monto ingresado por el usuario a Decimal con 2 decimales.
    Devuelve None si está vacío, no es numérico o no es finito."""
    if valor is None:
        return None
    try:
        monto = Decimal(str(valor).strip().replace(',', '.'))
    except (InvalidOperation, ValueError):
        return None
    if not monto.is_finite() or abs(monto) >= Decimal('1e12'):
        return None
    return monto.quantize(Decimal('0.01'))


def monto_decimal(valor):
    return Decimal(valor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def vaciar_carrito_completo(request, carrito):
    """Vacía el carrito de la BD y la sesión completamente."""
    carrito.items.all().delete()
    carrito.activo = False
    carrito.save()
    clear_cart_session(request.session)
    request.session.pop('codigo_descuento', None)
    request.session.pop('descuento_monto', None)
    request.session.modified = True


def buscar_cupon(codigo):
    """(cupon, motivo): el cupón si se puede usar ahora, o None y el motivo por el que no."""
    codigo_normalizado = (codigo or '').strip().upper()
    if not codigo_normalizado:
        return None, None
    cupon = Oferta.objects.filter(
        codigo__iexact=codigo_normalizado,
        es_cupon=True,
    ).first()
    if not cupon:
        return None, 'El código no existe.'
    puede, motivo = cupon.puede_usarse()
    if not puede:
        return None, motivo
    return cupon, None


def obtener_cupon_activo(codigo):
    return buscar_cupon(codigo)[0]


def calcular_descuento_cupon(subtotal, codigo):
    cupon = obtener_cupon_activo(codigo)
    if not cupon:
        return None, Decimal('0.00')
    descuento = monto_decimal(Decimal(subtotal) * Decimal(cupon.descuento) / Decimal(100))
    return cupon, min(descuento, Decimal(subtotal))


def whatsapp_comprobante_url(pedido):
    numero = whatsapp_numero()
    cliente = pedido.cliente
    nombre_completo = f'{cliente.user.first_name} {cliente.user.last_name}'.strip() or cliente.user.username
    email = cliente.user.email or 'Sin email'
    mensaje = (
        f'Hola IndiraGold, te envio el comprobante del pedido #{pedido.id}.\n\n'
        f'Cliente: {nombre_completo}\n'
        f'Email: {email}\n'
        f'Total: ${pedido.total}'
    )
    return f'https://wa.me/{numero}?text={quote(mensaje)}'


def whatsapp_transferencia_url(pedido):
    numero = whatsapp_numero()
    cliente = pedido.cliente
    nombre_completo = f'{cliente.user.first_name} {cliente.user.last_name}'.strip() or cliente.user.username
    email = cliente.user.email or 'Sin email'
    mensaje = (
        f'Hola IndiraGold, te envio el comprobante de transferencia del pedido #{pedido.id}.\n\n'
        f'Cliente: {nombre_completo}\n'
        f'Email: {email}\n'
        f'Total: ${pedido.total}'
    )
    return f'https://wa.me/{numero}?text={quote(mensaje)}'


def enviar_email_confirmacion_pedido(pedido):
    """Envía email de confirmación al cliente cuando se crea un pedido."""
    items_pedido = pedido.items.select_related(
        'variante__producto',
        'variante__talle'
    ).prefetch_related('variante__colores')

    productos_html = []
    for item in items_pedido:
        colores = item.color_nombre or ', '.join(
            color.nombre for color in item.variante.colores.all()
        )
        talle = item.variante.talle.nombre if item.variante.talle else 'Sin talle'
        detalle_color = f' - Color: {colores}' if colores else ''
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
    metodo_pago_display = {
        'mercado_pago': 'Mercado Pago',
        'transferencia': 'Transferencia bancaria',
        'efectivo': 'Efectivo en local',
        'mercado_pago_qr': 'QR de Mercado Pago',
    }.get(pedido.metodo_pago, pedido.metodo_pago)

    estado_display = pedido.get_estado_display()
    entrega_display = pedido.get_metodo_entrega_display()

    mensaje_estado = ""
    if pedido.metodo_pago in ['transferencia', 'efectivo', 'mercado_pago_qr']:
        mensaje_estado = """
        <div style="background:#fff8e6;border:1px solid #f5d67a;border-radius:10px;padding:16px;margin:20px 0;">
          <p style="margin:0;color:#8a6d00;font-size:14px;">
            <strong>⏳ Tu pedido está pendiente de confirmación.</strong><br>
            La administradora revisará tu pedido y actualizará el estado. Te notificaremos por email cuando haya novedades.
          </p>
        </div>
        """

    html_email = f"""
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
                <div style="font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:#eee3cf;margin-top:6px;">Confirmación de pedido</div>
              </td>
            </tr>
            <tr>
              <td style="padding:34px 34px 12px;">
                <p style="margin:0 0 18px;font-size:16px;line-height:1.6;">
                  Hola <strong>{escape(nombre_cliente)}</strong>,
                </p>
                <p style="margin:0 0 18px;font-size:16px;line-height:1.6;">
                  Recibimos tu pedido <strong>#{pedido.id}</strong>. Acá te dejamos los detalles:
                </p>

                {mensaje_estado}

                <div style="background:#faf7f2;border-radius:12px;padding:20px;margin:20px 0;">
                  <table style="width:100%;font-size:14px;">
                    <tr>
                      <td style="padding:8px 0;color:#786b60;">Método de pago:</td>
                      <td style="padding:8px 0;text-align:right;font-weight:700;">{escape(metodo_pago_display)}</td>
                    </tr>
                    <tr>
                      <td style="padding:8px 0;color:#786b60;">Estado:</td>
                      <td style="padding:8px 0;text-align:right;font-weight:700;">{escape(estado_display)}</td>
                    </tr>
                    <tr>
                      <td style="padding:8px 0;color:#786b60;">Entrega:</td>
                      <td style="padding:8px 0;text-align:right;font-weight:700;">{escape(entrega_display)}</td>
                    </tr>
                  </table>
                </div>

                <h3 style="margin:28px 0 14px;font-size:14px;text-transform:uppercase;letter-spacing:.1em;color:#6e0e2e;font-weight:700;">
                  Productos
                </h3>
                <table style="width:100%;border-collapse:collapse;font-size:14px;">
                  {''.join(productos_html)}
                </table>

                <div style="border-top:2px solid #1f1712;margin-top:20px;padding-top:16px;text-align:right;">
                  <span style="font-size:14px;color:#786b60;">Total:</span>
                  <span style="font-size:24px;font-weight:700;color:#6e0e2e;margin-left:12px;">${pedido.total}</span>
                </div>
              </td>
            </tr>
            <tr>
              <td style="padding:24px 34px 34px;text-align:center;">
                <p style="margin:0;font-size:13px;color:#786b60;">
                  ¿Tenés dudas? Escribinos por WhatsApp al {whatsapp_numero_visible()}
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

    admin_email = getattr(settings, 'EMAIL_HOST_USER', None)
    if pedido.cliente.user.email:
        send_mail(
            subject=f'Pedido #{pedido.id} - IndiraGold',
            message=f'Recibimos tu pedido #{pedido.id}. Total: ${pedido.total}. Método de pago: {metodo_pago_display}.',
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', admin_email),
            recipient_list=[pedido.cliente.user.email],
            fail_silently=True,
            html_message=html_email
        )


@login_required
def enviar_comprobante_transferencia(request, pedido_id):
    pedido = get_object_or_404(Pedido, pk=pedido_id, cliente__user=request.user)
    carrito = get_or_create_cart(request)
    vaciar_carrito_completo(request, carrito)
    return redirect(whatsapp_transferencia_url(pedido))


def qr_manual_image_url():
    url = (getattr(settings, 'MERCADO_PAGO_QR_IMAGE_URL', '') or '').strip()
    if not url or 'url-del-qr' in url:
        return ''
    return url


def qr_data_a_imagen_base64(qr_data):
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"


def crear_qr_link_pago_mercado_pago(productos, external_reference):
    site_url = settings.SITE_URL.rstrip('/')
    preference_response = sdk.preference().create({
        "items": productos,
        "external_reference": external_reference,
        "back_urls": {
            "success": f"{site_url}/pedidos/mis-pedidos/",
            "failure": f"{site_url}/pedidos/checkout/",
            "pending": f"{site_url}/pedidos/mis-pedidos/"
        },
        "payment_methods": {
            "excluded_payment_types": [
                {"id": "ticket"},
                {"id": "atm"},
                {"id": "bank_transfer"}
            ]
        }
    })

    if preference_response.get("status") not in [200, 201]:
        mp_error = preference_response.get("response", {})
        detalle = mp_error.get("message") or mp_error.get("error") or str(mp_error)
        raise ValueError(f"Mercado Pago respondio: {detalle}")

    preference = preference_response.get("response", {})
    init_point = preference.get("init_point")
    if not init_point:
        raise ValueError("Mercado Pago no devolvio el link para generar el QR.")

    return {
        'payment_url': init_point,
        'qr_image': qr_data_a_imagen_base64(init_point),
    }


def normalizar_zona(valor):
    texto = unicodedata.normalize('NFKD', str(valor or ''))
    texto = ''.join(caracter for caracter in texto if not unicodedata.combining(caracter))
    return ' '.join(texto.casefold().split())


def direccion_en_zona_flex(direccion, zonas_flex):
    if not direccion or not zonas_flex:
        return False

    ubicacion = normalizar_zona(
        f'{direccion.ciudad} {direccion.provincia} {direccion.codigo_postal}'
    )

    return any(
        normalizar_zona(zona) in ubicacion
        for zona in zonas_flex
    )


def costo_envio_checkout(metodo_entrega, configuracion_envio):
    if metodo_entrega == 'flex' and configuracion_envio.flex_activo:
        return Decimal(configuracion_envio.costo_flex)
    if metodo_entrega == 'correo' and configuracion_envio.correo_activo:
        return Decimal('0')  # Se cotiza con la API de Correo Argentino
    return Decimal('0')


def costo_correo_argentino_desde_sesion(request, codigo_postal, tipo_entrega, items=None):
    cotizacion = request.session.get('correo_cotizacion') or {}
    paquete = calcular_paquete_envio(items or [])
    if (
        cotizacion.get('codigo_postal') == codigo_postal
        and cotizacion.get('tipo_entrega') == tipo_entrega
        and cotizacion.get('paquete') == paquete
        and cotizacion.get('importe')
    ):
        return monto_decimal(Decimal(str(cotizacion['importe'])))

    importe, detalle = cotizar_correo_argentino(codigo_postal, tipo_entrega, items)
    request.session['correo_cotizacion'] = {
        'importe': str(importe),
        'codigo_postal': codigo_postal,
        'tipo_entrega': tipo_entrega,
        'paquete': paquete,
        'detalle': detalle,
    }
    request.session.modified = True
    return importe


def crear_envio_pedido(pedido):
    if pedido.metodo_entrega == 'local':
        return None

    if pedido.metodo_entrega == 'flex':
        return EnvioPedido.objects.get_or_create(
            pedido=pedido,
            defaults={
                'proveedor': 'flex',
                'tipo_entrega': 'domicilio',
                'costo': pedido.costo_envio,
            }
        )[0]

    if pedido.metodo_entrega == 'correo':
        envio, created = EnvioPedido.objects.get_or_create(
            pedido=pedido,
            defaults={
                'proveedor': pedido.correo or 'correo_argentino',
                'tipo_entrega': pedido.tipo_correo or 'domicilio',
                'sucursal': pedido.sucursal_correo,
                'sucursal_id': pedido.sucursal_correo_id,
                'costo': pedido.costo_envio,
            }
        )

        return envio

    return None


def url_seguimiento_envio(envio):
    if not envio or not envio.tracking:
        return ''
    if envio.proveedor == 'correo_argentino':
        return 'https://www.correoargentino.com.ar/formularios/e-commerce'
    return ''


def errores_stock_items(lineas):
    """Valida stock (por color cuando corresponde) de una lista de (variante, color_nombre, cantidad),
    sumando las líneas del mismo talle y color. Devuelve una lista de mensajes de error."""
    acumulado = {}
    for variante, color_nombre, cantidad in lineas:
        clave = (variante.id, (color_nombre or '').strip().lower())
        if clave not in acumulado:
            acumulado[clave] = [variante, color_nombre, 0]
        acumulado[clave][2] += cantidad

    errores = []
    for variante, color_nombre, cantidad in acumulado.values():
        try:
            validar_stock(variante, cantidad, color_nombre)
        except ValueError as error:
            errores.append(str(error))
    return errores


def descontar_stock_pedido(pedido):
    items = list(pedido.items.select_related('variante__producto', 'variante__talle'))
    errores = errores_stock_items(
        (item.variante, item.color_nombre, item.cantidad) for item in items
    )
    if errores:
        raise ValueError(' '.join(errores))

    for item in items:
        descontar_stock(item.variante, item.cantidad, item.color_nombre)


def descontar_stock_variante(variante, cantidad, color_nombre=None):
    descontar_stock(variante, cantidad, color_nombre)


def reponer_stock_pedido(pedido):
    for item in pedido.items.select_related('variante__producto', 'variante__talle'):
        reponer_stock(item.variante, item.cantidad, item.color_nombre)


def cambiar_estado_pedido(pedido, nuevo_estado):
    """Aplica un cambio de estado respetando Pedido.TRANSICIONES y moviendo el stock una sola vez:
    se descuenta al aceptar un pedido pendiente y se repone al cancelar uno que ya lo había
    descontado. No guarda el pedido. Lanza ValueError si el cambio no está permitido."""
    estado_anterior = pedido.estado
    if nuevo_estado == estado_anterior:
        return False

    if nuevo_estado not in pedido.estados_siguientes():
        nombres = dict(Pedido.ESTADOS)
        raise ValueError(
            f'No se puede pasar un pedido de "{nombres.get(estado_anterior, estado_anterior)}" '
            f'a "{nombres.get(nuevo_estado, nuevo_estado)}".'
        )

    if (
        estado_anterior == 'pendiente'
        and nuevo_estado == 'aceptado'
        and pedido.metodo_pago in ['mercado_pago_qr', 'efectivo', 'transferencia']
    ):
        descontar_stock_pedido(pedido)

    if estado_anterior in Pedido.ESTADOS_CON_STOCK_DESCONTADO and nuevo_estado == 'cancelado':
        reponer_stock_pedido(pedido)

    pedido.estado = nuevo_estado
    return True


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
def listado_deudas(request):
    """
    Listado de deudas pendientes: pedidos online y ventas presenciales con saldo.
    """
    pedidos_con_deuda = Pedido.objects.filter(
        deuda__gt=0
    ).select_related('cliente__user').order_by('-deuda')

    ventas_con_deuda = VentaLocal.objects.filter(
        saldo_pendiente__gt=0
    ).select_related('cliente__user')

    # Búsqueda por cliente o número de pedido/venta
    q = request.GET.get('q', '').strip()
    if q:
        filtro_cliente = (
            Q(cliente__user__first_name__icontains=q) |
            Q(cliente__user__last_name__icontains=q) |
            Q(cliente__dni__icontains=q) |
            Q(id__icontains=q)
        )
        pedidos_con_deuda = pedidos_con_deuda.filter(filtro_cliente)
        ventas_con_deuda = ventas_con_deuda.filter(filtro_cliente)

    deudas = [
        {
            'tipo': 'Pedido',
            'id': pedido.id,
            'cliente': pedido.cliente,
            'fecha': pedido.created_at,
            'total': pedido.total,
            'pagado': pedido.monto_pagado,
            'pendiente': pedido.deuda,
            'url': reverse('pedidos:detalle_pedido', args=[pedido.id]),
        }
        for pedido in pedidos_con_deuda
    ] + [
        {
            'tipo': 'Venta local',
            'id': venta.id,
            'cliente': venta.cliente,
            'fecha': venta.created_at,
            'total': venta.total,
            'pagado': venta.monto_pagado,
            'pendiente': venta.saldo_pendiente,
            'url': f"{reverse('pedidos:ventas_presenciales')}?venta={venta.id}",
        }
        for venta in ventas_con_deuda
    ]
    deudas.sort(key=lambda deuda: deuda['pendiente'], reverse=True)

    total_deudas = sum((deuda['pendiente'] for deuda in deudas), Decimal('0.00'))

    context = {
        'deudas': deudas,
        'total_deudas': total_deudas,
        'cantidad': len(deudas),
        'q': q,
    }
    return render(request, 'pedidos/listado_deudas.html', context)


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


def opciones_variantes_con_stock():
    """Opciones "<variante_id>|<color>" de talles (y colores, si el talle tiene stock por color)
    con stock, para elegir qué producto se entrega en cambios o se agrega a un pedido."""
    opciones = []
    for variante in Variante.objects.filter(
        activa=True,
        stock__gt=0
    ).select_related('producto', 'talle').prefetch_related('variante_colores__color').order_by('producto__nombre', 'talle__nombre'):
        colores_activos = [vc for vc in variante.variante_colores.all() if vc.activo]
        etiqueta = f'{variante.producto.nombre} - Talle {variante.talle.nombre}'
        if colores_activos:
            for vc in colores_activos:
                if vc.stock > 0:
                    opciones.append({
                        'valor': f'{variante.id}|{vc.color.nombre}',
                        'etiqueta': f'{etiqueta} - {vc.color.nombre} (Stock: {vc.stock})',
                    })
        else:
            opciones.append({
                'valor': f'{variante.id}|',
                'etiqueta': f'{etiqueta} (Stock: {variante.stock})',
            })
    return opciones


@admin_required
def detalle_pedido(request, pedido_id):
    """
    Muestra el detalle completo de un pedido.
    """
    from productos.models import Variante

    pedido = get_object_or_404(
        Pedido.objects.select_related('cliente', 'cliente__user', 'envio').prefetch_related(
            'items__variante__producto',
            'items__variante__talle',
            'items__variante__colores',
            'pagos_registrados',
            'cambios__producto_devuelto',
            'cambios__producto_entregado',
            'cambios__variante_devuelta__talle',
            'cambios__variante_entregada__talle',
            'notas_credito',
        ),
        pk=pedido_id,
    )
    pago = getattr(pedido, 'pago', None)
    pagos_registrados = pedido.pagos_registrados.all()
    saldo_pendiente = pedido.total - pedido.monto_pagado

    # Talles (y colores, si el talle tiene stock por color) disponibles para cambios
    variantes_disponibles = opciones_variantes_con_stock()

    context = {
        'pedido': pedido,
        'pago': pago,
        'pagos_registrados': pagos_registrados,
        'saldo_pendiente': saldo_pendiente,
        'subtotal_items': sum((item.precio_total for item in pedido.items.all()), Decimal('0.00')),
        'items_devolvibles': [(item, unidades_devolvibles(item)) for item in pedido.items.all()],
        'admite_nota_credito': pedido.estado in Pedido.ESTADOS_CON_STOCK_DESCONTADO,
        'items_cambiables': [(item, unidades_cambiables(item)) for item in pedido.items.all()],
        'items': pedido.items.all(),
        'variantes_disponibles': variantes_disponibles,
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
        # Si el pedido ya descontó stock (aceptado en adelante), los cambios de cantidad o de
        # ítems mueven stock (talle y color); si está pendiente, solo se valida que alcance.
        stock_descontado = pedido.estado in Pedido.ESTADOS_CON_STOCK_DESCONTADO
        try:
            with transaction.atomic():
                ids_a_eliminar = set(request.POST.getlist('eliminar_item'))
                for item in list(PedidoItem.objects.filter(pedido=pedido).select_related('variante__producto', 'variante__talle')):
                    try:
                        nueva_cantidad = int(request.POST.get(f'cantidad_{item.id}', item.cantidad))
                    except (TypeError, ValueError):
                        nueva_cantidad = item.cantidad

                    if str(item.id) in ids_a_eliminar or nueva_cantidad <= 0:
                        if stock_descontado:
                            reponer_stock(item.variante, item.cantidad, item.color_nombre)
                        item.delete()
                        continue

                    diferencia = nueva_cantidad - item.cantidad
                    if diferencia > 0:
                        if stock_descontado:
                            descontar_stock(item.variante, diferencia, item.color_nombre)
                        else:
                            validar_stock(item.variante, nueva_cantidad, item.color_nombre)
                    elif diferencia < 0 and stock_descontado:
                        reponer_stock(item.variante, -diferencia, item.color_nombre)

                    if diferencia:
                        item.cantidad = nueva_cantidad
                        item.precio_total = item.precio_unitario * nueva_cantidad
                        item.save()

                # Agregar nuevo item ("<variante_id>|<color>")
                variante_valor = request.POST.get('nueva_variante_id') or ''
                cantidad_nueva = request.POST.get('nueva_cantidad')
                if variante_valor and cantidad_nueva:
                    variante_id, _, color_nuevo = variante_valor.partition('|')
                    variante = Variante.objects.filter(id=variante_id).select_related('producto', 'talle').first()
                    try:
                        cantidad_nueva_int = int(cantidad_nueva)
                    except (TypeError, ValueError):
                        cantidad_nueva_int = 0
                    if variante and cantidad_nueva_int > 0:
                        if stock_descontado:
                            descontar_stock(variante, cantidad_nueva_int, color_nuevo or None)
                        else:
                            validar_stock(variante, cantidad_nueva_int, color_nuevo or None)
                        precio_unitario = precio_unitario_vigente(variante)
                        PedidoItem.objects.create(
                            pedido=pedido,
                            variante=variante,
                            color_nombre=color_nuevo or None,
                            cantidad=cantidad_nueva_int,
                            precio_unitario=precio_unitario,
                            precio_total=precio_unitario * cantidad_nueva_int,
                        )

                items_finales = list(PedidoItem.objects.filter(pedido=pedido))
                if not items_finales:
                    raise ValueError(
                        'El pedido tiene que tener al menos un producto. Si ya no corresponde, cambiá su estado a Cancelado.'
                    )

                pedido.metodo_entrega = request.POST.get('metodo_entrega', pedido.metodo_entrega)
                pedido.codigo_postal = request.POST.get('codigo_postal', pedido.codigo_postal)
                pedido.localidad = request.POST.get('localidad', pedido.localidad)
                pedido.calle_numero = request.POST.get('calle_numero', pedido.calle_numero)

                # El costo de envío se conserva; solo el retiro en local no tiene envío
                if pedido.metodo_entrega == 'local':
                    pedido.costo_envio = Decimal('0.00')

                # Actualizar dirección
                direccion_info = request.POST.get('direccion_info', '').strip()
                if direccion_info:
                    pedido.direccion_info = direccion_info

                # Actualizar estado (mismas reglas y movimiento de stock que en la gestión de pedidos)
                nuevo_estado = request.POST.get('estado', pedido.estado)
                if nuevo_estado in dict(Pedido.ESTADOS) and nuevo_estado != pedido.estado:
                    cambiar_estado_pedido(pedido, nuevo_estado)

                # Total = ítems - descuento + envío, y la deuda acompaña al total
                subtotal_items = sum((item.precio_total for item in items_finales), Decimal('0.00'))
                if pedido.descuento_porcentaje:
                    pedido.descuento_monto = monto_decimal(
                        subtotal_items * Decimal(pedido.descuento_porcentaje) / Decimal(100)
                    )
                pedido.descuento_monto = min(pedido.descuento_monto or Decimal('0.00'), subtotal_items)
                pedido.total = subtotal_items - pedido.descuento_monto + (pedido.costo_envio or Decimal('0.00'))
                pedido.deuda = max(pedido.total - pedido.monto_pagado, Decimal('0.00'))
                pedido.save()
        except ValueError as error:
            messages.error(request, str(error))
            return redirect('pedidos:editar_pedido', pedido_id=pedido.id)

        messages.success(request, 'Pedido actualizado correctamente.')
        return redirect('pedidos:detalle_pedido', pedido_id=pedido.id)

    # GET: mostrar form
    variantes_disponibles = opciones_variantes_con_stock()
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
    # Administradores no pueden hacer checkout
    if request.user.is_superuser or request.user.is_staff:
        messages.error(request, "Los administradores no pueden realizar compras.")
        return redirect("home:home")

    carrito = get_or_create_cart(request)
    if carrito is None:
        messages.error(request, "No se pudo acceder al carrito.")
        return redirect("home:home")

    # Precios al día (ofertas, cambios de precio) antes de mostrar el resumen
    refrescar_precios_carrito(carrito)

    # Traemos los items con sus variantes y fotos
    items = carrito.items.all().select_related('variante__producto', 'variante__talle')
    configuracion_envio = ConfiguracionEnvio.actual()
    configuracion_pago = ConfiguracionPago.actual()
    planes_cuotas = configuracion_pago.planes_cuotas.filter(activo=True)
    cliente, _ = Cliente.objects.get_or_create(user=request.user)
    direcciones = direcciones_sin_duplicados(cliente.direcciones.all().order_by('etiqueta', 'calle', 'numero'))

    # Opciones de Flex múltiples
    opciones_flex = OpcionEnvioFlex.objects.filter(activo=True)

    # Para compatibilidad con código existente
    zonas_flex = configuracion_envio.zonas_flex_lista
    if opciones_flex:
        # Cada dirección lleva las opciones Flex que la cubren; el checkout filtra según la opción elegida
        direcciones_flex = []
        for direccion in direcciones:
            ids = [str(opcion.id) for opcion in opciones_flex if opcion.incluye_direccion(direccion)]
            if ids:
                direccion.opciones_flex_ids = ','.join(ids)
                direcciones_flex.append(direccion)
    else:
        direcciones_flex = [
            direccion
            for direccion in direcciones
            if direccion_en_zona_flex(direccion, zonas_flex)
        ]
    etiquetas_direcciones = sorted({direccion.etiqueta for direccion in direcciones}, key=str.casefold)
    etiquetas_flex = sorted({direccion.etiqueta for direccion in direcciones_flex}, key=str.casefold)
    
    subtotal = sum(
        item.subtotal for item in items
    )
    codigo_descuento = request.session.get('codigo_descuento', '')
    cupon, descuento_monto = calcular_descuento_cupon(subtotal, codigo_descuento)
    subtotal_con_descuento = subtotal - descuento_monto
    return render(request, 'pedidos/checkout.html', {
        'items': items,
        'subtotal': subtotal,
        'total': subtotal_con_descuento,
        'carrito': carrito,
        'configuracion_envio': configuracion_envio,
        'configuracion_pago': configuracion_pago,
        'planes_cuotas': planes_cuotas,
        'precio_flex': configuracion_envio.costo_flex,
        'precio_correo': None,  # Se cotiza con la API
        'zonas_flex': zonas_flex,
        'direcciones': direcciones,
        'direcciones_flex': direcciones_flex,
        'etiquetas_direcciones': etiquetas_direcciones,
        'etiquetas_flex': etiquetas_flex,
        'opciones_flex': opciones_flex,
        'codigo_descuento': cupon.codigo if cupon else '',
        'descuento_porcentaje': cupon.descuento if cupon else 0,
        'descuento_monto': descuento_monto,
        'cart_expires_in': get_cart_seconds_left(request.session, carrito),
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
        es_regalo = request.POST.get('es_regalo') == '1'
        configuracion_envio = ConfiguracionEnvio.actual()
        opcion_flex_id = request.POST.get('opcion_flex_id')
        opcion_flex = None
        costo_envio = Decimal('0')

        cliente, _ = Cliente.objects.get_or_create(user=request.user)
        subtotal_productos = sum(item.precio_total for item in items_del_carrito)
        codigo_descuento = request.POST.get('codigo_descuento') or request.session.get('codigo_descuento')
        cupon, descuento_monto = calcular_descuento_cupon(subtotal_productos, codigo_descuento)
        total_productos_con_descuento = subtotal_productos - descuento_monto
        direccion = None

        if metodo == 'flex':
            direccion = Direccion.objects.filter(
                id=request.POST.get('direccion_id'),
                cliente=cliente
            ).first()

            # Validar con opción Flex específica si existe
            if opcion_flex_id:
                try:
                    opcion_flex = OpcionEnvioFlex.objects.get(id=opcion_flex_id, activo=True)
                    if not opcion_flex.incluye_direccion(direccion):
                        messages.error(request, f'La dirección seleccionada no está dentro de las zonas de {opcion_flex.nombre}.')
                        return redirect("pedidos:checkout")
                    costo_envio = opcion_flex.costo_actual
                except OpcionEnvioFlex.DoesNotExist:
                    messages.error(request, 'La opción de envío seleccionada no es válida.')
                    return redirect("pedidos:checkout")
            else:
                # Fallback a configuración legacy
                if not direccion_en_zona_flex(direccion, configuracion_envio.zonas_flex_lista):
                    messages.error(request, 'La dirección seleccionada no está dentro de las zonas de Envío Flex.')
                    return redirect("pedidos:checkout")
                costo_envio = costo_envio_checkout(metodo, configuracion_envio)
        elif metodo == 'correo':
            if not configuracion_envio.correo_activo:
                messages.error(request, 'El envio por correo no esta disponible en este momento.')
                return redirect("pedidos:checkout")
            if request.POST.get('tipo_correo') == 'domicilio':
                direccion = Direccion.objects.filter(
                    id=request.POST.get('direccion_correo_id'),
                    cliente=cliente
                ).first()
            if request.POST.get('tipo_correo') == 'domicilio' and not direccion:
                messages.error(request, 'Selecciona una direccion para el envio por correo.')
                return redirect("pedidos:checkout")
            if request.POST.get('tipo_correo') == 'sucursal' and not request.POST.get('sucursal_correo'):
                messages.error(request, 'Indica la sucursal para retirar el envio.')
                return redirect("pedidos:checkout")
            if request.POST.get('correo') == 'correo_argentino':
                codigo_postal_cotizacion = direccion.codigo_postal if direccion else request.POST.get('codigo_postal_sucursal')
                if not codigo_postal_cotizacion:
                    messages.error(request, 'Indica el codigo postal para cotizar Correo Argentino.')
                    return redirect("pedidos:checkout")
                try:
                    costo_envio = costo_correo_argentino_desde_sesion(
                        request,
                        codigo_postal_cotizacion,
                        request.POST.get('tipo_correo') or 'domicilio',
                        items_del_carrito,
                    )
                except ErrorEnvio as error:
                    messages.error(request, str(error))
                    return redirect("pedidos:checkout")

        # VALIDACIÓN DE STOCK
        variantes_sin_stock = errores_stock_items(
            (item.variante, item.color_nombre, item.cantidad) for item in items_del_carrito
        )
        if variantes_sin_stock:
            messages.error(request, "No hay stock suficiente para los siguientes productos:\n" + "\n".join(variantes_sin_stock))
            return redirect("pedidos:checkout")

        # Creamos el pedido oficial
        pedido = Pedido.objects.create(
            cliente=cliente,
            total=total_productos_con_descuento + costo_envio,
            costo_envio=costo_envio,
            opcion_flex=opcion_flex,
            codigo_descuento=cupon.codigo if cupon else None,
            descuento_porcentaje=cupon.descuento if cupon else 0,
            descuento_monto=descuento_monto,
            metodo_entrega=metodo,
            direccion=direccion,
            codigo_postal=direccion.codigo_postal if direccion else request.POST.get('codigo_postal'),
            localidad=direccion.ciudad if direccion else request.POST.get('localidad'),
            calle_numero=f'{direccion.calle} {direccion.numero}' if direccion else request.POST.get('calle_numero'),
            correo=request.POST.get('correo'),
            tipo_correo=request.POST.get('tipo_correo'),
            sucursal_correo=request.POST.get('sucursal_correo'),
            sucursal_correo_id=request.POST.get('sucursal_correo_id'),
            tipo_venta='online',
            estado='pendiente',
            es_regalo=es_regalo,
        )
        crear_envio_pedido(pedido)

        # 3. Movemos los productos al pedido y bajamos el stock
        for item in items_del_carrito:
            PedidoItem.objects.create(
                pedido=pedido,
                variante=item.variante,
                color_nombre=item.color_nombre,
                cantidad=item.cantidad,
                precio_unitario=item.variante.precio,
                precio_total=item.cantidad * item.variante.precio
            )
            # Bajamos el stock del talle y color elegidos
            descontar_stock_variante(item.variante, item.cantidad, item.color_nombre)

        # 4. Limpieza final
        vaciar_carrito_completo(request, carrito)

        messages.success(request, f"¡Pedido #{pedido.id} realizado con éxito!")
        return redirect("pedidos:detalle_pedido", pedido_id=pedido.id)

    return redirect("pedidos:checkout")
    # pedidos/views.py

@login_required
def eliminar_item_carrito(request, variante_id):
    from carritos.models import CarritoItem
    from carritos.utils import _make_cart_item_key, _parse_cart_item_key, SESSION_CART_COLORS_KEY

    carrito = get_or_create_cart(request)
    cart_key = request.POST.get("cart_key") or str(variante_id)
    next_url = request.POST.get("next") or request.META.get('HTTP_REFERER') or reverse('home:home')
    variante_id_int, _color_token = _parse_cart_item_key(cart_key)
    if not variante_id_int:
        variante_id_int = int(variante_id)

    # Buscar item: por su id si viene (identifica la línea exacta aunque el talle esté en
    # varios colores); si no, comparando cart_key generada con la recibida
    item_a_eliminar = None
    item_id = request.POST.get('item_id')
    if item_id:
        item_a_eliminar = carrito.items.filter(id=item_id).first()
    for item_db in ([] if item_a_eliminar else carrito.items.filter(variante_id=variante_id_int)):
        item_key = _make_cart_item_key(item_db.variante.id, item_db.color_nombre, item_db.color_hex)
        if item_key == cart_key:
            item_a_eliminar = item_db
            break

    # Fallback: si no encontró por id ni por cart_key exacto, eliminar el primero de esa variante
    if item_a_eliminar is None and not item_id:
        item_a_eliminar = carrito.items.filter(variante_id=variante_id_int).first()

    if item_a_eliminar:
        item_a_eliminar.delete()
        messages.success(request, "Producto quitado del carrito.")

    # Sincronizar la sesión
    carrito_final = {}
    colores_final = {}
    for item_db in carrito.items.all():
        key = _make_cart_item_key(item_db.variante.id, item_db.color_nombre, item_db.color_hex)
        carrito_final[key] = item_db.cantidad
        colores_final[key] = {
            "nombre": item_db.color_nombre,
            "hex": item_db.color_hex,
        }
    request.session['carrito'] = carrito_final
    request.session[SESSION_CART_COLORS_KEY] = colores_final
    request.session.modified = True

    if not carrito.items.exists():
        messages.info(request, "No quedan productos en tu carrito.")

    return redirect(next_url)
sdk = mercadopago.SDK(settings.MERCADO_PAGO_ACCESS_TOKEN)


def decimal_mp(valor, defecto='0.00'):
    if valor is None or valor == '':
        return Decimal(defecto)
    return monto_decimal(Decimal(str(valor)))


def obtener_id_pago_mercado_pago(request):
    return (
        request.GET.get('payment_id')
        or request.GET.get('collection_id')
        or request.GET.get('id')
    )


def obtener_detalle_pago_mercado_pago(payment_id):
    if not payment_id:
        return {}

    try:
        respuesta = sdk.payment().get(payment_id)
    except Exception:
        return {}

    if respuesta.get('status') != 200:
        return {}

    return respuesta.get('response') or {}


def total_retenciones_mercado_pago(detalle_pago):
    fee_details = detalle_pago.get('fee_details') or []
    cargos = detalle_pago.get('charges_details') or []
    total = Decimal('0.00')

    for fee in fee_details:
        total += decimal_mp(fee.get('amount'))

    if total:
        return total

    for cargo in cargos:
        amounts = cargo.get('amounts') or {}
        total += decimal_mp(amounts.get('original') or amounts.get('paid'))

    return total


def resumen_pago_mercado_pago(request):
    payment_id = obtener_id_pago_mercado_pago(request)
    detalle_pago = obtener_detalle_pago_mercado_pago(payment_id)
    cuotas = int(detalle_pago.get('installments') or 1) if detalle_pago else 1
    tipo_pago = detalle_pago.get('payment_type_id') if detalle_pago else ''
    es_tarjeta_en_cuotas = tipo_pago == 'credit_card' and cuotas > 1
    retencion = (
        total_retenciones_mercado_pago(detalle_pago)
        if es_tarjeta_en_cuotas
        else Decimal('0.00')
    )
    monto = decimal_mp(detalle_pago.get('transaction_amount')) if detalle_pago else Decimal('0.00')
    neto = decimal_mp(detalle_pago.get('net_received_amount')) if detalle_pago else Decimal('0.00')

    if detalle_pago and not neto:
        neto = monto - retencion

    return {
        'payment_id': str(payment_id or ''),
        'cuotas': cuotas,
        'retencion': retencion,
        'neto': neto,
        'detalle': detalle_pago,
    }


@login_required
@require_POST
def validar_codigo_descuento(request):
    carrito = get_or_create_cart(request)
    items = carrito.items.all()
    subtotal = sum(item.subtotal for item in items)

    if subtotal <= 0:
        return JsonResponse({'success': False, 'error': 'El carrito esta vacio.'}, status=400)

    codigo = request.POST.get('codigo_descuento', '')
    cupon, descuento_monto = calcular_descuento_cupon(subtotal, codigo)

    if not cupon:
        request.session.pop('codigo_descuento', None)
        request.session.modified = True
        _, motivo = buscar_cupon(codigo)
        return JsonResponse({'success': False, 'error': motivo or 'Ingresá un código de descuento.'}, status=404)

    request.session['codigo_descuento'] = cupon.codigo
    request.session.modified = True

    return JsonResponse({
        'success': True,
        'codigo': cupon.codigo,
        'nombre': cupon.nombre,
        'porcentaje': cupon.descuento,
        'descuento': float(descuento_monto),
        'subtotal_con_descuento': float(subtotal - descuento_monto),
    })


@login_required
@require_POST
def quitar_codigo_descuento(request):
    """Quita el codigo de descuento almacenado en sesión y devuelve totales actualizados."""
    try:
        carrito = get_or_create_cart(request)
        items = carrito.items.all()
        subtotal = sum(item.subtotal for item in items)

        # Remover datos de descuento de sesión
        request.session.pop('codigo_descuento', None)
        request.session.pop('descuento_monto', None)
        request.session.modified = True

        return JsonResponse({
            'success': True,
            'codigo': '',
            'descuento': 0,
            'subtotal': float(subtotal),
            'subtotal_con_descuento': float(subtotal),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error al quitar descuento: {str(e)}'}, status=400)


@login_required
@require_POST
def cotizar_correo_argentino_checkout(request):
    import re
    cliente, _ = Cliente.objects.get_or_create(user=request.user)
    carrito = get_or_create_cart(request)
    items = carrito.items.all().select_related('variante__producto')
    tipo_entrega = request.POST.get('tipo_correo') or 'domicilio'
    codigo_postal = request.POST.get('codigo_postal', '').strip()

    print(f"DEBUG cotizar: tipo={tipo_entrega}, cp_post={codigo_postal}, dir_id={request.POST.get('direccion_correo_id')}")

    if tipo_entrega == 'domicilio':
        direccion = Direccion.objects.filter(
            id=request.POST.get('direccion_correo_id'),
            cliente=cliente
        ).first()
        if not direccion:
            print(f"DEBUG: No se encontro direccion para cliente {cliente.id}")
            return JsonResponse({'success': False, 'error': 'Selecciona una direccion.'}, status=400)
        codigo_postal = direccion.codigo_postal
        print(f"DEBUG: Direccion encontrada, cp={codigo_postal}")

    if not codigo_postal:
        print("DEBUG: codigo_postal vacio")
        return JsonResponse({'success': False, 'error': 'Indica un codigo postal.'}, status=400)

    # Extraer solo los 4 digitos del codigo postal (ej: "B1900AVW" -> "1900")
    numeros = re.findall(r'\d+', codigo_postal)
    if numeros:
        codigo_postal = numeros[0][:4]
    print(f"DEBUG: codigo_postal final={codigo_postal}")

    paquete = calcular_paquete_envio(items)

    try:
        importe, detalle = cotizar_correo_argentino(codigo_postal, tipo_entrega, items)
    except ErrorEnvio as error:
        return JsonResponse({
            'success': False,
            'error': str(error),
            'debug': {
                'codigo_postal': codigo_postal,
                'tipo_entrega': tipo_entrega,
                'items_count': items.count() if hasattr(items, 'count') else len(items),
                'paquete': paquete,
            }
        }, status=400)

    request.session['correo_cotizacion'] = {
        'importe': str(importe),
        'codigo_postal': codigo_postal,
        'tipo_entrega': tipo_entrega,
        'paquete': paquete,
        'detalle': detalle,
    }
    request.session.modified = True

    return JsonResponse({
        'success': True,
        'importe': float(importe),
        'codigo_postal': codigo_postal,
        'paquete': paquete,
    })


_cache_sucursales = {'data': None, 'timestamp': 0}

@login_required
def buscar_sucursales_correo(request):
    from pedidos.servicios_envio import buscar_sucursales_paqar
    import time

    busqueda = request.GET.get('busqueda', '').strip().lower()
    todas = request.GET.get('todas', '').strip()
    codigo_postal = request.GET.get('codigo_postal', '').strip()
    localidad = request.GET.get('localidad', '').strip()

    try:
        # Usar caché de 10 minutos para no llamar a la API cada vez
        ahora = time.time()
        if _cache_sucursales['data'] is None or (ahora - _cache_sucursales['timestamp']) > 600:
            _cache_sucursales['data'] = buscar_sucursales_paqar()
            _cache_sucursales['timestamp'] = ahora

        todas_sucursales = _cache_sucursales['data']

        # Si hay búsqueda, filtrar por nombre o ciudad
        if busqueda:
            sucursales = [
                s for s in todas_sucursales
                if busqueda in s.get('nombre', '').lower()
                or busqueda in s.get('ciudad', '').lower()
                or busqueda in s.get('provincia', '').lower()
                or busqueda in s.get('codigo_postal', '').lower()
            ]
        elif todas == '1':
            sucursales = todas_sucursales
        elif codigo_postal or localidad:
            sucursales = [
                s for s in todas_sucursales
                if (codigo_postal and codigo_postal in s.get('codigo_postal', ''))
                or (localidad and localidad.lower() in s.get('ciudad', '').lower())
            ]
        else:
            return JsonResponse({'success': False, 'error': 'Indica un termino de busqueda.'}, status=400)

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

    # Si pide todas, devolver todas. Si es búsqueda, limitar a 100
    if todas == '1':
        resultado = sucursales
    else:
        resultado = sucursales[:100]

    return JsonResponse({
        'success': True,
        'sucursales': resultado,
        'count': len(resultado),
    })


@login_required
def crear_pago(request):

    carrito = get_or_create_cart(request)
    refrescar_precios_carrito(carrito)

    # Traer items del carrito
    items = carrito.items.all().select_related(
        'variante__producto',
        'variante__talle'
    )

    # Verificar si el carrito está vacío
    if not items.exists():
        messages.error(request, 'Tu carrito está vacío.')
        return redirect('pedidos:checkout')

    # VALIDAR STOCK (por color cuando el talle tiene stock por color)
    variantes_sin_stock = errores_stock_items(
        (item.variante, item.color_nombre, item.cantidad) for item in items
    )

    # Si hay productos sin stock
    if variantes_sin_stock:

        messages.error(
            request,
            "No hay stock suficiente para:\n" +
            "\n".join(variantes_sin_stock)
        )

        return redirect('pedidos:checkout')

    subtotal_productos = sum(item.subtotal for item in items)
    codigo_descuento = request.POST.get('codigo_descuento') or request.session.get('codigo_descuento')
    cupon, descuento_monto = calcular_descuento_cupon(subtotal_productos, codigo_descuento)
    if codigo_descuento and not cupon:
        _, motivo = buscar_cupon(codigo_descuento)
        request.session.pop('codigo_descuento', None)
        request.session.modified = True
        messages.error(request, f'El código {codigo_descuento.strip().upper()} ya no se puede usar: {motivo} Revisá el total antes de pagar.')
        return redirect('pedidos:checkout')
    factor_descuento = (
        max(Decimal('0'), Decimal('1') - (Decimal(cupon.descuento) / Decimal(100)))
        if cupon
        else Decimal('1')
    )

    request.session['codigo_descuento'] = cupon.codigo if cupon else ''
    request.session['descuento_monto'] = str(descuento_monto)
    request.session.modified = True

    # ARMAR PRODUCTOS PARA MP
    productos = []

    for item in items:
        precio_mp = monto_decimal(Decimal(item.precio_unitario) * factor_descuento)

        productos.append({
            "title": item.variante.producto.nombre,
            "quantity": item.cantidad,
            "currency_id": "ARS",
            "unit_price": float(precio_mp)
        })
    request.session['metodo_entrega'] = request.POST.get(
        'metodo_entrega',
        'local'
    )
    metodo_pago = request.POST.get('metodo_pago', 'mercado_pago')
    request.session['metodo_pago'] = metodo_pago

    configuracion_pago = ConfiguracionPago.actual()

    if metodo_pago not in ['mercado_pago', 'mercado_pago_qr', 'efectivo', 'transferencia']:
        messages.error(request, 'Selecciona un metodo de pago valido.')
        return redirect('pedidos:checkout')

    if metodo_pago == 'efectivo' and request.session['metodo_entrega'] != 'local':
        messages.error(request, 'El pago en efectivo solo esta disponible para retiro en el local.')
        return redirect('pedidos:checkout')

    if metodo_pago == 'mercado_pago' and not configuracion_pago.mercado_pago_activo:
        messages.error(request, 'Mercado Pago no esta disponible en este momento.')
        return redirect('pedidos:checkout')

    if metodo_pago == 'transferencia' and not configuracion_pago.transferencia_activa:
        messages.error(request, 'La transferencia bancaria no esta disponible en este momento.')
        return redirect('pedidos:checkout')

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
    request.session['sucursal_correo_id'] = request.POST.get('sucursal_correo_id')
    request.session['codigo_postal_sucursal'] = request.POST.get('codigo_postal_sucursal')
    request.session['es_regalo'] = request.POST.get('es_regalo') == '1'

    configuracion_envio = ConfiguracionEnvio.actual()
    cliente, _ = Cliente.objects.get_or_create(user=request.user)
    direccion_flex = None
    direccion_correo = None

    opcion_flex = None
    request.session['opcion_flex_id'] = None
    hay_opciones_flex = OpcionEnvioFlex.objects.filter(activo=True).exists()

    if request.session['metodo_entrega'] == 'flex' and hay_opciones_flex:
        opcion_flex = OpcionEnvioFlex.objects.filter(
            id=request.POST.get('opcion_flex_id') or None,
            activo=True
        ).first()
        if not opcion_flex:
            messages.error(request, 'Elegí una opción de Envío Flex.')
            return redirect('pedidos:checkout')
        request.session['opcion_flex_id'] = opcion_flex.id
    elif request.session['metodo_entrega'] == 'flex' and not configuracion_envio.flex_activo:
        messages.error(request, 'El Envio Flex no esta disponible en este momento.')
        return redirect('pedidos:checkout')

    if request.session['metodo_entrega'] == 'correo' and not configuracion_envio.correo_activo:
        messages.error(request, 'El envio por correo no esta disponible en este momento.')
        return redirect('pedidos:checkout')

    if request.session['metodo_entrega'] == 'flex':
        direccion_flex = Direccion.objects.filter(
            id=request.session.get('direccion_id'),
            cliente=cliente
        ).first()
        if not direccion_flex:
            messages.error(request, 'Selecciona una direccion para Envio Flex.')
            return redirect('pedidos:checkout')
        if opcion_flex:
            if not opcion_flex.incluye_direccion(direccion_flex):
                messages.error(request, f'La dirección seleccionada no está dentro de las zonas de {opcion_flex.nombre}.')
                return redirect('pedidos:checkout')
        elif not direccion_en_zona_flex(direccion_flex, configuracion_envio.zonas_flex_lista):
            messages.error(request, 'La dirección seleccionada no está dentro de las zonas de Envío Flex.')
            return redirect('pedidos:checkout')

    if request.session['metodo_entrega'] == 'correo':
        if request.session.get('correo') != 'correo_argentino':
            messages.error(request, 'Selecciona Correo Argentino.')
            return redirect('pedidos:checkout')
        if request.session.get('tipo_correo') not in ['domicilio', 'sucursal']:
            messages.error(request, 'Selecciona el tipo de entrega por correo.')
            return redirect('pedidos:checkout')
        if request.session.get('tipo_correo') == 'domicilio':
            direccion_correo = Direccion.objects.filter(
                id=request.session.get('direccion_correo_id'),
                cliente=cliente
            ).first()
            if not direccion_correo:
                messages.error(request, 'Selecciona una direccion para el envio por correo.')
                return redirect('pedidos:checkout')
        else:
            if not request.session.get('sucursal_correo'):
                messages.error(request, 'Indica la sucursal para retirar el envio.')
                return redirect('pedidos:checkout')
            if request.session.get('correo') == 'correo_argentino' and not request.session.get('codigo_postal_sucursal'):
                messages.error(request, 'Indica el codigo postal para cotizar Correo Argentino.')
                return redirect('pedidos:checkout')

    costo_envio = costo_envio_checkout(request.session['metodo_entrega'], configuracion_envio)
    if opcion_flex:
        costo_envio = opcion_flex.costo_actual
    if request.session['metodo_entrega'] == 'correo' and request.session.get('correo') == 'correo_argentino':
        codigo_postal_cotizacion = (
            direccion_correo.codigo_postal
            if direccion_correo
            else request.session.get('codigo_postal_sucursal')
        )
        try:
            costo_envio = costo_correo_argentino_desde_sesion(
                request,
                codigo_postal_cotizacion,
                request.session.get('tipo_correo') or 'domicilio',
                items,
            )
        except ErrorEnvio as error:
            messages.error(request, str(error))
            return redirect('pedidos:checkout')
        request.session['correo_costo_final'] = str(costo_envio)
        request.session.modified = True

    if costo_envio > 0:
        titulo_envio = 'Envio Flex' if request.session['metodo_entrega'] == 'flex' else 'Envio por correo'
        productos.append({
            "title": titulo_envio,
            "quantity": 1,
            "currency_id": "ARS",
            "unit_price": float(costo_envio)
        })

    if metodo_pago in ['efectivo', 'mercado_pago_qr', 'transferencia']:
        total_pedido = (subtotal_productos - descuento_monto) + costo_envio
        qr_pago = None
        if metodo_pago == 'mercado_pago_qr':
            try:
                qr_pago = crear_qr_link_pago_mercado_pago(
                    productos,
                    f"pedido_qr_{uuid.uuid4().hex[:16]}"
                )
            except ValueError as error:
                messages.error(request, f"No pudimos generar el QR de Mercado Pago. {error}")
                return redirect('pedidos:checkout')

        pedido = Pedido.objects.create(
            cliente=cliente,
            total=total_pedido,
            costo_envio=costo_envio,
            opcion_flex=opcion_flex,
            codigo_descuento=cupon.codigo if cupon else None,
            descuento_porcentaje=cupon.descuento if cupon else 0,
            descuento_monto=descuento_monto,
            metodo_entrega=request.session['metodo_entrega'],
            direccion=direccion_flex or direccion_correo,
            codigo_postal=(direccion_flex or direccion_correo).codigo_postal if (direccion_flex or direccion_correo) else None,
            localidad=(direccion_flex or direccion_correo).ciudad if (direccion_flex or direccion_correo) else None,
            calle_numero=f'{(direccion_flex or direccion_correo).calle} {(direccion_flex or direccion_correo).numero}' if (direccion_flex or direccion_correo) else None,
            correo=request.session.get('correo'),
            tipo_correo=request.session.get('tipo_correo'),
            sucursal_correo=request.session.get('sucursal_correo'),
            sucursal_correo_id=request.session.get('sucursal_correo_id'),
            metodo_pago=metodo_pago,
            monto_pagado=Decimal('0.00'),
            deuda=total_pedido,
            tipo_venta='online',
            estado='pendiente',
            es_regalo=request.session['es_regalo'],
        )
        if cupon:
            cupon.registrar_uso()
        crear_envio_pedido(pedido)

        for item in items:
            PedidoItem.objects.create(
                pedido=pedido,
                variante=item.variante,
                color_nombre=item.color_nombre,
                cantidad=item.cantidad,
                precio_unitario=item.precio_unitario,
                precio_total=item.subtotal
            )

        enviar_email_confirmacion_pedido(pedido)

        if metodo_pago == 'mercado_pago_qr':
            vaciar_carrito_completo(request, carrito)
            return render(request, 'pedidos/pago_qr_pendiente.html', {
                'pedido': pedido,
                'qr_image_url': qr_pago['qr_image'],
                'payment_url': qr_pago['payment_url'],
                'whatsapp_url': whatsapp_comprobante_url(pedido),
                'whatsapp_numero': whatsapp_numero_visible(),
            })

        if metodo_pago == 'transferencia':
            vaciar_carrito_completo(request, carrito)
            return render(request, 'pedidos/pago_transferencia_pendiente.html', {
                'pedido': pedido,
                'configuracion_pago': configuracion_pago,
                'whatsapp_url': whatsapp_transferencia_url(pedido),
                'whatsapp_numero': whatsapp_numero_visible(),
            })

        vaciar_carrito_completo(request, carrito)
        messages.success(request, f'Pedido #{pedido.id} creado para pagar en efectivo al retirar.')
        return redirect('pedidos:mis_pedidos')

    cuotas_activas = list(
        configuracion_pago.planes_cuotas.filter(activo=True).values_list('cuotas', flat=True)
    )
    max_cuotas = max(cuotas_activas) if cuotas_activas else 1

    # CREAR PREFERENCIA
    site_url = settings.SITE_URL.rstrip('/')
    referencia_mp = f"carrito_{carrito.id}_{uuid.uuid4().hex[:16]}"
    request.session['mp_external_reference'] = referencia_mp
    request.session.modified = True
    preference_data = {
        "items": productos,
        "external_reference": referencia_mp,
        "back_urls": {
            "success": f"{site_url}/pedidos/pago-exitoso/",
            "failure": f"{site_url}/",
            "pending": f"{site_url}/"
        },
        "auto_return": "approved",
        "payment_methods": {
            "installments": max_cuotas,
            "excluded_payment_types": [
                {"id": "ticket"},
                {"id": "atm"},
                {"id": "bank_transfer"}
            ]
        }
    }
    preference_response = sdk.preference().create(preference_data)

    print(preference_response)

    # VALIDAR RESPUESTA
    if preference_response.get("status") != 201:

        mp_error = preference_response.get("response", {})
        detalle = mp_error.get("message") or mp_error.get("error") or str(mp_error)
        messages.error(request, f"No pudimos iniciar el pago online. Mercado Pago respondio: {detalle}")

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
    refrescar_precios_carrito(carrito)

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
        item.subtotal for item in items
    )
    cupon, descuento_monto = calcular_descuento_cupon(
        subtotal,
        request.session.get('codigo_descuento')
    )
    total_productos_con_descuento = subtotal - descuento_monto

    metodo_entrega = request.session.get(
        'metodo_entrega',
        'local'
    )

    configuracion_envio = ConfiguracionEnvio.actual()
    costo_envio = costo_envio_checkout(metodo_entrega, configuracion_envio)
    opcion_flex = None
    if metodo_entrega == 'flex' and request.session.get('opcion_flex_id'):
        opcion_flex = OpcionEnvioFlex.objects.filter(id=request.session.get('opcion_flex_id')).first()
        if opcion_flex:
            costo_envio = opcion_flex.costo_actual
    if metodo_entrega == 'correo' and request.session.get('correo') == 'correo_argentino':
        costo_envio = monto_decimal(Decimal(str(request.session.get('correo_costo_final') or '0')))
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

    mercado_pago = resumen_pago_mercado_pago(request)
    detalle_pago = mercado_pago['detalle']
    total_esperado = total_productos_con_descuento + costo_envio
    referencia_esperada = request.session.get('mp_external_reference')
    error_pago = None

    if not mercado_pago['payment_id'] or not detalle_pago:
        error_pago = 'No pudimos verificar tu pago con Mercado Pago.'
    elif detalle_pago.get('status') != 'approved':
        error_pago = 'Mercado Pago todavía no aprobó tu pago.'
    elif referencia_esperada and detalle_pago.get('external_reference') != referencia_esperada:
        error_pago = 'El pago informado no corresponde a esta compra.'
    elif decimal_mp(detalle_pago.get('transaction_amount')) + Decimal('1.00') < total_esperado:
        error_pago = 'El monto pagado no coincide con el total de tu compra.'
    elif Pago.objects.filter(mercado_pago_payment_id=mercado_pago['payment_id']).exists():
        error_pago = 'Este pago ya fue registrado.'

    if error_pago:
        messages.error(
            request,
            f'{error_pago} Tu pedido no fue confirmado. Si el dinero se debitó, '
            'escribinos por WhatsApp con el comprobante.'
        )
        return redirect('pedidos:checkout')

    request.session.pop('mp_external_reference', None)

    pedido = Pedido.objects.create(
        cliente=cliente,
        total=total_productos_con_descuento + costo_envio,
        costo_envio=costo_envio,
        opcion_flex=opcion_flex,
        codigo_descuento=cupon.codigo if cupon else None,
        descuento_porcentaje=cupon.descuento if cupon else 0,
        descuento_monto=descuento_monto,
        metodo_entrega=metodo_entrega,
        metodo_pago='mercado_pago',
        monto_pagado=total_productos_con_descuento + costo_envio,
        direccion=direccion,
        codigo_postal=direccion.codigo_postal if direccion else request.session.get('codigo_postal'),
        localidad=direccion.ciudad if direccion else request.session.get('localidad'),
        calle_numero=f'{direccion.calle} {direccion.numero}' if direccion else request.session.get('calle_numero'),
        correo=request.session.get('correo'),
        tipo_correo=request.session.get('tipo_correo'),
        sucursal_correo=request.session.get('sucursal_correo'),
        sucursal_correo_id=request.session.get('sucursal_correo_id'),
        tipo_venta='online',
        estado='aceptado',
        es_regalo=bool(request.session.get('es_regalo')),
    )

    if cupon:
        cupon.registrar_uso()

    Pago.objects.create(
        pedido=pedido,
        metodo='Mercado Pago',
        monto=pedido.total,
        mercado_pago_payment_id=mercado_pago['payment_id'],
        cuotas=mercado_pago['cuotas'],
        retencion_mercado_pago=mercado_pago['retencion'],
        neto_recibido=mercado_pago['neto'] or (pedido.total - mercado_pago['retencion']),
        detalle_mercado_pago=mercado_pago['detalle'],
    )
    crear_envio_pedido(pedido)

    # CREAR ITEMS Y DESCONTAR STOCK
    for item in items:

        PedidoItem.objects.create(
            pedido=pedido,
            variante=item.variante,
            color_nombre=item.color_nombre,
            cantidad=item.cantidad,
            precio_unitario=item.precio_unitario,
            precio_total=item.subtotal
        )

        try:
            descontar_stock_variante(item.variante, item.cantidad, item.color_nombre)
        except ValueError:
            # El pago ya fue aprobado: se registra el pedido igual y se descuenta lo que haya
            disponible = stock_disponible(item.variante, item.color_nombre)
            if disponible > 0:
                try:
                    descontar_stock_variante(item.variante, disponible, item.color_nombre)
                except ValueError:
                    pass

    items_pedido = pedido.items.select_related(
        'variante__producto',
        'variante__talle'
    ).prefetch_related(
        'variante__colores'
    )

    productos_texto = []
    productos_html = []

    for item in items_pedido:
        colores = item.color_nombre or ', '.join(
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
        if pedido.direccion and pedido.direccion.referencia:
            direccion_envio += f' - Ref: {pedido.direccion.referencia}'

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
    vaciar_carrito_completo(request, carrito)

    messages.success(
        request,
        f"¡Tu pago fue realizado con éxito! Pedido #{pedido.id} confirmado."
    )

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

    elif tipo_periodo == 'hoy':

        fecha_inicio = hoy
        fecha_fin = hoy

    elif tipo_periodo == '7dias':

        fecha_inicio = hoy - timedelta(days=7)
        fecha_fin = hoy

    elif tipo_periodo == 'semana':
        # Semana actual (lunes a hoy)
        fecha_inicio = hoy - timedelta(days=hoy.weekday())
        fecha_fin = hoy

    elif tipo_periodo == 'mes':
        # Mes actual
        fecha_inicio = hoy.replace(day=1)
        fecha_fin = hoy

    elif tipo_periodo == 'ano':
        # Año actual
        fecha_inicio = hoy.replace(month=1, day=1)
        fecha_fin = hoy

    elif tipo_periodo == '90dias':

        fecha_inicio = hoy - timedelta(days=90)
        fecha_fin = hoy

    else:

        fecha_inicio = hoy - timedelta(days=30)
        fecha_fin = hoy

    # Pedidos del período (todos, para el cuadro "Pedidos por estado")
    pedidos_periodo = Pedido.objects.filter(
        created_at__date__gte=fecha_inicio,
        created_at__date__lte=fecha_fin
    )

    # Solo cuentan como venta los pedidos confirmados (pago aceptado en adelante).
    # Pendientes, rechazados, cancelados y vencidos no son ventas.
    pedidos = pedidos_periodo.filter(estado__in=Pedido.ESTADOS_CON_STOCK_DESCONTADO)
    pedidos_pendientes = pedidos_periodo.filter(estado='pendiente')
    pendientes_cantidad = pedidos_pendientes.count()
    pendientes_total = pedidos_pendientes.aggregate(total=Sum('total'))['total'] or Decimal('0.00')

    # Notas de crédito emitidas sobre las ventas del período: restan de lo vendido
    total_notas_credito = (
        NotaCredito.objects.filter(pedido__in=pedidos).exclude(estado='anulada').aggregate(total=Sum('monto'))['total']
        or Decimal('0.00')
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
        pedidos_periodo.values('estado')
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
            created_at__date=fecha,
            estado__in=Pedido.ESTADOS_CON_STOCK_DESCONTADO,
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

    # Gastos en el período
    total_gastos = (
        Gasto.objects.filter(
            fecha__gte=fecha_inicio,
            fecha__lte=fecha_fin
        ).aggregate(total=Sum('monto'))['total']
        or Decimal('0.00')
    )

    # Deudas en pedidos del período
    total_deudas = (
        pedidos.aggregate(total=Sum('deuda'))['total']
        or Decimal('0.00')
    )

    # Retenciones de MercadoPago en pedidos online
    retenciones_mp = (
        Pago.objects.filter(
            pedido__in=pedidos
        ).aggregate(total=Sum('retencion_mercado_pago'))['total']
        or Decimal('0.00')
    )

    # Neto recibido (lo que realmente entró en la billetera por MP)
    total_neto_recibido = (
        Pago.objects.filter(
            pedido__in=pedidos
        ).aggregate(total=Sum('neto_recibido'))['total']
        or Decimal('0.00')
    )

    # Ventas locales en el período
    ventas_locales = VentaLocal.objects.filter(
        created_at__date__gte=fecha_inicio,
        created_at__date__lte=fecha_fin
    )
    total_ventas_locales = (
        ventas_locales.aggregate(total=Sum('total'))['total']
        or Decimal('0.00')
    )
    cobrado_ventas_locales = (
        ventas_locales.aggregate(total=Sum('monto_pagado'))['total']
        or Decimal('0.00')
    )

    # Retenciones de ventas presenciales (tarjeta/MP)
    retenciones_presenciales = (
        ventas_locales.aggregate(total=Sum('retencion'))['total']
        or Decimal('0.00')
    )

    # Total retenciones = MP online + tarjeta presencial
    total_retenciones = retenciones_mp + retenciones_presenciales

    # Total con deudas (ventas confirmadas incluyendo lo que falta cobrar), menos notas de crédito
    total_con_deudas = total_ventas + total_ventas_locales - total_notas_credito

    # Lo realmente cobrado = monto_pagado de pedidos + monto_pagado de ventas locales
    cobrado_pedidos = (
        pedidos.aggregate(total=Sum('monto_pagado'))['total']
        or Decimal('0.00')
    )
    ingresos_brutos = cobrado_pedidos + cobrado_ventas_locales

    # Neto negocio = subtotal ventas - gastos - retenciones
    neto_negocio = total_con_deudas - total_gastos - total_retenciones

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
        # Nuevos campos
        'total_gastos': total_gastos,
        'total_deudas': total_deudas,
        'total_retenciones': total_retenciones,
        'total_neto_recibido': total_neto_recibido,
        'total_con_deudas': total_con_deudas,
        'ingresos_brutos': ingresos_brutos,
        'neto_negocio': neto_negocio,
        'total_notas_credito': total_notas_credito,
        'pendientes_cantidad': pendientes_cantidad,
        'pendientes_total': pendientes_total,
    }

    return render(
        request,
        'pedidos/estadisticas_ventas.html',
        context
    )
@login_required
def estado_pedido(request, pedido_id):

    pedido = get_object_or_404(
        Pedido.objects.select_related('envio'),
        id=pedido_id,
        cliente__user=request.user
    )
    envio = getattr(pedido, 'envio', None)

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

    # Pedidos cerrados sin entregar (rechazado, cancelado, vencido) o en un estado que no
    # corresponde al método de entrega: no se dibuja la línea de tiempo, se informa el estado
    mensajes_estado = {
        'rechazado': 'El pago de este pedido fue rechazado. Si ya pagaste, escribinos con el comprobante.',
        'cancelado': 'Este pedido fue cancelado. Si tenés dudas, escribinos.',
        'vencido': 'Este pedido venció porque no recibimos el pago a tiempo.',
    }
    if pedido.estado not in flujo:
        return render(
            request,
            'pedidos/estado_pedido.html',
            {
                'pedido': pedido,
                'pasos': [],
                'estado_cerrado': mensajes_estado.get(
                    pedido.estado,
                    f'Estado actual: {pedido.get_estado_display()}.'
                ),
                'envio': envio,
                'seguimiento_url': url_seguimiento_envio(envio),
            }
        )

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
            'pasos': pasos,
            'envio': envio,
            'seguimiento_url': url_seguimiento_envio(envio),
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


def item_carrito_de_request(request, carrito, variante_id):
    """Ítem del carrito a modificar: por su id (item_id) si viene, porque el mismo talle puede
    estar en varias líneas de distintos colores; si no, el primero de esa variante."""
    item_id = request.POST.get('item_id')
    if item_id:
        return get_object_or_404(CarritoItem, carrito=carrito, id=item_id)
    item = CarritoItem.objects.filter(carrito=carrito, variante_id=variante_id).order_by('id').first()
    if not item:
        raise Http404('El producto ya no está en el carrito.')
    return item


@login_required
@require_POST
def aumentar_cantidad(request, variante_id):

    carrito = get_or_create_cart(request)

    item = item_carrito_de_request(request, carrito, variante_id)

    if item.cantidad < stock_disponible(item.variante, item.color_nombre):

        item.cantidad += 1
        item.save()

    else:

        messages.error(
            request,
            'No hay más stock disponible de este talle y color.'
        )

    return redirect('pedidos:checkout')
@login_required
@require_POST
def disminuir_cantidad(request, variante_id):

    carrito = get_or_create_cart(request)

    item = item_carrito_de_request(request, carrito, variante_id)

    item.cantidad -= 1

    if item.cantidad <= 0:
        item.delete()

    else:
        item.save()

    return redirect('pedidos:checkout')


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
        try:
            with transaction.atomic():
                cambiar_estado_pedido(pedido, nuevo_estado)
                pedido.save()
        except ValueError as error:
            messages.error(request, str(error))
            return redirect('pedidos:gestion_pedidos')

        if estado_anterior != nuevo_estado and pedido.cliente.user.email:
            estados_dict = dict(Pedido.ESTADOS)
            productos = []
            productos_html = []

            for item in pedido.items.all():
                colores = item.color_nombre or ', '.join(
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
@require_POST
def actualizar_tracking_envio(request, pedido_id):
    pedido = get_object_or_404(Pedido.objects.select_related('envio'), id=pedido_id)
    envio = getattr(pedido, 'envio', None) or crear_envio_pedido(pedido)

    if not envio:
        messages.error(request, 'Este pedido no tiene envio asociado.')
        return redirect('pedidos:detalle_pedido', pedido_id=pedido.id)

    tracking = (request.POST.get('tracking') or '').strip()
    envio.tracking = tracking or None
    envio.error = ''
    envio.save(update_fields=['tracking', 'error', 'updated_at'])

    if tracking:
        messages.success(request, 'Codigo de seguimiento guardado.')
    else:
        messages.success(request, 'Codigo de seguimiento eliminado.')

    return redirect('pedidos:detalle_pedido', pedido_id=pedido.id)


@admin_required
def ventas_presenciales(request):

    ventas = VentaLocal.objects.select_related(
        'cliente',
        'cliente__user',
        'direccion'
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

    try:
        data = json.loads(request.body)

        cliente_id = data.get('cliente_id')

        productos = data.get('productos')
        
        metodo_pago = data.get('metodo_pago', 'efectivo')
        metodo_entrega = data.get('metodo_entrega', 'local')
        direccion_id = data.get('direccion_id')
        es_regalo = bool(data.get('es_regalo'))
        
        nueva_deuda = leer_monto(data.get('nueva_deuda') or 0)

        if nueva_deuda is None:
            return JsonResponse({
                'success': False,
                'error': 'El monto de la deuda no es válido'
            }, status=400)

        if not cliente_id or not productos:

            return JsonResponse({

                'success': False,
                'error': 'Faltan cliente o productos'

            })
        
        if metodo_pago not in ['efectivo', 'mercado_pago', 'tarjeta']:
            return JsonResponse({
                'success': False,
                'error': 'Método de pago inválido'
            })

        if metodo_entrega not in ['local', 'envio']:
            return JsonResponse({
                'success': False,
                'error': 'Método de entrega inválido'
            }, status=400)

        cliente = Cliente.objects.get(
            user_id=cliente_id
        )

        direccion = None
        if metodo_entrega == 'envio':
            direccion = Direccion.objects.filter(
                id=direccion_id,
                cliente=cliente
            ).first()
            if not direccion:
                return JsonResponse({
                    'success': False,
                    'error': 'Seleccioná una dirección de envío'
                }, status=400)

        # Validar todos los ítems y la deuda ANTES de guardar nada, para no dejar
        # ventas a medias ni descontar stock si algo falla.
        total = Decimal('0.00')
        lineas = []
        pedidas_por_variante = {}

        for item in productos:

            variante = Variante.objects.select_for_update().select_related('producto').get(
                id=item.get('variante_id')
            )

            try:
                cantidad = int(item.get('cantidad'))
            except (TypeError, ValueError):
                cantidad = 0

            if cantidad < 1:
                return JsonResponse({
                    'success': False,
                    'error': 'La cantidad debe ser mayor a cero'
                }, status=400)

            color = (item.get('color') or '').strip()
            clave_stock = (variante.id, color.lower())
            pedidas_por_variante[clave_stock] = pedidas_por_variante.get(clave_stock, 0) + cantidad

            try:
                validar_stock(variante, pedidas_por_variante[clave_stock], color)
            except ValueError as error:
                return JsonResponse({
                    'success': False,
                    'error': str(error)
                }, status=400)

            # El precio publicado es el del producto (el del talle solo si el producto no tiene)
            precio_base = variante.producto.precio or variante.precio

            # Aplicar descuento si hay oferta activa
            oferta = variante.producto.obtener_oferta_activa()
            if oferta:
                descuento = Decimal(oferta.descuento) / Decimal(100)
                precio_unitario = precio_base * (1 - descuento)
            else:
                precio_unitario = precio_base

            subtotal = precio_unitario * cantidad
            total += subtotal
            lineas.append((variante, color, cantidad, precio_unitario, subtotal))

        if nueva_deuda < 0:
            return JsonResponse({
                'success': False,
                'error': 'La deuda no puede ser negativa'
            }, status=400)
        if nueva_deuda > total:
            return JsonResponse({
                'success': False,
                'error': 'La deuda no puede ser mayor al total de la venta'
            }, status=400)

        venta = VentaLocal.objects.create(

            cliente=cliente,

            total=total,

            monto_pagado=0,

            saldo_pendiente=0,

            estado_pago='PAGADO',
            
            metodo_pago=metodo_pago,
            metodo_entrega=metodo_entrega,
            direccion=direccion,
            es_regalo=es_regalo
        )

        for variante, color, cantidad, precio_unitario, subtotal in lineas:

            VentaLocalItem.objects.create(

                venta=venta,

                producto=variante.producto,

                variante=variante,

                color=color,

                cantidad=cantidad,

                precio_unitario=precio_unitario,

                subtotal=subtotal

            )

            descontar_stock_variante(variante, cantidad, color)

        monto_pagado = total - nueva_deuda
        saldo_pendiente = nueva_deuda

        if saldo_pendiente > 0:
            estado_pago = 'PARCIAL'
        else:
            estado_pago = 'PAGADO'

        venta.total = total
        venta.monto_pagado = monto_pagado
        venta.saldo_pendiente = saldo_pendiente
        venta.estado_pago = estado_pago

        # Calcular retención si pago con tarjeta/MP
        if metodo_pago in ['tarjeta', 'mercado_pago', 'mercado_pago_qr'] and monto_pagado > 0:
            config = ConfiguracionPago.actual()
            porcentaje = config.retencion_tarjeta_porcentaje or Decimal('0')
            venta.retencion = (monto_pagado * porcentaje) / Decimal('100')

        venta.save()
        if saldo_pendiente > 0:
            cliente.deuda_total += saldo_pendiente
            cliente.save(update_fields=['deuda_total'])
        if monto_pagado > 0:

            PagoVentaLocal.objects.create(

                venta=venta,

                monto=monto_pagado
            )

        return JsonResponse({

            'success': True,
            'venta_id': venta.id,
            'mensaje': f'Venta registrada. Deuda: ${saldo_pendiente}' if saldo_pendiente > 0 else 'Venta completada'

        })
    
    except Cliente.DoesNotExist:
        transaction.set_rollback(True)
        return JsonResponse({
            'success': False,
            'error': 'Cliente no encontrado'
        }, status=404)
    except Variante.DoesNotExist:
        transaction.set_rollback(True)
        return JsonResponse({
            'success': False,
            'error': 'Producto no encontrado'
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Formato de datos inválido'
        }, status=400)
    except Exception as e:
        transaction.set_rollback(True)
        return JsonResponse({
            'success': False,
            'error': f'Error al registrar venta: {str(e)}'
        }, status=400)


@admin_required
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

        'fecha': timezone.localtime(venta.created_at).strftime(
            '%d/%m/%Y %H:%M'
        ),

        'total': float(venta.total),
        'pagado': float(venta.monto_pagado),

        'pendiente': float(venta.saldo_pendiente),

        'estado': venta.estado_pago,
        
        'metodo_pago': venta.get_metodo_pago_display() if hasattr(venta, 'get_metodo_pago_display') else venta.metodo_pago,

        'metodo_entrega': venta.get_metodo_entrega_display() if hasattr(venta, 'get_metodo_entrega_display') else venta.metodo_entrega,

        'es_regalo': venta.es_regalo,

        'ticket_cambio_url': f'/pedidos/venta-local/{venta.id}/ticket-cambio/',

        'ticket_envio_url': f'/pedidos/venta-local/{venta.id}/ticket-envio/',

        'tiene_envio': True,

        'direccion': (
            f'{venta.direccion.etiqueta}: {venta.direccion.calle} {venta.direccion.numero}, '
            f'{venta.direccion.ciudad}, {venta.direccion.provincia} - CP {venta.direccion.codigo_postal}'
            if venta.direccion else ''
        ),
        
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


def contexto_ticket_venta(venta):
    items = venta.items.select_related(
        'producto',
        'variante',
        'variante__talle'
    ).prefetch_related('variante__colores')
    fecha = timezone.localtime(venta.created_at)
    items_ticket = []
    for item in items:
        color_mostrar = item.color
        if color_mostrar and color_mostrar.startswith('#'):
            color_obj = item.variante.colores.filter(codigo_hex__iexact=color_mostrar).first()
            if color_obj:
                color_mostrar = color_obj.nombre
            else:
                color_mostrar = None
        if not color_mostrar:
            color_mostrar = ', '.join(
                color.nombre for color in item.variante.colores.all()
            ) or '-'
        items_ticket.append({
            'producto': item.producto.nombre,
            'color': color_mostrar,
            'talle': item.variante.talle.nombre,
            'precio': formato_pesos(item.precio_unitario),
            'cantidad': item.cantidad,
            'subtotal': formato_pesos(item.subtotal),
        })
    configuracion_envio = ConfiguracionEnvio.actual()
    costo_envio = (
        Decimal(configuracion_envio.costo_flex)
        if venta.metodo_entrega == 'envio'
        else Decimal('0')
    )

    return {
        'venta': venta,
        'items': items_ticket,
        'fecha_ticket': fecha.strftime('%d/%m/%Y - %H:%M'),
        'orden': str(venta.id).zfill(5),
        'cliente_nombre': f'{venta.cliente.user.first_name} {venta.cliente.user.last_name}'.strip(),
        'telefono': venta.cliente.telefono,
        'subtotal': formato_pesos(venta.total),
        'descuento': formato_pesos(0),
        'total': formato_pesos(venta.total),
        'costo_envio': formato_pesos(costo_envio),
        'metodo_pago': venta.get_metodo_pago_display(),
        'es_regalo': venta.es_regalo,
        'direccion': venta.direccion,
    }


def contexto_ticket_pedido(pedido):
    items = pedido.items.select_related(
        'variante',
        'variante__producto',
        'variante__talle',
    ).prefetch_related('variante__colores')
    fecha = timezone.localtime(pedido.created_at)
    items_ticket = []

    for item in items:
        color_mostrar = item.color_nombre
        if color_mostrar and color_mostrar.startswith('#'):
            color_obj = item.variante.colores.filter(codigo_hex__iexact=color_mostrar).first()
            if color_obj:
                color_mostrar = color_obj.nombre
            else:
                color_mostrar = None
        if not color_mostrar:
            color_mostrar = ', '.join(
                color.nombre for color in item.variante.colores.all()
            ) or '-'
        items_ticket.append({
            'producto': item.variante.producto.nombre,
            'color': color_mostrar,
            'talle': item.variante.talle.nombre if item.variante.talle else 'Sin talle',
            'precio': formato_pesos(item.precio_unitario),
            'cantidad': item.cantidad,
            'subtotal': formato_pesos(item.precio_total),
        })

    pago = getattr(pedido, 'pago', None)

    return {
        'pedido': pedido,
        'items': items_ticket,
        'fecha_ticket': fecha.strftime('%d/%m/%Y - %H:%M'),
        'orden': str(pedido.id).zfill(5),
        'cliente_nombre': f'{pedido.cliente.user.first_name} {pedido.cliente.user.last_name}'.strip() or pedido.cliente.user.username,
        'telefono': pedido.cliente.telefono,
        'subtotal': formato_pesos(pedido.total - pedido.costo_envio + pedido.descuento_monto),
        'descuento': formato_pesos(pedido.descuento_monto),
        'total': formato_pesos(pedido.total),
        'costo_envio': formato_pesos(pedido.costo_envio),
        'metodo_pago': pago.metodo if pago else (pedido.get_metodo_pago_display() if pedido.metodo_pago else 'Mercado Pago'),
        'es_regalo': pedido.es_regalo,
        # Si el admin editó la dirección del pedido, esa es la que se imprime
        'direccion': None if pedido.direccion_info else pedido.direccion,
        'pedido_direccion_texto': pedido.direccion_info or pedido.calle_numero or '',
    }


@admin_required
def ticket_cambio_venta_local(request, venta_id):
    venta = get_object_or_404(
        VentaLocal.objects.select_related(
            'cliente',
            'cliente__user',
            'direccion'
        ).prefetch_related('items'),
        id=venta_id
    )

    return render(
        request,
        'pedidos/ticket_cambio_venta.html',
        contexto_ticket_venta(venta)
    )


@admin_required
def ticket_envio_venta_local(request, venta_id):
    venta = get_object_or_404(
        VentaLocal.objects.select_related(
            'cliente',
            'cliente__user',
            'direccion'
        ).prefetch_related('items'),
        id=venta_id
    )

    return render(
        request,
        'pedidos/ticket_envio_venta.html',
        contexto_ticket_venta(venta)
    )


@admin_required
def ticket_cambio_pedido(request, pedido_id):
    pedido = get_object_or_404(
        Pedido.objects.select_related(
            'cliente',
            'cliente__user',
            'direccion',
        ).prefetch_related('items'),
        id=pedido_id
    )

    return render(
        request,
        'pedidos/ticket_cambio_venta.html',
        contexto_ticket_pedido(pedido)
    )


@admin_required
def ticket_envio_pedido(request, pedido_id):
    pedido = get_object_or_404(
        Pedido.objects.select_related(
            'cliente',
            'cliente__user',
            'direccion',
        ).prefetch_related('items'),
        id=pedido_id
    )

    return render(
        request,
        'pedidos/ticket_envio_venta.html',
        contexto_ticket_pedido(pedido)
    )


@require_POST
@admin_required
def registrar_pago_venta(request, venta_id):

    venta = get_object_or_404(
        VentaLocal,
        id=venta_id
    )

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        data = {}

    monto = leer_monto(data.get('monto'))
    saldo_actual = venta.total - venta.monto_pagado

    if monto is None or monto <= 0:
        return JsonResponse({'success': False, 'error': 'Ingresá un monto mayor a 0.'}, status=400)

    if saldo_actual <= 0:
        return JsonResponse({'success': False, 'error': 'Esta venta no tiene saldo pendiente.'}, status=400)

    if monto > saldo_actual:
        return JsonResponse({
            'success': False,
            'error': f'El monto no puede superar el saldo pendiente (${saldo_actual}).'
        }, status=400)

    venta.monto_pagado += monto

    venta.saldo_pendiente = (
        venta.total - venta.monto_pagado
    )

    if venta.cliente_id:
        cliente = venta.cliente
        cliente.deuda_total = max(Decimal('0.00'), cliente.deuda_total - monto)
        cliente.save(update_fields=['deuda_total'])

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


@require_POST
@admin_required
def registrar_pago_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id)
    data = json.loads(request.body)

    monto = Decimal(str(data.get('monto', 0)))
    metodo_pago = data.get('metodo_pago', 'efectivo')
    observaciones = data.get('observaciones', '')

    if pedido.estado in ('cancelado', 'rechazado', 'vencido'):
        return JsonResponse({
            'success': False,
            'error': f'No se pueden registrar pagos en un pedido {pedido.get_estado_display().lower()}.'
        })

    if monto <= 0:
        return JsonResponse({'success': False, 'error': 'El monto debe ser mayor a 0'})

    saldo_pendiente = pedido.total - pedido.monto_pagado
    if monto > saldo_pendiente:
        monto = saldo_pendiente

    with transaction.atomic():
        pedido.monto_pagado += monto
        pedido.deuda = pedido.total - pedido.monto_pagado

        if pedido.deuda <= 0:
            pedido.deuda = 0
            pedido.metodo_pago = metodo_pago

            # Un pedido pendiente que queda saldado pasa a "Pago aceptado" y descuenta stock,
            # igual que al aceptarlo desde la gestión de pedidos. Nunca se marca "Entregado" por un pago.
            if pedido.estado == 'pendiente':
                try:
                    descontar_stock_pedido(pedido)
                except ValueError as error:
                    transaction.set_rollback(True)
                    return JsonResponse({'success': False, 'error': str(error)})
                pedido.estado = 'aceptado'

        pedido.save()

        PagoPedido.objects.create(
            pedido=pedido,
            monto=monto,
            metodo_pago=metodo_pago,
            observaciones=observaciones
        )

    pagos = pedido.pagos_registrados.all()
    pagos_html = ""
    for p in pagos:
        pagos_html += f"""
        <div class="pago-item">
            <div class="pago-fecha">{p.fecha.strftime('%d/%m/%Y %H:%M')}</div>
            <div class="pago-metodo">{p.get_metodo_pago_display()}</div>
            <div class="pago-monto">${p.monto}</div>
        </div>
        """

    return JsonResponse({
        'success': True,
        'monto_pagado': float(pedido.monto_pagado),
        'deuda': float(pedido.deuda),
        'pagado_completo': pedido.deuda == 0,
        'pagos_html': pagos_html
    })


@admin_required
def configurar_envios(request):
    from .forms import OpcionEnvioFlexFormSet
    from .models import OpcionEnvioFlex

    configuracion = ConfiguracionEnvio.actual()

    if request.method == 'POST':
        form = ConfiguracionEnvioForm(request.POST, instance=configuracion)
        formset = OpcionEnvioFlexFormSet(request.POST, prefix='flex')

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, 'Configuración de envíos actualizada correctamente.')
            return redirect('pedidos:configurar_envios')
        else:
            # Mostrar errores del formulario principal
            if form.errors:
                for field, errors in form.errors.items():
                    messages.error(request, f'Error en {field}: {", ".join(errors)}')
            # Mostrar errores del formset
            for i, error in enumerate(formset.errors):
                if error:
                    messages.error(request, f'Error en opción Flex #{i+1}: {error}')
            if formset.non_form_errors():
                messages.error(request, f'Error: {formset.non_form_errors()}')
    else:
        form = ConfiguracionEnvioForm(instance=configuracion)
        formset = OpcionEnvioFlexFormSet(queryset=OpcionEnvioFlex.objects.all(), prefix='flex')

    return render(request, 'pedidos/configurar_envios.html', {
        'form': form,
        'formset': formset,
        'configuracion': configuracion,
        'opciones_flex': OpcionEnvioFlex.objects.filter(activo=True),
    })


@admin_required
def configurar_pagos(request):
    configuracion = ConfiguracionPago.actual()

    if request.method == 'POST':
        form = ConfiguracionPagoForm(request.POST, instance=configuracion)
        if form.is_valid():
            configuracion = form.save()

            # Guardar porcentaje de retención de tarjeta
            retencion_tarjeta = request.POST.get('retencion_tarjeta_porcentaje', '0')
            try:
                configuracion.retencion_tarjeta_porcentaje = Decimal(str(retencion_tarjeta).replace(',', '.'))
            except Exception:
                configuracion.retencion_tarjeta_porcentaje = Decimal('0')
            configuracion.save()

            configuracion.planes_cuotas.all().delete()

            cuotas = request.POST.getlist('cuotas[]')
            retenciones = request.POST.getlist('retencion_porcentaje[]')
            sin_interes_values = request.POST.getlist('sin_interes[]')
            activos = request.POST.getlist('activo[]')

            for index, cuotas_value in enumerate(cuotas):
                try:
                    cuotas_int = int(cuotas_value)
                except ValueError:
                    continue

                if cuotas_int <= 0:
                    continue

                retencion_value = retenciones[index] if index < len(retenciones) else '0'
                try:
                    retencion_porcentaje = Decimal(str(retencion_value).replace(',', '.'))
                except Exception:
                    retencion_porcentaje = Decimal('0')

                if retencion_porcentaje < 0:
                    retencion_porcentaje = Decimal('0')

                PlanCuotasMercadoPago.objects.create(
                    configuracion=configuracion,
                    cuotas=cuotas_int,
                    retencion_porcentaje=retencion_porcentaje,
                    sin_interes=str(index) in sin_interes_values,
                    activo=str(index) in activos,
                    orden=index,
                )

            messages.success(request, 'Configuracion de pagos actualizada.')
            return redirect('pedidos:configurar_pagos')
    else:
        form = ConfiguracionPagoForm(instance=configuracion)

    return render(request, 'pedidos/configurar_pagos.html', {
        'form': form,
        'configuracion': configuracion,
        'planes_cuotas': configuracion.planes_cuotas.all(),
    })


@admin_required
def registrar_cambio(request, pedido_id):
    """Registra un cambio de producto en un pedido y actualiza el stock."""
    from productos.models import Variante

    pedido = get_object_or_404(Pedido, pk=pedido_id)

    if request.method == 'POST':
        if pedido.estado not in Pedido.ESTADOS_CON_STOCK_DESCONTADO:
            messages.error(request, 'Solo se pueden registrar cambios en pedidos confirmados (pago aceptado en adelante).')
            return redirect('pedidos:detalle_pedido', pedido_id=pedido.id)

        # Devuelto: id del ítem del pedido. Entregado: "<variante_id>|<color>" (color vacío si el talle no usa stock por color)
        item_devuelto = pedido.items.select_related('variante__producto', 'variante__talle').filter(
            id=request.POST.get('item_devuelto') or None
        ).first()
        variante_entregada_id, _, color_entregado = (request.POST.get('variante_entregada') or '').partition('|')
        motivo = request.POST.get('motivo', '')

        if item_devuelto and variante_entregada_id:
            variante_devuelta = item_devuelto.variante
            variante_entregada = get_object_or_404(Variante.objects.select_related('producto', 'talle'), pk=variante_entregada_id)

            if unidades_cambiables(item_devuelto) <= 0:
                messages.error(
                    request,
                    f'Ya se cambiaron o devolvieron todas las unidades compradas de {variante_devuelta.producto.nombre} '
                    f'(talle {variante_devuelta.talle.nombre}).'
                )
                return redirect('pedidos:detalle_pedido', pedido_id=pedido.id)

            # Diferencia de precio: lo que vale hoy lo entregado contra lo que se pagó por lo devuelto
            diferencia = precio_unitario_vigente(variante_entregada) - item_devuelto.precio_unitario
            detalle_diferencia = ''

            try:
                with transaction.atomic():
                    # Restar stock al producto entregado (valida talle y color)
                    descontar_stock(variante_entregada, 1, color_entregado or None)

                    # Sumar stock al producto devuelto, en el color que se había vendido
                    reponer_stock(variante_devuelta, 1, item_devuelto.color_nombre)

                    if diferencia > 0:
                        # El cliente tiene que abonar la diferencia: se suma al total y al saldo del pedido
                        pedido.total += diferencia
                        pedido.deuda = max(pedido.total - pedido.monto_pagado, Decimal('0.00'))
                        pedido.save(update_fields=['total', 'deuda'])
                        detalle_diferencia = f' El cliente debe abonar ${diferencia} de diferencia (quedó en el saldo del pedido).'
                    elif diferencia < 0:
                        # A favor del cliente: queda como nota de crédito vigente
                        NotaCredito.objects.create(
                            pedido=pedido,
                            monto=-diferencia,
                            motivo=f'Diferencia a favor por cambio de {variante_devuelta.producto.nombre} por {variante_entregada.producto.nombre}',
                        )
                        detalle_diferencia = f' Se generó una nota de crédito por ${-diferencia} a favor del cliente.'

                    # Crear registro de cambio
                    Cambio.objects.create(
                        pedido=pedido,
                        variante_devuelta=variante_devuelta,
                        producto_devuelto=variante_devuelta.producto,
                        variante_entregada=variante_entregada,
                        producto_entregado=variante_entregada.producto,
                        motivo=motivo,
                    )
            except ValueError as error:
                messages.error(request, str(error))
                return redirect('pedidos:detalle_pedido', pedido_id=pedido.id)

            messages.success(request, f'Cambio registrado y stock actualizado.{detalle_diferencia}')
        else:
            messages.error(request, 'Debes seleccionar el producto devuelto y el entregado.')

    return redirect('pedidos:detalle_pedido', pedido_id=pedido.id)


def unidades_cambiables(pedido_item):
    """Unidades de un ítem que todavía se pueden cambiar: lo comprado menos los cambios ya
    registrados de ese talle en el pedido y lo devuelto con notas de crédito."""
    cambios_previos = Cambio.objects.filter(
        pedido=pedido_item.pedido,
        variante_devuelta=pedido_item.variante,
    ).count()
    return max(unidades_devolvibles(pedido_item) - cambios_previos, 0)


def unidades_devolvibles(pedido_item):
    """Unidades de un ítem que todavía se pueden devolver con nota de crédito."""
    devueltas = pedido_item.devoluciones.exclude(nota_credito__estado='anulada').aggregate(
        total=Sum('cantidad')
    )['total'] or 0
    return max(pedido_item.cantidad - devueltas, 0)


@admin_required
@require_POST
def crear_nota_credito(request, pedido_id):
    """Crea una nota de crédito para un pedido confirmado; opcionalmente devuelve unidades al stock."""
    pedido = get_object_or_404(Pedido, pk=pedido_id)

    if pedido.estado not in Pedido.ESTADOS_CON_STOCK_DESCONTADO:
        messages.error(request, 'Solo se pueden emitir notas de crédito sobre pedidos confirmados (pago aceptado en adelante).')
        return redirect('pedidos:detalle_pedido', pedido_id=pedido.id)

    monto = request.POST.get('monto')
    motivo = request.POST.get('motivo', '')

    if not monto:
        messages.error(request, 'Debes ingresar un monto.')
        return redirect('pedidos:detalle_pedido', pedido_id=pedido.id)

    try:
        monto_nota = Decimal(str(monto).strip().replace(',', '.'))
    except (InvalidOperation, ValueError):
        monto_nota = None

    if monto_nota is None or not monto_nota.is_finite():
        messages.error(request, 'Monto inválido.')
        return redirect('pedidos:detalle_pedido', pedido_id=pedido.id)
    if monto_nota <= 0:
        messages.error(request, 'El monto debe ser mayor a 0.')
        return redirect('pedidos:detalle_pedido', pedido_id=pedido.id)

    ya_acreditado = pedido.notas_credito.exclude(estado='anulada').aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
    disponible = max(Decimal('0.00'), pedido.total - ya_acreditado)
    if monto_nota > disponible:
        messages.error(
            request,
            f'El monto no puede superar ${disponible} '
            '(total del pedido menos las notas de crédito ya emitidas).'
        )
        return redirect('pedidos:detalle_pedido', pedido_id=pedido.id)

    # Unidades devueltas por ítem (vuelven al stock del talle y color vendidos)
    devoluciones = []
    for item in pedido.items.select_related('variante__producto', 'variante__talle'):
        try:
            cantidad = int(request.POST.get(f'devolver_{item.id}') or 0)
        except (TypeError, ValueError):
            cantidad = 0
        if cantidad <= 0:
            continue
        maximo = unidades_devolvibles(item)
        if cantidad > maximo:
            messages.error(
                request,
                f'De {item.variante.producto.nombre} (talle {item.variante.talle.nombre}) '
                f'se pueden devolver como máximo {maximo} unidad(es).'
            )
            return redirect('pedidos:detalle_pedido', pedido_id=pedido.id)
        devoluciones.append((item, cantidad))

    with transaction.atomic():
        nota = NotaCredito.objects.create(
            pedido=pedido,
            monto=monto_nota.quantize(Decimal('0.01')),
            motivo=motivo,
        )
        for item, cantidad in devoluciones:
            NotaCreditoItem.objects.create(nota_credito=nota, pedido_item=item, cantidad=cantidad)
            reponer_stock(item.variante, cantidad, item.color_nombre)

    detalle_stock = f' Se devolvieron {sum(c for _, c in devoluciones)} unidad(es) al stock.' if devoluciones else ''
    messages.success(request, f'Nota de crédito por ${nota.monto} creada correctamente.{detalle_stock}')
    return redirect('pedidos:detalle_pedido', pedido_id=pedido.id)


@admin_required
@require_POST
def actualizar_nota_credito(request, nota_id, accion):
    """Marca una nota de crédito vigente como usada (aplicada en otra compra) o la anula.
    Anularla vuelve a descontar las unidades que se habían devuelto al stock."""
    nota = get_object_or_404(NotaCredito, pk=nota_id)
    pedido_id = nota.pedido_id

    if nota.estado != 'vigente':
        messages.error(request, 'Solo se pueden modificar notas de crédito vigentes.')
    elif accion == 'usada':
        nota.estado = 'usada'
        nota.fecha_uso = timezone.now()
        nota.save(update_fields=['estado', 'fecha_uso'])
        messages.success(request, f'Nota de crédito #{nota.id} marcada como usada.')
    elif accion == 'anular':
        try:
            with transaction.atomic():
                for devolucion in nota.items.select_related('pedido_item__variante__producto', 'pedido_item__variante__talle'):
                    descontar_stock(
                        devolucion.pedido_item.variante,
                        devolucion.cantidad,
                        devolucion.pedido_item.color_nombre,
                    )
                nota.estado = 'anulada'
                nota.save(update_fields=['estado'])
        except ValueError as error:
            messages.error(request, f'No se puede anular la nota de crédito: {error}')
        else:
            messages.success(request, f'Nota de crédito #{nota.id} anulada.')
    else:
        messages.error(request, 'Acción no válida.')

    return redirect('pedidos:detalle_pedido', pedido_id=pedido_id)
