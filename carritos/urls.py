from django.urls import path

from . import views

app_name = "carritos"

urlpatterns = [
    path("agregar/", views.agregar_producto, name="agregar_producto"),
    path("eliminar/", views.eliminar_producto, name="eliminar_producto"),
    path("expirar/", views.expirar_carrito, name="expirar_carrito"),
]
