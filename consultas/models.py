from django.db import models
from django.contrib.auth.models import User

class TemaConsulta(models.Model):
    nombre = models.CharField(max_length=100)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre

class Consulta(models.Model):
    tema = models.ForeignKey(
        TemaConsulta,
        on_delete=models.CASCADE,
        related_name='consultas'
    )
    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )
    pregunta = models.TextField()
    respuesta = models.TextField(blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Consulta #{self.id}"

