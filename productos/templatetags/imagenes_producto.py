from django import template
from productos.imagenes import url_imagen

register = template.Library()
register.filter('imagen_optimizada', url_imagen)
