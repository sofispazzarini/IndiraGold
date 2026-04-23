from django.db import models
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
    def __str__(self):
        return self.nombre
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
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Alto: {self.alto} cm, Ancho: {self.ancho} cm, Largo: {self.largo} cm, Tiro: {self.tiro} cm"

class Color(models.Model):
    nombre = models.CharField(max_length=30)
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
    created_at = models.DateTimeField(auto_now_add=True)

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
