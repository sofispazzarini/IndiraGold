from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator


dni_validator = RegexValidator(
    regex=r'^\d{7,8}$',
    message="El DNI debe contener solo números (7 u 8 dígitos)."
)

class Cliente(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="cliente")
    telefono = models.CharField(max_length=20)
    dni = models.CharField(
        max_length=8,
        unique=True,
        validators=[dni_validator],
        default='00000000'
    )
    deuda_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )
    foto_perfil = models.ImageField(
        upload_to='perfiles/',
        null=True,
        blank=True
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

