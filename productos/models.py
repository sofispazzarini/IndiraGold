import uuid
import io
from django.db import models
from decimal import Decimal
# Tipos de medida globales (ej: Largo, Ancho, Circunferencia)
class TipoMedida(models.Model):
    nombre = models.CharField(max_length=50, unique=True)
    descripcion = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre


class Categoria(models.Model):
    nombre = models.CharField(max_length=100)
    activa = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre


class Subcategoria(models.Model):
    nombre = models.CharField(max_length=100)
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE, related_name='subcategorias')
    activa = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nombre} ({self.categoria.nombre})"


class Proveedor(models.Model):
    nombre = models.CharField(max_length=100)
    telefono = models.CharField(max_length=20)
    informacion_adicional = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    TAMANOS_PAQUETE = (
        ('chico', 'Chico - accesorios, remeras, tops'),
        ('mediano', 'Mediano - buzos, pantalones, vestidos'),
        ('grande', 'Grande - camperas, zapatillas, abrigos'),
    )

    codigo = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=150)
    tipo = models.CharField(max_length=150)
    tela = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True, null=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField()
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE)
    subcategoria = models.ForeignKey(Subcategoria, on_delete=models.CASCADE, null=True, blank=True, related_name='productos')
    proveedor = models.ForeignKey(Proveedor, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    temporada = models.CharField(max_length=100, blank=True, null=True)
    avios = models.TextField(blank=True, null=True)
    etiquetas = models.TextField(blank=True, null=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    imagen_tecnica = models.ImageField(upload_to='productos/fichas/', blank=True, null=True)
    tamano_paquete = models.CharField(max_length=20, choices=TAMANOS_PAQUETE, default='mediano')

    @property
    def stock_total(self):
        return self.variantes.filter(activa=True).aggregate(
            total=models.Sum('stock')
        )['total'] or 0

    def __str__(self):
        return self.nombre

    @property
    def imagen(self):
        imagen = self.imagenes.filter(es_portada=True).first() or self.imagenes.first()
        return imagen.imagen if imagen else None

    def obtener_oferta_activa(self):

        oferta_producto = Oferta.objects.filter(
            activa=True,
            es_cupon=False,
            productos=self
        ).first()

        if oferta_producto:
            return oferta_producto

        oferta_categoria = Oferta.objects.filter(
            activa=True,
            es_cupon=False,
            categoria=self.categoria
        ).first()

        if oferta_categoria:
            return oferta_categoria

        oferta_global = Oferta.objects.filter(
            activa=True,
            es_cupon=False,
            aplicar_a_todos=True
        ).first()

        if oferta_global:
            return oferta_global

        return None


    @property
    def precio_final(self):

        oferta = self.obtener_oferta_activa()

        if not oferta:
            return self.precio

        descuento = Decimal(oferta.descuento) / Decimal(100)

        return self.precio * (1 - descuento)
class ImagenProducto(models.Model):
    producto = models.ForeignKey(Producto, related_name='imagenes', on_delete=models.CASCADE)
    imagen = models.ImageField(upload_to='productos/')
    # Opcional: un campo para definir cuál es la principal
    es_portada = models.BooleanField(default=False)
class Talle(models.Model):
    nombre = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre
class Medida(models.Model):
    alto = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    ancho = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    largo = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    tiro = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    detalle_etiqueta = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Info adicional de etiqueta (ej: Prelavado, Tela premium)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Alto: {self.alto} cm, Ancho: {self.ancho} cm, Largo: {self.largo} cm, Tiro: {self.tiro} cm"

class Color(models.Model):
    nombre = models.CharField(max_length=30)
    codigo_hex = models.CharField(max_length=7, default='#888888')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre


class Variante(models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='variantes')
    talle = models.ForeignKey(Talle, on_delete=models.CASCADE)
    colores = models.ManyToManyField(Color, blank=True)
    medidas = models.ManyToManyField(Medida, blank=True)
    stock = models.PositiveIntegerField()
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    activa = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    qr_code = models.CharField(
        max_length=100,
        unique=True
    )
    class Meta:
        unique_together = ('producto', 'talle')

    def __str__(self):
        return f"{self.producto.nombre} - {self.talle}"


class CategoriaOrden(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Categoría de Orden'
        verbose_name_plural = 'Categorías de Orden'

    def __str__(self):
        return self.nombre
class CategoriaOrdenProducto(models.Model):
    categoria_orden = models.ForeignKey(
        CategoriaOrden,
        on_delete=models.CASCADE
    )
    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('categoria_orden', 'producto')

    def __str__(self):
        return f"{self.categoria_orden} - {self.producto}"


class VarianteColor(models.Model):
    """Combinación única de Variante (producto+talle) + Color, con código QR para identificación física."""
    variante = models.ForeignKey(Variante, on_delete=models.CASCADE, related_name='variante_colores')
    color = models.ForeignKey(Color, on_delete=models.CASCADE)
    qr_code = models.CharField(max_length=100, unique=True, blank=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('variante', 'color')
        verbose_name = 'Variante Color'
        verbose_name_plural = 'Variantes Color'

    def save(self, *args, **kwargs):
        if not self.qr_code:
            self.qr_code = str(uuid.uuid4())
        super().save(*args, **kwargs)

    def generar_qr_image(self):
        """Genera imagen QR con información del producto."""
        import qrcode

        data = f"IG-{self.variante.producto.codigo}-{self.variante.talle.nombre}-{self.color.nombre}-{self.qr_code[:8]}"

        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer

    def __str__(self):
        return f"{self.variante.producto.nombre} - {self.variante.talle} - {self.color.nombre}"
class Oferta(models.Model):
    nombre = models.CharField(max_length=100)
    codigo = models.CharField(max_length=40, unique=True, null=True, blank=True)
    es_cupon = models.BooleanField(default=False)

    descuento = models.PositiveIntegerField(
        help_text='Porcentaje de descuento'
    )

    aplicar_a_todos = models.BooleanField(default=False)

    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ofertas'
    )

    productos = models.ManyToManyField(
        Producto,
        blank=True,
        related_name='ofertas'
    )

    activa = models.BooleanField(default=True)

    fecha_inicio = models.DateTimeField(null=True, blank=True)
    fecha_fin = models.DateTimeField(null=True, blank=True)

    # Límite de usos del código
    limite_usos = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Cantidad máxima de veces que se puede usar el código. Dejar vacío para ilimitado.'
    )
    usos_actuales = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    def puede_usarse(self):
        """Verifica si el código todavía puede usarse."""
        from django.utils import timezone

        if not self.activa:
            return False, 'El código no está activo'

        # Verificar fecha límite
        if self.fecha_fin and timezone.now() > self.fecha_fin:
            return False, 'El código ha expirado'

        # Verificar límite de usos
        if self.limite_usos is not None and self.usos_actuales >= self.limite_usos:
            return False, 'El código ha alcanzado el límite de usos'

        return True, None

    def registrar_uso(self):
        """Incrementa el contador de usos."""
        self.usos_actuales += 1
        self.save(update_fields=['usos_actuales'])

    def save(self, *args, **kwargs):
        self.codigo = self.codigo.strip().upper() if self.codigo else None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre} - {self.descuento}%"
