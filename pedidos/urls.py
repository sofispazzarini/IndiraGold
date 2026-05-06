from django.urls import path
from . import views

app_name = 'pedidos'

urlpatterns = [
    path('gestion/', views.gestion_pedidos, name='gestion_pedidos'),
    path('historial-cliente/<int:cliente_id>/', views.historial_cliente, name='historial_cliente'),
    path('<int:pedido_id>/', views.detalle_pedido, name='detalle_pedido'),
]
