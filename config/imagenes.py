"""Validación y optimización de imágenes grandes que sube el admin (slides del carrousel, fondo del hero)."""
import os
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

FORMATOS_IMAGEN = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}
IMAGEN_MAX_MB = 5
# Ancho de sobra para pantallas grandes; más que esto solo hace pesada la home
IMAGEN_MAX_LADO = 2400


def optimizar_imagen(archivo, max_mb=IMAGEN_MAX_MB, max_lado=IMAGEN_MAX_LADO):
    """Valida que sea una imagen JPG/PNG/WEBP real de hasta max_mb y la achica a max_lado px.
    Devuelve (archivo_listo, None) o (None, mensaje_de_error)."""
    if archivo.size > max_mb * 1024 * 1024:
        return None, f'La imagen no puede pesar más de {max_mb:g} MB.'
    try:
        imagen = Image.open(archivo)
        imagen.verify()
        archivo.seek(0)
        imagen = Image.open(archivo)
        formato = imagen.format
        imagen.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None, 'La imagen tiene que ser un archivo JPG, PNG o WEBP.'
    if formato not in FORMATOS_IMAGEN:
        return None, 'La imagen tiene que ser un archivo JPG, PNG o WEBP.'

    # Respeta la orientación de las fotos de celular antes de achicar
    imagen = ImageOps.exif_transpose(imagen)
    imagen.thumbnail((max_lado, max_lado))
    if formato == 'JPEG' and imagen.mode not in ('RGB', 'L'):
        imagen = imagen.convert('RGB')
    salida = BytesIO()
    imagen.save(salida, format=formato, quality=85, optimize=True)
    nombre = os.path.splitext(os.path.basename(archivo.name or 'imagen'))[0] or 'imagen'
    return ContentFile(salida.getvalue(), name=f'{nombre}.{FORMATOS_IMAGEN[formato]}'), None
