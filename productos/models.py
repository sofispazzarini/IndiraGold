import uuid
import io
from urllib.parse import urlencode, urlparse

from django.conf import settings
from django.urls import reverse
from django.db import models, transaction
from django.core.validators import MinValueValidator
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
    precio = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'), message='El precio tiene que ser mayor a 0.')],
    )
    stock = models.PositiveIntegerField()
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE)
    # PROTECT: borrar una subcategoría o un proveedor no puede borrar sus productos
    subcategoria = models.ForeignKey(Subcategoria, on_delete=models.PROTECT, null=True, blank=True, related_name='productos')
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    temporada = models.CharField(max_length=100, blank=True, null=True)
    avios = models.TextField(blank=True, null=True)
    etiquetas = models.TextField(blank=True, null=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    imagen_tecnica = models.ImageField(upload_to='productos/fichas/', blank=True, null=True)
    tamano_paquete = models.CharField(max_length=20, choices=TAMANOS_PAQUETE, default='mediano')

    def save(self, *args, **kwargs):
        # Producto nuevo sin código: se le asigna el siguiente ART-XXXX al guardarlo, en la misma
        # transacción (si el guardado falla, el número no se consume). Después el código no cambia.
        if self._state.adding and not (self.codigo or '').strip():
            from .codigos import siguiente_codigo_producto
            with transaction.atomic():
                self.codigo = siguiente_codigo_producto()
                super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)

    @property
    def stock_total(self):
        """Stock vendible: por cada talle activo, la suma de sus colores si tiene stock por
        color (VarianteColor) o, si no, el stock del talle."""
        total = 0
        for variante in self.variantes.filter(activa=True).prefetch_related('variante_colores'):
            colores = [vc for vc in variante.variante_colores.all() if vc.activo]
            total += sum(vc.stock for vc in colores) if colores else variante.stock
        return total

    def __str__(self):
        return self.nombre

    @property
    def imagen(self):
        imagen = self.imagenes.filter(es_portada=True).first() or self.imagenes.first()
        return imagen.imagen if imagen else None

    def _operacion_activa(self, tipo):
        """Oferta de catálogo activa de un tipo ('descuento' o 'aumento'), sin cupones.
        Prioridad: la del producto, después la de su categoría, después la global; dentro de
        cada nivel gana la más nueva. Nunca se suman dos operaciones del mismo tipo."""
        cache = self.__dict__.setdefault('_operaciones_activas', {})
        if tipo in cache:
            return cache[tipo]

        activas = Oferta.objects.filter(activa=True, es_cupon=False, tipo=tipo).order_by('-id')
        oferta = (
            activas.filter(productos=self).first()
            or activas.filter(categoria=self.categoria_id).first()
            or activas.filter(aplicar_a_todos=True).first()
        )
        cache[tipo] = oferta
        return oferta

    def obtener_oferta_activa(self):
        """Descuento activo: lo único que se muestra como oferta. Un aumento no es oferta."""
        return self._operacion_activa(Oferta.TIPO_DESCUENTO)

    def obtener_aumento_activo(self):
        return self._operacion_activa(Oferta.TIPO_AUMENTO)

    def calcular_precio(self, precio_base, con_descuento=True):
        """Precio que se cobra a partir de un precio base: primero el aumento y, sobre ese
        precio, el descuento. Es el único lugar donde se aplican los porcentajes."""
        precio = Decimal(precio_base or 0)
        aumento = self.obtener_aumento_activo()
        if aumento:
            precio = (precio * (1 + Decimal(aumento.descuento) / Decimal(100))).quantize(Decimal('0.01'))
        oferta = self.obtener_oferta_activa() if con_descuento else None
        if oferta:
            precio = (precio * (1 - Decimal(oferta.descuento) / Decimal(100))).quantize(Decimal('0.01'))
        return precio

    @property
    def precio_lista(self):
        """Precio normal que ve el cliente: el cargado más el aumento activo (sin descuento).
        Es el que aparece tachado cuando hay oferta."""
        return self.calcular_precio(self.precio, con_descuento=False)

    @property
    def precio_final(self):
        return self.calcular_precio(self.precio)


class ImagenProducto(models.Model):
    producto = models.ForeignKey(Producto, related_name='imagenes', on_delete=models.CASCADE)
    imagen = models.ImageField(upload_to='productos/')
    # Opcional: un campo para definir cuál es la principal
    es_portada = models.BooleanField(default=False)
ORDEN_TALLES_LETRA = ['XXXS', 'XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL', '4XL', '5XL', '6XL']


def orden_talle(nombre):
    """Clave para ordenar talles de forma lógica: letras de chico a grande (XXS→5XL), después números
    de menor a mayor y al final el resto (Único, etc.). Antes se ordenaban alfabéticamente."""
    texto = (nombre or '').strip().upper()
    if texto in ORDEN_TALLES_LETRA:
        return (0, ORDEN_TALLES_LETRA.index(texto), '')
    try:
        return (1, float(texto.replace(',', '.')), '')
    except ValueError:
        return (2, 0, texto)


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


class SecuenciaCodigoProducto(models.Model):
    """Último número usado en los códigos automáticos de producto (ART-0001...). Una sola fila; se
    bloquea al asignar cada código y solo avanza (ver productos/codigos.py). No editar a mano."""
    id = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=30, unique=True)
    ultimo_numero = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Secuencia de códigos de producto'
        verbose_name_plural = 'Secuencias de códigos de producto'

    def __str__(self):
        return f'{self.nombre}: {self.ultimo_numero}'


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
        unique=True,
        blank=True
    )
    class Meta:
        unique_together = ('producto', 'talle')

    def save(self, *args, **kwargs):
        creando = self.pk is None
        qr_original = self.qr_code

        if creando and not self.qr_code:
            self.qr_code = f'__TMP_{uuid.uuid4().hex[:12].upper()}'

        if not creando and not self.qr_code:
            codigo_existente = type(self).objects.filter(pk=self.pk).values_list('qr_code', flat=True).first()
            if codigo_existente:
                self.qr_code = codigo_existente

        if not self.qr_code:
            self.qr_code = str(uuid.uuid4())
        super().save(*args, **kwargs)

        if creando and not qr_original:
            qr_final = f'VAR-{self.pk:04d}'
            if self.qr_code != qr_final:
                self.qr_code = qr_final
                super().save(update_fields=['qr_code'])

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
    """Combinación única de Variante (producto+talle) + Color, con código QR y stock individual."""
    variante = models.ForeignKey(Variante, on_delete=models.CASCADE, related_name='variante_colores')
    color = models.ForeignKey(Color, on_delete=models.CASCADE)
    stock = models.PositiveIntegerField(default=0)
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

    def obtener_url_publica(self):
        site_url = (getattr(settings, 'SITE_URL', '') or '').strip().rstrip('/')
        hostname = urlparse(site_url).hostname if site_url else ''
        if not site_url or hostname in ('localhost', '127.0.0.1'):
            site_url = 'https://www.indiragold.com.ar'
        return f"{site_url}{reverse('productos:detalle_producto', args=[self.variante.producto_id])}?{urlencode({'qr': self.qr_code})}"

    def generar_qr_image(self):
        """Genera imagen QR con información del producto."""
        import qrcode

        data = self.obtener_url_publica()

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
    TIPO_DESCUENTO = 'descuento'
    TIPO_AUMENTO = 'aumento'
    TIPOS = (
        (TIPO_DESCUENTO, 'Descuento'),
        (TIPO_AUMENTO, 'Aumento'),
    )

    nombre = models.CharField(max_length=100)
    codigo = models.CharField(max_length=40, unique=True, null=True, blank=True)
    es_cupon = models.BooleanField(default=False)

    # Un aumento sube el precio y no es oferta (sin etiqueta, sin tachado, fuera de la sección
    # Ofertas). Los cupones son siempre descuentos.
    tipo = models.CharField(max_length=10, choices=TIPOS, default=TIPO_DESCUENTO)

    descuento = models.PositiveIntegerField(
        help_text='Porcentaje de descuento o de aumento, según el tipo'
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
        """Incrementa el contador de usos (con F() para no perder usos simultáneos)."""
        Oferta.objects.filter(pk=self.pk).update(usos_actuales=models.F('usos_actuales') + 1)
        self.refresh_from_db(fields=['usos_actuales'])

    @property
    def estado_texto(self):
        """Estado para el admin: Vencida / Agotada / Activa / Pausada."""
        from django.utils import timezone

        if self.fecha_fin and timezone.now() > self.fecha_fin:
            return 'Vencida'
        if self.limite_usos is not None and self.usos_actuales >= self.limite_usos:
            return 'Agotada'
        return 'Activa' if self.activa else 'Pausada'

    def save(self, *args, **kwargs):
        self.codigo = self.codigo.strip().upper() if self.codigo else None
        super().save(*args, **kwargs)

    @property
    def es_aumento(self):
        return self.tipo == self.TIPO_AUMENTO

    def __str__(self):
        signo = '+' if self.es_aumento else '-'
        return f"{self.nombre} {signo}{self.descuento}%"
