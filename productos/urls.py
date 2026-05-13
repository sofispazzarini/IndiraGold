
from django.urls import path
from . import views

app_name = 'productos'

urlpatterns = [
    # --- VISTAS PÚBLICAS ---
    path('producto/<int:producto_id>/', views.detalle_producto, name='detalle_producto'),
    
    # --- GESTIÓN GENERAL Y NAVEGACIÓN ---
    path('gestion/', views.gestion_productos, name='gestion_productos'),
    path('categoria/<int:categoria_id>/', views.lista_subcategorias, name='lista_subcategorias'),
    path('subcategoria/<int:subcat_id>/productos/', views.productos_por_subcategoria, name='productos_por_subcategoria'),

    # --- PRODUCTOS (CRUD) ---
    path('subcategoria/<int:subcat_id>/productos/agregar/', views.agregar_producto, name='agregar_producto'),
    path('producto/<int:prod_id>/editar/', views.editar_producto, name='editar_producto'),
    path('producto/<int:prod_id>/eliminar/', views.eliminar_producto, name='eliminar_producto'),
    
    # AJAX para el modal de previsualización
    path('ajax/detalle-producto/<int:producto_id>/', views.obtener_detalle_producto_ajax, name='get_detalle_producto_ajax'),
    path('ajax/tabla-medidas/<int:producto_id>/', views.obtener_tabla_medidas_ajax, name='obtener_tabla_medidas'),

    # --- VARIANTES ---
    path('variante/<int:variante_id>/eliminar/', views.eliminar_variante, name='eliminar_variante'),

    # --- CATEGORÍAS Y SUBCATEGORÍAS ---
    path('agregar-categoria/', views.agregar_categoria, name='agregar_categoria'),
    path('categoria/<int:cat_id>/eliminar/', views.eliminar_categoria, name='eliminar_categoria'),
    
    path('agregar-subcategoria/', views.agregar_subcategoria, name='agregar_subcategoria'),
    path('categoria/<int:cat_id>/subcategorias/gestion/', views.gestion_subcategorias, name='gestion_subcategorias'),
    path('subcategoria/<int:subcat_id>/eliminar/', views.eliminar_subcategoria, name='eliminar_subcategoria'),

    # --- PROVEEDORES Y MEDIDAS ---
    path('proveedores/agregar/', views.agregar_proveedor, name='agregar_proveedor'),
    path('proveedores/editar/<int:proveedor_id>/', views.editar_proveedor, name='editar_proveedor'),
    path('medidas/', views.gestion_medidas, name='gestion_medidas'),
    path('ajax/actualizar-variante/', views.actualizar_variante_ajax, name='actualizar_variante_ajax'),
    path('producto/foto/eliminar/<int:foto_id>/', views.eliminar_foto_galeria, name='eliminar_foto'),
    path('variante/editar/<int:variante_id>/', views.editar_variante, name='editar_variante'),
    path('producto/eliminar-esquema/<int:prod_id>/', views.eliminar_esquema_tecnico, name='eliminar_esquema'),
    path('buscar-productos/',views.buscar_productos,name='buscar_productos'),
    # --- QR CODES ---
    path('variante-color/<int:vc_id>/qr/', views.variante_color_qr, name='variante_color_qr'),
    path('producto/<int:producto_id>/qrs/', views.producto_qrs_impresion, name='producto_qrs_impresion'),
    path('variantes/<int:producto_id>/',views.obtener_variantes_producto,name='obtener_variantes_producto'),
]