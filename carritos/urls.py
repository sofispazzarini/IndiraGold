from django.urls import path

from . import views

app_name = "carritos"

urlpatterns = [
    path("agregar/", views.agregar_producto, name="agregar_producto"),
]
