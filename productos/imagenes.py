"""Derivadas WebP versionadas; nunca reemplaza ni elimina el original."""
import hashlib
import logging
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)
TAMANOS = (480, 960, 1600)


def nombre_derivada(archivo, lado):
    clave = hashlib.sha256(archivo.name.encode('utf-8')).hexdigest()
    return f'productos/optimizadas/v1/{clave}-{lado}.webp'


def generar_derivadas(archivo):
    """Genera solo las que faltan, con Storage (también admite almacenamiento remoto)."""
    pendientes = [lado for lado in TAMANOS if not archivo.storage.exists(nombre_derivada(archivo, lado))]
    if not pendientes:
        return 0
    with archivo.storage.open(archivo.name, 'rb') as entrada:
        with Image.open(entrada) as origen:
            # Conserva animaciones en su archivo original.
            if getattr(origen, 'is_animated', False):
                raise ValueError('Imagen animada: se conserva el original sin derivadas.')
            imagen = ImageOps.exif_transpose(origen)
            imagen.load()
            imagen = imagen.convert('RGBA' if 'A' in imagen.getbands() or 'transparency' in imagen.info else 'RGB')
    for lado in pendientes:
        copia = imagen.copy()
        copia.thumbnail((lado, lado), Image.Resampling.LANCZOS)
        salida = BytesIO()
        copia.save(salida, 'WEBP', quality=84, method=4)
        # Storage.save nunca sobrescribe el original. En una carrera puede quedar
        # una copia adicional, pero la URL determinista sigue siendo válida.
        archivo.storage.save(nombre_derivada(archivo, lado), ContentFile(salida.getvalue()))
    return len(pendientes)


def url_imagen(archivo, lado=960):
    if not archivo:
        return ''
    nombre = nombre_derivada(archivo, int(lado))
    try:
        if archivo.storage.exists(nombre):
            return archivo.storage.url(nombre)
    except OSError:
        logger.warning('No se pudo consultar la imagen optimizada; se usa el original.')
    return archivo.url
