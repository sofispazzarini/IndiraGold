"""
Códigos automáticos de producto: ART-0001, ART-0002, ...

- El número sale de un contador (SecuenciaCodigoProducto) que se lee y se actualiza con su fila
  bloqueada (SELECT ... FOR UPDATE) dentro de la misma transacción que guarda el producto. Dos altas
  simultáneas se atienden de a una y nunca reciben el mismo número (PostgreSQL y MySQL/InnoDB).
- El contador solo avanza: los códigos de productos borrados no se vuelven a usar.
- Si ya hay códigos ART-XXXX cargados (por ejemplo a mano), se sigue desde el mayor.
- Si el guardado falla, la transacción se deshace y el número no se consume. Abrir o cancelar el
  formulario no toca el contador: el código se asigna recién al guardar.
- La restricción unique de Producto.codigo sigue siendo la última garantía.
"""
import re

from django.db import transaction

PREFIJO = 'ART-'
NOMBRE_SECUENCIA = 'producto'
PATRON_CODIGO = re.compile(r'^ART-(\d+)$', re.IGNORECASE)


def formatear_codigo(numero):
    return f'{PREFIJO}{numero:04d}'


def mayor_numero_existente(codigos):
    """Mayor número entre los códigos con formato ART-<número>; los demás formatos no cuentan."""
    numeros = []
    for codigo in codigos:
        coincidencia = PATRON_CODIGO.match((codigo or '').strip())
        if coincidencia:
            numeros.append(int(coincidencia.group(1)))
    return max(numeros, default=0)


def codigo_en_uso(codigo):
    from .models import Producto
    return Producto.objects.filter(codigo__iexact=codigo).exists()


def siguiente_codigo_producto():
    """Reserva y devuelve el próximo código. Se llama dentro de la transacción que guarda el producto:
    el contador queda bloqueado hasta que esa transacción termina."""
    from .models import Producto, SecuenciaCodigoProducto

    with transaction.atomic():
        secuencia, _ = SecuenciaCodigoProducto.objects.get_or_create(nombre=NOMBRE_SECUENCIA)
        secuencia = SecuenciaCodigoProducto.objects.select_for_update().get(pk=secuencia.pk)

        # El contador (leído con la fila bloqueada) manda; los códigos ART existentes solo pueden
        # adelantarlo, nunca hacerlo volver atrás
        existentes = Producto.objects.filter(codigo__istartswith=PREFIJO).values_list('codigo', flat=True)
        numero = max(secuencia.ultimo_numero, mayor_numero_existente(existentes)) + 1
        while codigo_en_uso(formatear_codigo(numero)):
            numero += 1

        secuencia.ultimo_numero = numero
        secuencia.save(update_fields=['ultimo_numero'])
    return formatear_codigo(numero)
