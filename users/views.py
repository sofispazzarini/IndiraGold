from django.contrib.auth import logout
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.contrib.auth.views import PasswordChangeView
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
import random
from django.core.mail import send_mail
from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login
from .forms import RegistroUsuarioForm
from .models import Cliente, Direccion
from django.db.models import Q
from django.contrib.auth.models import User
from .forms_manual import RegistroManualClienteForm, EditarClienteForm, NuevaDireccionForm
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.contrib.auth.decorators import user_passes_test
from carritos.utils import vincular_carrito_con_usuario

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
    return render(request, 'users/dashboard_cliente.html')


@login_required
def perfil(request):
    cliente = request.user.cliente
    mensaje = None
    mensaje_tipo = None

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        apellido = request.POST.get('apellido', '').strip()
        email = request.POST.get('email', '').strip()
        telefono = request.POST.get('telefono', '').strip()

        if nombre:
            request.user.first_name = nombre
        if apellido:
            request.user.last_name = apellido
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

    direcciones = cliente.direcciones.all()

    return render(request, 'users/perfil.html', {
        'cliente': cliente,
        'direcciones': direcciones,
        'mensaje': mensaje,
        'mensaje_tipo': mensaje_tipo,
    })


@login_required
@user_passes_test(lambda u: u.is_superuser)
def dashboard_admin(request):
    from productos.models import Categoria, Producto
    from pedidos.models import Pedido

    total_clientes = Cliente.objects.count()
    total_categorias = Categoria.objects.count()
    total_productos = Producto.objects.count()
    pedidos_activos = Pedido.objects.exclude(estado__in=['entregado', 'cancelado', 'vencido']).count()

    # Pedidos por estado
    pedidos_pendientes = Pedido.objects.filter(estado='pendiente').count()
    pedidos_aceptados = Pedido.objects.filter(estado='aceptado').count()
    pedidos_en_preparacion = Pedido.objects.filter(estado='en_preparacion').count()
    pedidos_enviados = Pedido.objects.filter(estado='enviado').count()

    context = {
        'total_clientes': total_clientes,
        'total_categorias': total_categorias,
        'total_productos': total_productos,
        'pedidos_activos': pedidos_activos,
        'pedidos_pendientes': pedidos_pendientes,
        'pedidos_aceptados': pedidos_aceptados,
        'pedidos_en_preparacion': pedidos_en_preparacion,
        'pedidos_enviados': pedidos_enviados,
    }
    return render(request, 'users/dashboard_admin.html', context)
# Vista para listado y búsqueda de clientes (solo admin)
@login_required
@user_passes_test(lambda u: u.is_superuser)
def listado_clientes(request):
    query = request.GET.get('q', '').strip()
    clientes = Cliente.objects.select_related('user').all()
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
    direcciones = cliente.direcciones.all()
    mensaje = None
    if request.method == 'POST':
        form = NuevaDireccionForm(request.POST, initial={'cliente': cliente})
        if form.is_valid():
            direccion = form.save(commit=False)
            direccion.cliente = cliente
            direccion.save()
            mensaje = 'Dirección agregada correctamente.'
            form = NuevaDireccionForm()  # Limpiar formulario
            direcciones = cliente.direcciones.all()  # Actualizar lista
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


def registro(request):
    error = None
    show_verification_modal = False
    initial_data = request.session.get('registro_data')

    if request.method == 'POST':
        form = RegistroUsuarioForm(request.POST)
        if form.is_valid():
            dni = form.cleaned_data.get('dni')
            email = form.cleaned_data.get('email')
            if Cliente.objects.filter(dni=dni).exists() or Cliente.objects.filter(user__email=email).exists():
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
    if request.method == "POST" and all(k in request.POST for k in ["calle", "numero", "ciudad", "provincia", "codigo_postal"]):
        data['calle'] = request.POST.get('calle', data.get('calle'))
        data['numero'] = request.POST.get('numero', data.get('numero'))
        data['ciudad'] = request.POST.get('ciudad', data.get('ciudad'))
        data['provincia'] = request.POST.get('provincia', data.get('provincia'))
        data['codigo_postal'] = request.POST.get('codigo_postal', data.get('codigo_postal'))
        request.session['registro_data'] = data
        return JsonResponse({'success': True})

    # Confirmación final de dirección (POST sin campos de dirección)
    elif request.method == "POST":
        form = RegistroUsuarioForm(data)
        if form.is_valid():
            form.save()
            del request.session["registro_data"]
            return redirect("users:login")

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
            # 4. REDIRECCIÓN INTELIGENTE
            if user.is_superuser:
                return redirect('users:dashboard_admin')

            # 2. Los pasamos a la base de datos
            from carritos.utils import vincular_carrito_con_usuario, get_or_create_cart
            vincular_carrito_con_usuario(request, session_id_previo=old_session_key, carrito_sesion=carrito_temporal)

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
            email = form.cleaned_data['email']
            telefono = form.cleaned_data['telefono']
            calle = form.cleaned_data['calle']
            numero = form.cleaned_data['numero']
            ciudad = form.cleaned_data['ciudad']
            provincia = form.cleaned_data['provincia']
            codigo_postal = form.cleaned_data['codigo_postal']
            password = dni  # La contraseña será el mismo DNI

            user = User.objects.create_user(username=dni, email=email, password=password, first_name=nombre)
            cliente = Cliente.objects.create(user=user, dni=dni, telefono=telefono)
            Direccion.objects.create(cliente=cliente, calle=calle, numero=numero, ciudad=ciudad, provincia=provincia, codigo_postal=codigo_postal)

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