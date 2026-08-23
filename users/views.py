from django.contrib.auth import logout
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.contrib.auth.views import PasswordChangeView
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
import random
from django.core.mail import send_mail
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login as auth_login
from .forms import RegistroUsuarioForm, capitalizar_texto
from .models import Cliente, Direccion, direcciones_sin_duplicados
from django.db.models import Q
from django.db import IntegrityError
from django.contrib.auth.models import User
from .forms_manual import RegistroManualClienteForm, EditarClienteForm, NuevaDireccionForm
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.contrib.auth.decorators import user_passes_test
from carritos.utils import vincular_carrito_con_usuario
from django.http import JsonResponse
from django.contrib.auth.models import User
# --- LOGOUT VIEW ---
def logout_view(request):
    logout(request)
    return redirect(reverse('home:home'))
# Vista personalizada para cambio de contraseña con mensaje de éxito en la misma página
class CustomPasswordChangeView(PasswordChangeView):
    template_name = 'users/password_change.html'
    success_url = '/users/password_change/'

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, '¡Tu contraseña se cambió correctamente!')
        return response
# Vista dashboard para cliente normal

@login_required
def dashboard_cliente(request):
    from pedidos.models import Pedido
    es_cliente_recurrente = False
    try:
        cliente = request.user.cliente
        es_cliente_recurrente = Pedido.objects.filter(cliente=cliente).exists()
    except:
        pass
    return render(request, 'users/dashboard_cliente.html', {
        'es_cliente_recurrente': es_cliente_recurrente
    })


@login_required
def perfil(request):
    cliente = request.user.cliente
    mensaje = None
    mensaje_tipo = None

    if request.method == 'POST':
        if 'eliminar_direccion_cliente' in request.POST:
            direccion = get_object_or_404(Direccion, pk=request.POST.get('eliminar_direccion_cliente'), cliente=cliente)
            direccion.delete()
            mensaje = 'Direccion eliminada correctamente.'
            mensaje_tipo = 'success'
            direccion_form = NuevaDireccionForm(initial={'cliente': cliente})
        elif 'editar_direccion_cliente' in request.POST:
            direccion = get_object_or_404(Direccion, pk=request.POST.get('editar_direccion_cliente'), cliente=cliente)
            direccion_form = NuevaDireccionForm(request.POST, instance=direccion, initial={'cliente': cliente})
            if direccion_form.is_valid():
                direccion_form.save()
                mensaje = 'Direccion actualizada correctamente.'
                mensaje_tipo = 'success'
                direccion_form = NuevaDireccionForm(initial={'cliente': cliente})
            else:
                mensaje = 'Por favor revisa los datos de la direccion.'
                mensaje_tipo = 'danger'
        elif 'agregar_direccion_cliente' in request.POST:
            direccion_form = NuevaDireccionForm(request.POST, initial={'cliente': cliente})
            if direccion_form.is_valid():
                direccion = direccion_form.save(commit=False)
                direccion.cliente = cliente
                direccion.save()
                mensaje = 'Direccion agregada correctamente.'
                mensaje_tipo = 'success'
                direccion_form = NuevaDireccionForm(initial={'cliente': cliente})
            else:
                mensaje = 'Por favor revisa los datos de la direccion.'
                mensaje_tipo = 'danger'
        else:
            nombre = request.POST.get('nombre', '').strip()
            apellido = request.POST.get('apellido', '').strip()
            email = request.POST.get('email', '').strip()
            telefono = request.POST.get('telefono', '').strip()

            if nombre:
                request.user.first_name = capitalizar_texto(nombre)
            if apellido:
                request.user.last_name = capitalizar_texto(apellido)
            if email:
                request.user.email = email
            if telefono:
                cliente.telefono = telefono

            if 'foto_perfil' in request.FILES:
                cliente.foto_perfil = request.FILES['foto_perfil']

            if 'eliminar_foto' in request.POST:
                cliente.foto_perfil.delete(save=False)
                cliente.foto_perfil = None

            request.user.save()
            cliente.save()
            mensaje = 'Perfil actualizado correctamente.'
            mensaje_tipo = 'success'
            direccion_form = NuevaDireccionForm(initial={'cliente': cliente})
    else:
        direccion_form = NuevaDireccionForm(initial={'cliente': cliente})

    direcciones = cliente.direcciones.all().order_by('etiqueta', 'calle', 'numero')

    return render(request, 'users/perfil.html', {
        'cliente': cliente,
        'direcciones': direcciones,
        'direccion_form': direccion_form,
        'mensaje': mensaje,
        'mensaje_tipo': mensaje_tipo,
    })


@login_required
@user_passes_test(lambda u: u.is_superuser)
def dashboard_admin(request):
    from productos.models import Categoria, Producto
    from pedidos.models import Pedido
    from django.db.models import Sum

    total_clientes = Cliente.objects.count()
    total_categorias = Categoria.objects.count()
    total_productos = Producto.objects.count()
    pedidos_activos = Pedido.objects.exclude(estado__in=['entregado', 'cancelado', 'vencido']).count()

    # Pedidos por estado
    pedidos_pendientes = Pedido.objects.filter(estado='pendiente').count()
    pedidos_aceptados = Pedido.objects.filter(estado='aceptado').count()
    pedidos_en_preparacion = Pedido.objects.filter(estado='en_preparacion').count()
    pedidos_enviados = Pedido.objects.filter(estado='enviado').count()

    # Deudas activas
    pedidos_con_deuda = Pedido.objects.filter(deuda__gt=0).select_related('cliente__user').order_by('-deuda')[:10]
    total_deudas = Pedido.objects.filter(deuda__gt=0).aggregate(total=Sum('deuda'))['total'] or 0
    cantidad_deudas = Pedido.objects.filter(deuda__gt=0).count()

    context = {
        'total_clientes': total_clientes,
        'total_categorias': total_categorias,
        'total_productos': total_productos,
        'pedidos_activos': pedidos_activos,
        'pedidos_pendientes': pedidos_pendientes,
        'pedidos_aceptados': pedidos_aceptados,
        'pedidos_en_preparacion': pedidos_en_preparacion,
        'pedidos_enviados': pedidos_enviados,
        'pedidos_con_deuda': pedidos_con_deuda,
        'total_deudas': total_deudas,
        'cantidad_deudas': cantidad_deudas,
    }
    return render(request, 'users/dashboard_admin.html', context)
# Vista para listado y búsqueda de clientes (solo admin)
@login_required
@user_passes_test(lambda u: u.is_superuser)
def listado_clientes(request):
    query = request.GET.get('q', '').strip()
    clientes = Cliente.objects.select_related('user').filter(user__is_superuser=False)
    if query:
        clientes = clientes.filter(
            Q(dni__icontains=query) |
            Q(user__email__icontains=query)
        )
    return render(request, 'users/listado_clientes.html', {'clientes': clientes})
# Vista para agregar nueva dirección a un cliente (solo admin)
@login_required
@user_passes_test(lambda u: u.is_superuser)
def agregar_direccion(request, cliente_id):
    cliente = Cliente.objects.get(pk=cliente_id)
    direcciones = direcciones_sin_duplicados(cliente.direcciones.all().order_by('etiqueta', 'calle', 'numero'))
    mensaje = None
    if request.method == 'POST':
        form = NuevaDireccionForm(request.POST, initial={'cliente': cliente})
        if form.is_valid():
            # Verificar si ya existe una dirección igual usando el método del modelo
            etiqueta = form.cleaned_data.get('etiqueta', '')
            calle = form.cleaned_data.get('calle', '')
            numero = form.cleaned_data.get('numero', '')
            ciudad = form.cleaned_data.get('ciudad', '')
            provincia = form.cleaned_data.get('provincia', '')
            codigo_postal = form.cleaned_data.get('codigo_postal', '')
            referencia = form.cleaned_data.get('referencia', '')

            clave = Direccion.clave_unica(etiqueta, calle, numero, ciudad, provincia, codigo_postal, referencia)
            existe = any(d.clave_normalizada == clave for d in cliente.direcciones.all())

            if existe:
                mensaje = 'Ya existe una dirección igual para este cliente.'
            else:
                direccion = form.save(commit=False)
                direccion.cliente = cliente
                direccion.save()
                mensaje = 'Dirección agregada correctamente.'
                form = NuevaDireccionForm(initial={'cliente': cliente})  # Limpiar formulario
                direcciones = direcciones_sin_duplicados(cliente.direcciones.all().order_by('etiqueta', 'calle', 'numero'))  # Actualizar lista
        else:
            mensaje = 'Por favor revisa los datos ingresados.'
    else:
        form = NuevaDireccionForm(initial={'cliente': cliente})
    return render(request, 'users/agregar_direccion.html', {'form': form, 'cliente': cliente, 'mensaje': mensaje, 'direcciones': direcciones})
# Vista para editar cliente (solo admin)
@login_required
@user_passes_test(lambda u: u.is_superuser)
def editar_cliente(request, cliente_id):
    cliente = Cliente.objects.select_related('user').get(pk=cliente_id)
    user = cliente.user
    mensaje = None
    if request.method == 'POST':
        form = EditarClienteForm(request.POST, instance=cliente, user_instance=user)
        if form.is_valid():
            # Actualizar datos del user y cliente
            user.first_name = form.cleaned_data['nombre']
            user.email = form.cleaned_data['email']
            user.save()
            cliente.telefono = form.cleaned_data['telefono']
            cliente.save()
            mensaje = 'Datos actualizados correctamente.'
        else:
            mensaje = 'Por favor revisa los datos ingresados.'
    else:
        form = EditarClienteForm(instance=cliente, user_instance=user)
    return render(request, 'users/editar_cliente.html', {'form': form, 'cliente': cliente, 'mensaje': mensaje})


def _html_codigo_verificacion(codigo):
    return f"""
    <div style="margin:0;padding:32px 0;background:#f7f1e8;font-family:Arial,Helvetica,sans-serif;color:#1f1915;">
      <div style="max-width:560px;margin:0 auto;background:#fffdf9;border:1px solid #eadcc6;border-radius:18px;overflow:hidden;">
        <div style="padding:28px 30px 20px;text-align:center;border-bottom:1px solid #eadcc6;">
          <div style="font-family:Georgia,serif;font-size:30px;color:#b88a18;letter-spacing:.5px;">IndiraGold</div>
          <div style="margin-top:6px;font-size:11px;letter-spacing:4px;text-transform:uppercase;color:#8b7769;">Verificacion de cuenta</div>
        </div>
        <div style="padding:30px;">
          <h1 style="margin:0 0 12px;font-family:Georgia,serif;font-size:28px;line-height:1.2;color:#111;">Tu codigo de verificacion</h1>
          <p style="margin:0 0 22px;font-size:15px;line-height:1.6;color:#6f6259;">
            Usalo para confirmar tu correo y terminar el registro de tu cuenta.
          </p>
          <div style="margin:24px 0;padding:20px;text-align:center;background:#fff7dc;border:1px solid #e6c766;border-radius:14px;">
            <div style="font-size:36px;line-height:1;font-weight:700;letter-spacing:10px;color:#7a0030;">{codigo}</div>
          </div>
          <p style="margin:22px 0 0;font-size:13px;line-height:1.5;color:#8b7769;">
            Si no solicitaste este registro, podes ignorar este mensaje.
          </p>
        </div>
      </div>
    </div>
    """


def registro(request):
    error = None
    show_verification_modal = False
    initial_data = request.session.get('registro_data')

    if request.method == 'POST':
        form = RegistroUsuarioForm(request.POST)
        if form.is_valid():
            dni = form.cleaned_data.get('dni')
            email = form.cleaned_data.get('email')
            if (
                User.objects.filter(username=dni).exists()
                or Cliente.objects.filter(dni=dni).exists()
                or User.objects.filter(email=email).exists()
                or Cliente.objects.filter(user__email=email).exists()
            ):
                error = 'Ya existe una cuenta registrada con estos datos (DNI o correo electrónico).'
            else:
                # Generar código de verificación
                codigo = str(random.randint(100000, 999999))
                # Guardar datos y código en sesión
                request.session['registro_data'] = form.cleaned_data
                request.session['codigo_verificacion'] = codigo
                request.session['email_verificado'] = False
                # Enviar email
                send_mail(
                    'Código de verificación Indira Gold',
                    f'Tu código de verificación es: {codigo}',
                    settings.EMAIL_HOST_USER,
                    [email],
                    fail_silently=False,
                    html_message=_html_codigo_verificacion(codigo),
                )
                show_verification_modal = True
        else:
            error = 'Por favor revisa los datos ingresados.'
    else:
        if initial_data:
            form = RegistroUsuarioForm(initial=initial_data)
        else:
            form = RegistroUsuarioForm()
    return render(request, 'users/registro.html', {
        'form': form,
        'error': error,
        'show_verification_modal': show_verification_modal
    })



@csrf_exempt
def verificar_codigo_email(request):
    if request.method == 'POST':
        codigo_usuario = request.POST.get('codigo')
        codigo_sesion = request.session.get('codigo_verificacion')
        if codigo_usuario and codigo_sesion and codigo_usuario == codigo_sesion:
            request.session['email_verificado'] = True
            return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'error': 'Código incorrecto'})
    return JsonResponse({'success': False, 'error': 'Método no permitido'})


def confirmar_direccion(request):
    data = request.session.get("registro_data")

    if not data:
        return redirect("users:registro")

    # Si POST con campos de dirección: actualizar sesión y devolver JSON
    if request.method == "POST" and all(k in request.POST for k in ["etiqueta", "calle", "numero", "ciudad", "provincia", "codigo_postal"]):
        data['etiqueta'] = capitalizar_texto(request.POST.get('etiqueta', data.get('etiqueta')))
        data['calle'] = capitalizar_texto(request.POST.get('calle', data.get('calle')))
        data['numero'] = request.POST.get('numero', data.get('numero'))
        data['ciudad'] = capitalizar_texto(request.POST.get('ciudad', data.get('ciudad')))
        data['provincia'] = capitalizar_texto(request.POST.get('provincia', data.get('provincia')))
        data['codigo_postal'] = request.POST.get('codigo_postal', data.get('codigo_postal'))
        data['referencia'] = capitalizar_texto(request.POST.get('referencia', data.get('referencia', '')))
        request.session['registro_data'] = data
        return JsonResponse({'success': True})

    # Confirmación final de dirección (POST sin campos de dirección)
    elif request.method == "POST":
        form = RegistroUsuarioForm(data)
        if form.is_valid():
            try:
                form.save()
            except IntegrityError:
                return render(request, "users/confirmar_direccion.html", {
                    "data": data,
                    "form": form,
                    "error": "Ya existe una cuenta con ese DNI o correo. Inicia sesion con tu DNI o volve al registro con otros datos.",
                })
            request.session.pop("registro_data", None)
            return redirect("users:login")
        return render(request, "users/confirmar_direccion.html", {"data": data, "form": form, "error": "No pudimos confirmar la direcciÃ³n. RevisÃ¡ los datos e intentÃ¡ de nuevo."})

    # Render normal
    form = RegistroUsuarioForm(initial=data)
    return render(request, "users/confirmar_direccion.html", {"data": data, "form": form})

def home(request):
    return redirect('home:home')

# users/views.py

def login_view(request):
    error = None
    if request.method == 'POST':
        dni = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=dni, password=password)
        if user is not None:
            carrito_temporal = request.session.get('carrito', {})
            old_session_key = request.session.session_key
            
            auth_login(request, user) # Django limpia la sesión acá

            # Vincular carrito de invitado con usuario (ANTES de cualquier redirect)
            from carritos.utils import vincular_carrito_con_usuario, get_or_create_cart
            vincular_carrito_con_usuario(request, session_id_previo=old_session_key, carrito_sesion=carrito_temporal)

            # REDIRECCIÓN INTELIGENTE
            if user.is_superuser:
                return redirect('users:dashboard_admin')

            # Redirigir SIEMPRE a checkout si el usuario tenía productos en el carrito de la sesión antes de loguear
            if carrito_temporal and any(int(q) > 0 for q in carrito_temporal.values()):
                return redirect('pedidos:checkout')
            # Si no, verificar si el carrito en BD tiene productos
            try:
                carrito = get_or_create_cart(request)
                if carrito.items.exists():
                    return redirect('pedidos:checkout')
            except Exception:
                pass
            return redirect('users:dashboard_cliente')

            
        else:
            error = 'DNI o contraseña incorrectos.'
            
    return render(request, 'users/login.html', {'error': error})
# Vista para registro manual de cliente (solo admin)
@user_passes_test(lambda u: u.is_superuser)
def registro_manual_cliente(request):
    
    mensaje = None
    if request.method == 'POST':
        form = RegistroManualClienteForm(request.POST)
        if form.is_valid():
            dni = form.cleaned_data['dni']
            nombre = form.cleaned_data['nombre']
            apellido = form.cleaned_data['apellido']
            email = form.cleaned_data['email']
            telefono = form.cleaned_data['telefono']
            etiqueta = form.cleaned_data['etiqueta']
            referencia = form.cleaned_data.get('referencia', '')
            calle = form.cleaned_data['calle']
            numero = form.cleaned_data['numero']
            ciudad = form.cleaned_data['ciudad']
            provincia = form.cleaned_data['provincia']
            codigo_postal = form.cleaned_data['codigo_postal']
            password = dni  # La contraseña será el mismo DNI

            user = User.objects.create_user(username=dni, email=email, password=password, first_name=nombre, last_name=apellido)
            cliente = Cliente.objects.create(user=user, dni=dni, telefono=telefono)
            Direccion.objects.create(cliente=cliente, etiqueta=etiqueta, referencia=referencia, calle=calle, numero=numero, ciudad=ciudad, provincia=provincia, codigo_postal=codigo_postal)

            # Enviar email con usuario y contraseña
            from django.core.mail import send_mail
            from django.conf import settings
            print('Enviando mail de registro manual a:', email)
            send_mail(
                'Bienvenido a Indira Gold',
                f'Hola {nombre},\n\nTu usuario ha sido registrado correctamente.\n\nUsuario: {dni}\nContraseña: {password}\n\nPuedes iniciar sesión en el sistema con estos datos.\n\nPor seguridad, te recomendamos cambiar tu contraseña después de ingresar por primera vez desde el panel de tu cuenta.',
                settings.EMAIL_HOST_USER,
                [email],
                fail_silently=False,
            )

            mensaje = 'Cliente registrado correctamente.'
            form = RegistroManualClienteForm()  # Limpiar formulario
        else:
            mensaje = 'Por favor revisa los datos ingresados.'
    else:
        form = RegistroManualClienteForm()
    return render(request, 'users/registro_manual_cliente.html', {'form': form, 'mensaje': mensaje})
def buscar_clientes(request):

    q = request.GET.get('q', '')

    clientes = User.objects.filter(is_staff=False).filter(
        Q(first_name__icontains=q)
        | Q(last_name__icontains=q)
        | Q(email__icontains=q)
        | Q(username__icontains=q)
    )[:5]

    data = []

    for cliente in clientes:

        data.append({

            'id': cliente.id,

            'nombre': f'{cliente.first_name} {cliente.last_name}',

            'email': cliente.email

        })

    return JsonResponse(data, safe=False)


@user_passes_test(lambda u: u.is_superuser)
def direcciones_cliente_ajax(request, cliente_id):
    cliente = get_object_or_404(Cliente, user_id=cliente_id)
    direcciones = direcciones_sin_duplicados(
        cliente.direcciones.all().order_by('etiqueta', 'calle', 'numero')
    )

    return JsonResponse({
        'success': True,
        'direcciones': [
            {
                'id': direccion.id,
                'etiqueta': direccion.etiqueta,
                'calle': direccion.calle,
                'numero': direccion.numero,
                'ciudad': direccion.ciudad,
                'provincia': direccion.provincia,
                'codigo_postal': direccion.codigo_postal,
                'referencia': direccion.referencia,
                'texto': (
                    f'{direccion.etiqueta}: {direccion.calle} {direccion.numero}, '
                    f'{direccion.ciudad}, {direccion.provincia} - CP {direccion.codigo_postal}'
                ),
            }
            for direccion in direcciones
        ],
    })


@user_passes_test(lambda u: u.is_superuser)
@require_POST
def crear_cliente_ajax(request):
    nombre = capitalizar_texto(request.POST.get('nombre', ''))
    apellido = capitalizar_texto(request.POST.get('apellido', ''))
    dni = request.POST.get('dni', '').strip()
    email = request.POST.get('email', '').strip()
    telefono = request.POST.get('telefono', '').strip()

    if not all([nombre, apellido, dni, email, telefono]):
        return JsonResponse({'success': False, 'error': 'Completá todos los campos del cliente.'}, status=400)
    if not dni.isdigit() or len(dni) not in [7, 8]:
        return JsonResponse({'success': False, 'error': 'El DNI debe tener 7 u 8 números.'}, status=400)
    if User.objects.filter(username=dni).exists() or Cliente.objects.filter(dni=dni).exists():
        return JsonResponse({'success': False, 'error': 'Ya existe un cliente con ese DNI.'}, status=400)
    if User.objects.filter(email=email).exists():
        return JsonResponse({'success': False, 'error': 'Ya existe un usuario con ese email.'}, status=400)

    user = User.objects.create_user(
        username=dni,
        email=email,
        password=dni,
        first_name=nombre,
        last_name=apellido,
    )
    Cliente.objects.create(user=user, dni=dni, telefono=telefono)

    return JsonResponse({
        'success': True,
        'cliente': {
            'id': user.id,
            'nombre': f'{nombre} {apellido}',
            'email': email,
        }
    })


@user_passes_test(lambda u: u.is_superuser)
@require_POST
def crear_direccion_ajax(request):
    cliente_id = request.POST.get('cliente_id')
    cliente = get_object_or_404(Cliente, user_id=cliente_id)

    etiqueta = capitalizar_texto(request.POST.get('etiqueta', ''))
    calle = capitalizar_texto(request.POST.get('calle', ''))
    numero = request.POST.get('numero', '').strip()
    ciudad = capitalizar_texto(request.POST.get('ciudad', ''))
    provincia = capitalizar_texto(request.POST.get('provincia', ''))
    codigo_postal = request.POST.get('codigo_postal', '').strip()
    referencia = capitalizar_texto(request.POST.get('referencia', ''))

    if not all([etiqueta, calle, numero, ciudad, provincia, codigo_postal]):
        return JsonResponse({'success': False, 'error': 'Completá los datos obligatorios de la dirección.'}, status=400)

    clave = Direccion.clave_unica(etiqueta, calle, numero, ciudad, provincia, codigo_postal, referencia)
    for direccion_existente in cliente.direcciones.all():
        if direccion_existente.clave_normalizada == clave:
            return JsonResponse({'success': False, 'error': 'Esa dirección ya está cargada para la clienta.'}, status=400)

    direccion = Direccion.objects.create(
        cliente=cliente,
        etiqueta=etiqueta,
        calle=calle,
        numero=numero,
        ciudad=ciudad,
        provincia=provincia,
        codigo_postal=codigo_postal,
        referencia=referencia,
    )

    return JsonResponse({
        'success': True,
        'direccion': {
            'id': direccion.id,
            'texto': f'{direccion.etiqueta}: {direccion.calle} {direccion.numero}, {direccion.ciudad}, {direccion.provincia} - CP {direccion.codigo_postal}',
        },
    })


@login_required
@require_POST
def crear_direccion_cliente_ajax(request):
    cliente, _ = Cliente.objects.get_or_create(user=request.user)

    etiqueta = capitalizar_texto(request.POST.get('etiqueta', ''))
    calle = capitalizar_texto(request.POST.get('calle', ''))
    numero = request.POST.get('numero', '').strip()
    ciudad = capitalizar_texto(request.POST.get('ciudad', ''))
    provincia = capitalizar_texto(request.POST.get('provincia', ''))
    codigo_postal = request.POST.get('codigo_postal', '').strip()
    referencia = capitalizar_texto(request.POST.get('referencia', ''))

    if not all([etiqueta, calle, numero, ciudad, provincia, codigo_postal]):
        return JsonResponse({'success': False, 'error': 'Completa los datos obligatorios de la direccion.'}, status=400)

    clave = Direccion.clave_unica(etiqueta, calle, numero, ciudad, provincia, codigo_postal, referencia)
    for direccion_existente in cliente.direcciones.all():
        if direccion_existente.clave_normalizada == clave:
            return JsonResponse({'success': False, 'error': 'Esa direccion ya esta cargada en tu cuenta.'}, status=400)

    direccion = Direccion.objects.create(
        cliente=cliente,
        etiqueta=etiqueta,
        calle=calle,
        numero=numero,
        ciudad=ciudad,
        provincia=provincia,
        codigo_postal=codigo_postal,
        referencia=referencia,
    )

    return JsonResponse({
        'success': True,
        'direccion': {
            'id': direccion.id,
            'etiqueta': direccion.etiqueta,
            'calle': direccion.calle,
            'numero': direccion.numero,
            'ciudad': direccion.ciudad,
            'provincia': direccion.provincia,
            'codigo_postal': direccion.codigo_postal,
            'referencia': direccion.referencia,
        },
    })
