from django.urls import path
from . import views

app_name = 'home'

urlpatterns = [
    path('', views.HomePublicaView.as_view(), name='home'),

    # Gestión carrousel (admin)
    path('admin/carrousel/', views.gestion_carrousel, name='gestion_carrousel'),
    path('admin/carrousel/crear/', views.crear_slide, name='crear_slide'),
    path('admin/carrousel/<int:slide_id>/editar/', views.editar_slide, name='editar_slide'),
    path('admin/carrousel/<int:slide_id>/eliminar/', views.eliminar_slide, name='eliminar_slide'),
    path('admin/carrousel/<int:slide_id>/toggle/', views.toggle_slide, name='toggle_slide'),

    # Configuración Hero
    path('admin/hero/', views.configurar_hero, name='configurar_hero'),
]