from django.contrib import admin
from django.utils.html import format_html
from .models import SlideCarrousel, ConfiguracionHero


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


@admin.register(ConfiguracionHero)
class ConfiguracionHeroAdmin(admin.ModelAdmin):
    list_display = ['eyebrow', 'titulo_linea1', 'activo', 'updated_at']
    fieldsets = (
        ('Textos', {
            'fields': ('eyebrow', 'titulo_linea1', 'titulo_linea2', 'subtitulo', 'texto_cta', 'link_cta')
        }),
        ('Colores', {
            'fields': ('color_fondo', 'color_texto', 'color_acento')
        }),
        ('Tipografía', {
            'fields': ('fuente_titulo',)
        }),
        ('Estado', {
            'fields': ('activo',)
        }),
    )

    def has_add_permission(self, request):
        if ConfiguracionHero.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False
