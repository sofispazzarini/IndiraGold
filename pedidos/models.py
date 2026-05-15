from django.db import models
from users.models import Cliente
from productos.models import Producto
from productos.models import Variante


class Pedido(models.Model):
    ESTADOS = (
        ('pendiente', 'Pendiente de confirmación'),
        ('aceptado', 'Pago aceptado'),

        ('en_preparacion', 'En preparación'),

        # retiro local
        ('listo_retirar', 'Listo para retirar'),

        # envío
        ('preparando_envio', 'Preparando envío'),
        ('enviado', 'Paquete enviado'),

        ('entregado', 'Entregado'),

        ('rechazado', 'Pago rechazado'),
        ('cancelado', 'Cancelado'),
        ('vencido', 'Vencido'),
    )
    TRANSICIONES = {

        'pendiente': [
            'aceptado',
            'rechazado'
        ],

        'aceptado': [
            'en_preparacion'
        ],

        'en_preparacion': [
            'listo_retirar',
            'preparando_envio'
        ],

        'preparando_envio': [
            'enviado'
        ],

        'enviado': [
            'entregado'
        ],

        'listo_retirar': [
            'entregado'
        ],
    }
    TIPOS_VENTA = (
        ('online', 'Online'),
        ('presencial', 'Presencial'),
        ('encargo', 'Encargo'),
    )
    METODOS_ENTREGA = (
        ('local', 'Retiro en Local (Gratis)'),
        ('flex', 'Envio Flex'),
        ('correo', 'Envio por Correo'),
    )
    metodo_entrega = models.CharField(max_length=20, choices=METODOS_ENTREGA, default='local')
    costo_envio = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    codigo_postal = models.CharField(max_length=10, blank=True, null=True)
    localidad = models.CharField(max_length=100, blank=True, null=True)
    calle_numero = models.CharField(max_length=255, blank=True, null=True)
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
    correo = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )

    tipo_correo = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    sucursal_correo = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    direccion = models.ForeignKey(
        'users.Direccion',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
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
ESTADOS_PAGO = [
    ("PAGADO", "Pagado"),
    ("PARCIAL", "Parcial"),
]
class VentaLocal(models.Model):

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name='ventas_local'
    )

    total = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )
    total = models.DecimalField(max_digits=10, decimal_places=2)

    monto_pagado = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    saldo_pendiente = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    estado_pago = models.CharField(
        max_length=20,
        choices=ESTADOS_PAGO,
        default="PAGADO"
    )
    def __str__(self):

        return f"Venta #{self.id}"


class VentaLocalItem(models.Model):

    venta = models.ForeignKey(
        VentaLocal,
        on_delete=models.CASCADE,
        related_name='items'
    )

    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE
    )

    variante = models.ForeignKey(
        Variante,
        on_delete=models.CASCADE
    )

    color = models.CharField(
        max_length=100
    )

    cantidad = models.PositiveIntegerField()

    precio_unitario = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    def __str__(self):

        return f"{self.producto.nombre} x{self.cantidad}"
class PagoVentaLocal(models.Model):

    venta = models.ForeignKey(
        VentaLocal,
        on_delete=models.CASCADE,
        related_name="pagos"
    )

    monto = models.DecimalField(max_digits=10, decimal_places=2)

    fecha = models.DateTimeField(auto_now_add=True)
class ConfiguracionEnvio(models.Model):
    flex_activo = models.BooleanField(
        default=True,
        help_text='Mostrar Envio Flex como opcion en el checkout'
    )

    precio_flex = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    flex_gratis = models.BooleanField(
        default=False
    )

    zonas_flex = models.TextField(
        blank=True,
        help_text='Separar zonas con coma. Ej: CABA, La Plata, Quilmes'
    )

    def __str__(self):
        return "Configuracion de Envios"

    @classmethod
    def actual(cls):
        configuracion, _ = cls.objects.get_or_create(pk=1)
        return configuracion

    @property
    def costo_flex(self):
        if self.flex_gratis:
            return 0
        return self.precio_flex

    @property
    def zonas_flex_lista(self):
        return [
            zona.strip()
            for zona in self.zonas_flex.split(',')
            if zona.strip()
        ]
