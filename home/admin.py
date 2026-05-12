from django.contrib import admin
from django.utils.html import format_html
from .models import SlideCarrousel


@admin.register(SlideCarrousel)
class SlideCarrouselAdmin(admin.ModelAdmin):
    list_display = ['preview_imagen', 'titulo', 'orden', 'activo', 'created_at']
    list_editable = ['orden', 'activo']
    list_filter = ['activo']
    search_fields = ['titulo', 'subtitulo']
    ordering = ['orden', '-created_at']

    def preview_imagen(self, obj):
        if obj.imagen:
            return format_html(
                '<img src="{}" style="height:50px; width:auto; border-radius:4px;" />',
                obj.imagen.url
            )
        return '-'
    preview_imagen.short_description = 'Preview'
