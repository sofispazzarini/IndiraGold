from django.contrib import admin
from .models import Pedido, PedidoItem, Pago, Gasto

admin.site.register(Pedido)
admin.site.register(PedidoItem)
admin.site.register(Pago)
admin.site.register(Gasto)
