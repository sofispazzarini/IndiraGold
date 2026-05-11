from django.db import models

class TemaConsulta(models.Model):
    nombre = models.CharField(max_length=100, verbose_name="Título")
    descripcion = models.TextField(blank=True, verbose_name="Descripción")
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Tema de consulta"
        verbose_name_plural = "Temas de consulta"

    def __str__(self):
        return self.nombre

class Consulta(models.Model):
    tema = models.ForeignKey(
        TemaConsulta,
        on_delete=models.CASCADE,
        related_name='consultas'
    )
    pregunta = models.TextField(verbose_name="Pregunta")
    respuesta = models.TextField(verbose_name="Respuesta")
    orden = models.PositiveIntegerField(default=0, verbose_name="Orden")
    activa = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['orden', 'created_at']
        verbose_name = "Pregunta frecuente"
        verbose_name_plural = "Preguntas frecuentes"

    def __str__(self):
        return self.pregunta[:50]

