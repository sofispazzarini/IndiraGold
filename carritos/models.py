from django.db import models
from django.utils import timezone
from datetime import timedelta
from users.models import Cliente
from productos.models import Producto
from productos.models import Variante



class Carrito(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, blank=True, null=True)
    session_id = models.CharField(max_length=64, blank=True, null=True, help_text="ID de sesión para carritos de invitados")
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def total_carrito(self):
        return sum(item.precio_total for item in self.items.all())

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=1)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Carrito {self.id} - {self.cliente}"


class CarritoItem(models.Model):
    carrito = models.ForeignKey(Carrito, on_delete=models.CASCADE, related_name='items')
    variante = models.ForeignKey(Variante, on_delete=models.CASCADE)
    cantidad = models.PositiveIntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    precio_total = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.variante} x {self.cantidad}"
    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario