from django.db import models


class SlideCarrousel(models.Model):
    imagen = models.ImageField(upload_to='carrousel/')
    titulo = models.CharField(max_length=100, blank=True)
    subtitulo = models.CharField(max_length=200, blank=True)
    link = models.URLField(blank=True, help_text='URL opcional al hacer clic')
    orden = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['orden', '-created_at']
        verbose_name = 'Slide del Carrousel'
        verbose_name_plural = 'Slides del Carrousel'

    def __str__(self):
        return self.titulo or f'Slide {self.pk}'


class ConfiguracionHero(models.Model):
    eyebrow = models.CharField(
        max_length=100,
        default='Nueva colección',
        help_text='Texto pequeño encima del título'
    )
    titulo_linea1 = models.CharField(
        max_length=100,
        default='Elegancia',
        help_text='Primera línea del título'
    )
    titulo_linea2 = models.CharField(
        max_length=100,
        default='que se siente',
        help_text='Segunda línea del título (en cursiva)'
    )
    subtitulo = models.CharField(
        max_length=255,
        default='Descubrí prendas únicas, pensadas para vos.'
    )
    texto_cta = models.CharField(
        max_length=50,
        default='Ver colección',
        help_text='Texto del botón'
    )
    link_cta = models.CharField(
        max_length=255,
        default='#catalogo',
        help_text='URL del botón'
    )

    color_fondo = models.CharField(
        max_length=20,
        default='#1a1612',
        help_text='Color de fondo (hex)'
    )
    color_texto = models.CharField(
        max_length=20,
        default='#ffffff',
        help_text='Color del texto (hex)'
    )
    color_acento = models.CharField(
        max_length=20,
        default='#b8922a',
        help_text='Color de acento/decoración (hex)'
    )

    FUENTES = [
        ('Cormorant Garamond', 'Cormorant Garamond (elegante)'),
        ('Playfair Display', 'Playfair Display (clásica)'),
        ('DM Sans', 'DM Sans (moderna)'),
    ]
    fuente_titulo = models.CharField(
        max_length=50,
        choices=FUENTES,
        default='Cormorant Garamond'
    )

    activo = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuración del Hero'
        verbose_name_plural = 'Configuración del Hero'

    def __str__(self):
        return 'Configuración Hero'

    @classmethod
    def actual(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
