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
    METODOS_PAGO = (
        ('efectivo', 'Efectivo'),
        ('mercado_pago', 'Mercado Pago'),
        ('mercado_pago_qr', 'Mercado Pago QR'),
        ('tarjeta', 'Tarjeta'),
        ('transferencia', 'Transferencia bancaria'),
    )
    metodo_entrega = models.CharField(max_length=20, choices=METODOS_ENTREGA, default='local')
    costo_envio = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    codigo_postal = models.CharField(max_length=10, blank=True, null=True)
    localidad = models.CharField(max_length=100, blank=True, null=True)
    calle_numero = models.CharField(max_length=255, blank=True, null=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    codigo_descuento = models.CharField(max_length=40, blank=True, null=True)
    descuento_porcentaje = models.PositiveIntegerField(default=0)
    descuento_monto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tipo_venta = models.CharField(
        max_length=30,
        choices=TIPOS_VENTA
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default='pendiente'
    )
    metodo_pago = models.CharField(max_length=20, choices=METODOS_PAGO, null=True, blank=True)
    monto_pagado = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deuda = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    es_presencial = models.BooleanField(default=False)
    es_regalo = models.BooleanField(default=False)
    fecha_creacion = models.DateTimeField(null=True, blank=True)
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

    sucursal_correo_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text='ID de la sucursal para PAQ.AR'
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
    color_nombre = models.CharField(max_length=100, blank=True, null=True)
    cantidad = models.PositiveIntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    precio_total = models.DecimalField(max_digits=10, decimal_places=2)
    def __str__(self):
        return f"{self.variante.producto.nombre} x {self.cantidad}"


class Pago(models.Model):
    pedido = models.OneToOneField(Pedido, on_delete=models.CASCADE)
    metodo = models.CharField(max_length=50)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    mercado_pago_payment_id = models.CharField(max_length=80, blank=True, null=True)
    cuotas = models.PositiveIntegerField(default=1)
    retencion_mercado_pago = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    neto_recibido = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    detalle_mercado_pago = models.JSONField(default=dict, blank=True)
    fecha_pago = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Pago Pedido {self.pedido.id}"


class PagoPedido(models.Model):
    METODOS_PAGO = (
        ('efectivo', 'Efectivo'),
        ('mercado_pago', 'Mercado Pago'),
        ('tarjeta', 'Tarjeta/Posnet'),
        ('transferencia', 'Transferencia'),
    )
    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        related_name='pagos_registrados'
    )
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo_pago = models.CharField(
        max_length=20,
        choices=METODOS_PAGO,
        default='efectivo'
    )
    observaciones = models.CharField(max_length=255, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha']

    def __str__(self):
        return f"Pago ${self.monto} - Pedido #{self.pedido.id}"


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
    METODOS_PAGO = (
        ('efectivo', 'Efectivo'),
        ('mercado_pago', 'Mercado Pago'),
        ('mercado_pago_qr', 'Mercado Pago QR'),
        ('tarjeta', 'Tarjeta'),
    )
    METODOS_ENTREGA = (
        ('local', 'Retiro en local'),
        ('envio', 'Con envio'),
    )

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
    
    metodo_pago = models.CharField(
        max_length=20,
        choices=METODOS_PAGO,
        default='efectivo'
    )

    metodo_entrega = models.CharField(
        max_length=20,
        choices=METODOS_ENTREGA,
        default='local'
    )

    direccion = models.ForeignKey(
        'users.Direccion',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    es_regalo = models.BooleanField(default=False)
    
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
    correo_activo = models.BooleanField(
        default=False,
        help_text='Mostrar Correo Argentino como opcion en el checkout'
    )

    precio_flex = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    flex_gratis = models.BooleanField(
        default=False
    )
    correo_gratis = models.BooleanField(
        default=False
    )
    correo_a_coordinar = models.BooleanField(
        default=False,
        help_text='Mostrar "A coordinar" en lugar de precio fijo para envío por correo'
    )

    zonas_flex = models.TextField(
        blank=True,
        help_text='Separar zonas con coma. Ej: CABA, La Plata, Quilmes'
    )
    precio_correo = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
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
    def costo_correo(self):
        if self.correo_gratis:
            return 0
        if self.correo_a_coordinar:
            return None
        return self.precio_correo

    @property
    def texto_costo_correo(self):
        if self.correo_gratis:
            return 'Gratis'
        if self.correo_a_coordinar:
            return 'A coordinar'
        return f'${self.precio_correo}'

    @property
    def zonas_flex_lista(self):
        return [
            zona.strip()
            for zona in self.zonas_flex.split(',')
            if zona.strip()
        ]


class EnvioPedido(models.Model):
    PROVEEDORES = (
        ('correo_argentino', 'Correo Argentino'),
        ('flex', 'Envio Flex'),
    )
    TIPOS_ENTREGA = (
        ('domicilio', 'A domicilio'),
        ('sucursal', 'Retiro en sucursal'),
    )
    ESTADOS = (
        ('pendiente', 'Pendiente de generar etiqueta'),
        ('etiqueta_generada', 'Etiqueta generada'),
        ('despachado', 'Despachado'),
        ('en_transito', 'En transito'),
        ('entregado', 'Entregado'),
        ('error', 'Error al generar envio'),
    )

    pedido = models.OneToOneField(
        Pedido,
        on_delete=models.CASCADE,
        related_name='envio'
    )
    proveedor = models.CharField(max_length=30, choices=PROVEEDORES)
    tipo_entrega = models.CharField(max_length=20, choices=TIPOS_ENTREGA, default='domicilio')
    estado = models.CharField(max_length=30, choices=ESTADOS, default='pendiente')
    costo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tracking = models.CharField(max_length=120, blank=True, null=True)
    sucursal = models.CharField(max_length=255, blank=True, null=True)
    sucursal_id = models.CharField(max_length=50, blank=True, null=True, help_text='ID de sucursal para PAQ.AR')
    etiqueta = models.FileField(upload_to='etiquetas_envio/', blank=True, null=True)
    respuesta_api = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Envio Pedido {self.pedido_id} - {self.get_proveedor_display()}"


class ConfiguracionPago(models.Model):
    mercado_pago_activo = models.BooleanField(default=True)
    transferencia_activa = models.BooleanField(default=True)
    titular_cuenta = models.CharField(max_length=150, default='Yazmin Miranda Capitanio')
    cuit_cuil = models.CharField(max_length=30, default='27-39554727-0')
    cvu = models.CharField(max_length=60, default='0000003100042870767609')
    alias = models.CharField(max_length=80, default='indiragold.')
    texto_mercado_pago = models.CharField(
        max_length=255,
        default='Podes pagar con dinero en cuenta, tarjeta de debito o credito desde Mercado Pago.'
    )
    texto_transferencia = models.CharField(
        max_length=255,
        default='Transferi el monto exacto y envianos el comprobante por WhatsApp.'
    )

    def __str__(self):
        return "Configuracion de Pagos"

    @classmethod
    def actual(cls):
        configuracion, _ = cls.objects.get_or_create(pk=1)
        return configuracion


class PlanCuotasMercadoPago(models.Model):
    configuracion = models.ForeignKey(
        ConfiguracionPago,
        on_delete=models.CASCADE,
        related_name='planes_cuotas'
    )
    cuotas = models.PositiveIntegerField()
    sin_interes = models.BooleanField(default=True)
    retencion_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    activo = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['orden', 'cuotas']

    def __str__(self):
        tipo = "sin interes" if self.sin_interes else "con interes"
        return f"Hasta {self.cuotas} cuotas {tipo}"
