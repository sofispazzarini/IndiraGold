from django.urls import path

from . import views

app_name = "carritos"

urlpatterns = [
    path("agregar/", views.agregar_producto, name="agregar_producto"),
    path("eliminar/", views.eliminar_producto, name="eliminar_producto"),
    path("confirmar/", views.confirmar_compra, name="confirmar_compra"),
    path("expirar/", views.expirar_carrito, name="expirar_carrito"),
    path("sumar/", views.sumar_producto, name="sumar_producto"),
    path("restaurar/", views.restaurar_carrito, name="restaurar_carrito"),
]