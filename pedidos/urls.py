from django.urls import path
from . import views

app_name = 'pedidos'

urlpatterns = [
    path('gestion/', views.gestion_pedidos, name='gestion_pedidos'),
    path('historial-cliente/<int:cliente_id>/', views.historial_cliente, name='historial_cliente'),
    path('<int:pedido_id>/', views.detalle_pedido, name='detalle_pedido'),
    path('<int:pedido_id>/editar/', views.editar_pedido, name='editar_pedido'),
    path('checkout/', views.checkout_view, name='checkout'),
    path('confirmar/', views.confirmar_pedido, name='confirmar_pedido'),
    path('checkout/eliminar/<int:variante_id>/', views.eliminar_item_carrito, name='eliminar_item_carrito'),
    path('crear-pago/', views.crear_pago, name='crear_pago'),
    path('pago-exitoso/', views.pago_exitoso, name='pago_exitoso'),
    path('estado/<int:pedido_id>/',views.estado_pedido, name='estado_pedido'),
    path('mis-pedidos/',views.mis_pedidos,name='mis_pedidos'),
    path('aumentar-cantidad/<int:variante_id>/',views.aumentar_cantidad, name='aumentar_cantidad'),

    path('disminuir-cantidad/<int:variante_id>/',views.disminuir_cantidad,name='disminuir_cantidad'),
]
