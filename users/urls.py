from productos.views import gestion_productos
from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from .views import CustomPasswordChangeView, logout_view

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("registro/", views.registro, name="registro"),
    path("confirmar-direccion/", views.confirmar_direccion, name="confirmar_direccion"),
    path('verificar-codigo-email/', views.verificar_codigo_email, name='verificar_codigo_email'),
    path('registro-manual-cliente/', views.registro_manual_cliente, name='registro_manual_cliente'),
    path('admin/dashboard/', views.dashboard_admin, name='dashboard_admin'),
    path('cliente/dashboard/', views.dashboard_cliente, name='dashboard_cliente'),
    path('cliente/perfil/', views.perfil, name='perfil'),
    path('password_change/', CustomPasswordChangeView.as_view(), name='password_change'),
    # Olvidé mi contraseña: link por email para elegir una nueva
    path('recuperar-contrasena/', auth_views.PasswordResetView.as_view(
        template_name='users/password_reset/formulario.html',
        email_template_name='users/password_reset/email.txt',
        subject_template_name='users/password_reset/asunto.txt',
        success_url=reverse_lazy('users:password_reset_done'),
    ), name='password_reset'),
    path('recuperar-contrasena/enviado/', auth_views.PasswordResetDoneView.as_view(
        template_name='users/password_reset/enviado.html',
    ), name='password_reset_done'),
    path('recuperar-contrasena/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='users/password_reset/nueva.html',
        success_url=reverse_lazy('users:password_reset_complete'),
    ), name='password_reset_confirm'),
    path('recuperar-contrasena/listo/', auth_views.PasswordResetCompleteView.as_view(
        template_name='users/password_reset/listo.html',
    ), name='password_reset_complete'),
    path('admin/clientes/', views.listado_clientes, name='listado_clientes'),
    path('admin/clientes/<int:cliente_id>/editar/', views.editar_cliente, name='editar_cliente'),
    path('admin/clientes/<int:cliente_id>/agregar-direccion/', views.agregar_direccion, name='agregar_direccion'),
    path('logout/', logout_view, name='logout'),
    path('buscar-clientes/',views.buscar_clientes,name='buscar_clientes'),
    path('ajax/crear-cliente/', views.crear_cliente_ajax, name='crear_cliente_ajax'),
    path('ajax/clientes/<int:cliente_id>/direcciones/', views.direcciones_cliente_ajax, name='direcciones_cliente_ajax'),
    path('ajax/crear-direccion/', views.crear_direccion_ajax, name='crear_direccion_ajax'),
    path('ajax/cliente/crear-direccion/', views.crear_direccion_cliente_ajax, name='crear_direccion_cliente_ajax'),
]
