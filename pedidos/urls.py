from django.urls import path
from . import views

app_name = 'pedidos'

urlpatterns = [
    path('gestion/', views.gestion_pedidos, name='gestion_pedidos'),
]
