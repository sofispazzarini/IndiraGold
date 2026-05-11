from django.contrib import admin
from .models import TemaConsulta, Consulta


@admin.register(TemaConsulta)
class TemaConsultaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activo', 'created_at')
    list_filter = ('activo',)
    search_fields = ('nombre', 'descripcion')
    list_editable = ('activo',)
    ordering = ('-created_at',)


@admin.register(Consulta)
class ConsultaAdmin(admin.ModelAdmin):
    list_display = ('pregunta', 'tema', 'activa', 'orden')
    list_filter = ('tema', 'activa')
    search_fields = ('pregunta', 'respuesta')
    list_editable = ('activa', 'orden')
    ordering = ('tema', 'orden')
