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
    path('checkout/', views.checkout_view, name='checkout'),
    path('confirmar/', views.confirmar_pedido, name='confirmar_pedido'),
    path('checkout/eliminar/<int:variante_id>/', views.eliminar_item_carrito, name='eliminar_item_carrito'),
    path('crear-pago/', views.crear_pago, name='crear_pago'),
    path('pago-exitoso/', views.pago_exitoso, name='pago_exitoso'),
    path('estado/<int:pedido_id>/',views.estado_pedido, name='estado_pedido'),
    path('mis-pedidos/',views.mis_pedidos,name='mis_pedidos'),
    path('aumentar-cantidad/<int:variante_id>/',views.aumentar_cantidad, name='aumentar_cantidad'),
    path('disminuir-cantidad/<int:variante_id>/',views.disminuir_cantidad,name='disminuir_cantidad'),
    path('actualizar-estado/<int:pedido_id>/',views.actualizar_estado_pedido,name='actualizar_estado_pedido'),
    path('ventas-presenciales/',views.ventas_presenciales,name='ventas_presenciales'),
    path('registrar-venta-local/',views.registrar_venta_local,name='registrar_venta_local'),
    path('detalle-venta/<int:venta_id>/',views.detalle_venta_local,name='detalle_venta_local'),
    path('registrar-pago/<int:venta_id>/',views.registrar_pago_venta,name='registrar_pago_venta'),
]
