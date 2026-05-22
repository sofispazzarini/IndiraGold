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
    etiqueta = models.CharField(max_length=50, default='Casa')
    calle = models.CharField(max_length=100)
    numero = models.CharField(max_length=10)
    ciudad = models.CharField(max_length=50)
    provincia = models.CharField(max_length=50)
    codigo_postal = models.CharField(max_length=10)
    referencia = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.etiqueta}: {self.calle} {self.numero}"

    @staticmethod
    def clave_unica(etiqueta, calle, numero, ciudad, provincia, codigo_postal, referencia=""):
        valores = [etiqueta, calle, numero, ciudad, provincia, codigo_postal, referencia]
        return tuple(" ".join(str(valor or "").strip().casefold().split()) for valor in valores)

    @property
    def clave_normalizada(self):
        return self.clave_unica(
            self.etiqueta,
            self.calle,
            self.numero,
            self.ciudad,
            self.provincia,
            self.codigo_postal,
            self.referencia,
        )


def direcciones_sin_duplicados(direcciones):
    resultado = []
    vistas = set()
    for direccion in direcciones:
        clave = direccion.clave_normalizada
        if clave in vistas:
            continue
        vistas.add(clave)
        resultado.append(direccion)
    return resultado
#Django maneja:
#username
#password
#email
#login
#permisos
#se llama auth_user la tabla, no se ve, viene instalada dentro de django

