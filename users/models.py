from django.db import models
from django.contrib.auth.models import User


class Cliente(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    telefono = models.CharField(max_length=20)
    deuda_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return self.user.username


class Direccion(models.Model):
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name='direcciones'
    )
    calle = models.CharField(max_length=100)
    numero = models.CharField(max_length=10)
    ciudad = models.CharField(max_length=50)
    provincia = models.CharField(max_length=50)
    codigo_postal = models.CharField(max_length=10)

    def __str__(self):
        return f"{self.calle} {self.numero}"
#Django maneja:
#username
#password
#email
#login
#permisos
#se llama auth_user la tabla, no se ve, viene instalada dentro de django

