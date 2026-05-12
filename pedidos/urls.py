from django.urls import path
from . import views

app_name = 'pedidos'

urlpatterns = [
    path('gestion/', views.gestion_pedidos, name='gestion_pedidos'),
    path('estadisticas/', views.estadisticas_ventas, name='estadisticas_ventas'),
    path('gastos/', views.listado_gastos, name='listado_gastos'),
    path('gastos/crear/', views.crear_gasto, name='crear_gasto'),
    path('gastos/<int:gasto_id>/eliminar/', views.eliminar_gasto, name='eliminar_gasto'),
    path('historial-cliente/<int:cliente_id>/', views.historial_cliente, name='historial_cliente'),
    path('<int:pedido_id>/', views.detalle_pedido, name='detalle_pedido'),
    path('<int:pedido_id>/editar/', views.editar_pedido, name='editar_pedido'),
]
