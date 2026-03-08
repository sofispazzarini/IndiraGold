from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from .views import CustomPasswordChangeView

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("registro/", views.registro, name="registro"),
    path("confirmar-direccion/", views.confirmar_direccion, name="confirmar_direccion"),
    path('verificar-codigo-email/', views.verificar_codigo_email, name='verificar_codigo_email'),
    path('registro-manual-cliente/', views.registro_manual_cliente, name='registro_manual_cliente'),
    path('admin/dashboard/', views.dashboard_admin, name='dashboard_admin'),
    path('cliente/dashboard/', views.dashboard_cliente, name='dashboard_cliente'),
    path('password_change/', CustomPasswordChangeView.as_view(), name='password_change'),
    path('admin/clientes/', views.listado_clientes, name='listado_clientes'),
    path('admin/clientes/<int:cliente_id>/editar/', views.editar_cliente, name='editar_cliente'),
]