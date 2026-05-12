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
