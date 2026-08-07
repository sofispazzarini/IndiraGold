import sys
sys.path.insert(0, '.')
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IndiraGold.settings')
import django
django.setup()

from pedidos.models import VentaLocal, VentaLocalItem
from decimal import Decimal

# Obtener todas las ventas con total 0
ventas = VentaLocal.objects.filter(total=0)
print(f'Ventas con total 0: {ventas.count()}')

for venta in ventas:
    total = Decimal(0)
    for item in venta.items.all():
        variante = item.variante
        producto = variante.producto

        # Calcular precio correcto
        precio_base = variante.precio if variante.precio > 0 else producto.precio

        # Aplicar descuento si hay oferta
        oferta = producto.obtener_oferta_activa()
        if oferta:
            descuento = Decimal(oferta.descuento) / Decimal(100)
            precio_unitario = precio_base * (1 - descuento)
        else:
            precio_unitario = precio_base

        subtotal = precio_unitario * item.cantidad

        # Actualizar item
        item.precio_unitario = precio_unitario
        item.subtotal = subtotal
        item.save()

        total += subtotal
        print(f'  Item: {producto.nombre}, Precio: {precio_unitario}, Subtotal: {subtotal}')

    # Actualizar venta
    venta.total = total
    venta.monto_pagado = total - venta.saldo_pendiente
    venta.save()
    print(f'Venta {venta.id} actualizada: Total={total}, Pagado={venta.monto_pagado}')

print('Done!')
