
from django.urls import path
from . import views

urlpatterns = [
    path('subcategoria/<int:subcat_id>/eliminar/', views.eliminar_subcategoria, name='eliminar_subcategoria'),
    path('categoria/<int:cat_id>/eliminar/', views.eliminar_categoria, name='eliminar_categoria'),
    path('gestion/', views.gestion_productos, name='gestion_productos'),
    path('agregar-categoria/', views.agregar_categoria, name='agregar_categoria'),
    path('agregar-subcategoria/', views.agregar_subcategoria, name='agregar_subcategoria'),
    path('categoria/<int:cat_id>/subcategorias/', views.gestion_subcategorias, name='gestion_subcategorias'),
    path('subcategoria/<int:subcat_id>/productos/', views.productos_por_subcategoria, name='productos_por_subcategoria'),
    path('subcategoria/<int:subcat_id>/productos/agregar/', views.agregar_producto, name='agregar_producto'),
    path('medidas/', views.gestion_medidas, name='gestion_medidas'),
    path('proveedores/agregar/', views.agregar_proveedor, name='agregar_proveedor'),
    path('proveedores/editar/<int:proveedor_id>/', views.editar_proveedor, name='editar_proveedor'),
    
    path('', views.ProductoListView.as_view(), name='producto_list'),
    path('nuevo/', views.ProductoCreateView.as_view(), name='producto_create'),
    path('<int:pk>/', views.ProductoDetailView.as_view(), name='producto_detail'),
    path('<int:pk>/editar/', views.ProductoUpdateView.as_view(), name='producto_update'),
    path('<int:pk>/eliminar/', views.ProductoDeleteView.as_view(), name='producto_delete'),
]


