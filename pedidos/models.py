from django.db import models
from users.models import Cliente
from productos.models import Producto
from productos.models import Variante


class Pedido(models.Model):
    ESTADOS = (
        ('pendiente', 'Pendiente'),
        ('aceptado', 'Aceptado'),
        ('en_preparacion', 'En preparación'),
        ('enviado', 'Enviado'),
        ('entregado', 'Entregado'),
        ('cancelado', 'Cancelado'),
        ('vencido', 'Vencido'),
    )
    TIPOS_VENTA = (
        ('online', 'Online'),
        ('presencial', 'Presencial'),
        ('encargo', 'Encargo'),
    )
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    tipo_venta = models.CharField(
        max_length=30,
        choices=TIPOS_VENTA
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default='pendiente'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    direccion_info = models.TextField(blank=True, null=True, help_text="Información de dirección del envío")

    def __str__(self):
        return f"Pedido {self.id}"


class PedidoItem(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='items')
    variante = models.ForeignKey(Variante, on_delete=models.CASCADE)
    cantidad = models.PositiveIntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    precio_total = models.DecimalField(max_digits=10, decimal_places=2)
    def __str__(self):
        return f"{self.variante.producto.nombre} x {self.cantidad}"


class Pago(models.Model):
    pedido = models.OneToOneField(Pedido, on_delete=models.CASCADE)
    metodo = models.CharField(max_length=50)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_pago = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Pago Pedido {self.pedido.id}"

class Gasto(models.Model):
    descripcion = models.CharField(max_length=200)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    fecha = models.DateField()
    observaciones = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.descripcion} - ${self.monto}"
