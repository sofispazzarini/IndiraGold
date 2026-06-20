import random
import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from pedidos.models import (
    Gasto,
    PagoPedido,
    Pedido,
    PedidoItem,
    PagoVentaLocal,
    VentaLocal,
    VentaLocalItem,
)
from productos.models import (
    Categoria,
    Color,
    Producto,
    Proveedor,
    Subcategoria,
    Talle,
    Variante,
)
from users.models import Cliente, Direccion

DEMO_DNIS = ["30000001", "30000002", "30000003"]
DEMO_CODES = ["DEMO-001", "DEMO-002", "DEMO-003", "DEMO-004", "DEMO-005", "DEMO-006"]
DEMO_MARKER = "##DEMO##"


class Command(BaseCommand):
    help = "Carga datos demo para IndiraGold. Usa --delete para eliminar solo los datos demo."

    def add_arguments(self, parser):
        parser.add_argument(
            '--delete',
            action='store_true',
            help='Elimina solo los datos marcados como DEMO',
        )

    def handle(self, *args, **options):
        if options['delete']:
            self.delete_demo_data()
        else:
            self.create_demo_data()

    @transaction.atomic
    def delete_demo_data(self):
        self.stdout.write(self.style.WARNING("\n--- Eliminando datos DEMO ---\n"))

        PagoVentaLocal.objects.filter(venta__cliente__dni__in=DEMO_DNIS).delete()
        VentaLocalItem.objects.filter(venta__cliente__dni__in=DEMO_DNIS).delete()
        VentaLocal.objects.filter(cliente__dni__in=DEMO_DNIS).delete()

        PagoPedido.objects.filter(pedido__cliente__dni__in=DEMO_DNIS).delete()
        PedidoItem.objects.filter(pedido__cliente__dni__in=DEMO_DNIS).delete()
        Pedido.objects.filter(cliente__dni__in=DEMO_DNIS).delete()

        gastos_deleted = Gasto.objects.filter(observaciones__contains=DEMO_MARKER).delete()[0]

        Variante.objects.filter(producto__codigo__in=DEMO_CODES).delete()
        productos_deleted = Producto.objects.filter(codigo__in=DEMO_CODES).delete()[0]

        Subcategoria.objects.filter(categoria__nombre="Calzado Demo").delete()
        Subcategoria.objects.filter(categoria__nombre="Accesorios Demo").delete()
        Categoria.objects.filter(nombre__in=["Calzado Demo", "Accesorios Demo"]).delete()
        Proveedor.objects.filter(telefono="1155550000").delete()

        Direccion.objects.filter(cliente__dni__in=DEMO_DNIS).delete()
        clientes_demo = Cliente.objects.filter(dni__in=DEMO_DNIS)
        users_to_delete = [c.user for c in clientes_demo]
        clientes_demo.delete()
        for user in users_to_delete:
            user.delete()

        self.stdout.write(self.style.SUCCESS(f"Productos eliminados: {productos_deleted}"))
        self.stdout.write(self.style.SUCCESS(f"Gastos eliminados: {gastos_deleted}"))
        self.stdout.write(self.style.SUCCESS("\n--- DATOS DEMO ELIMINADOS ---\n"))

    @transaction.atomic
    def create_demo_data(self):
        random.seed(42)
        now = timezone.now()

        self.stdout.write(self.style.WARNING("\n--- Creando datos DEMO ---\n"))

        if Producto.objects.filter(codigo__in=DEMO_CODES).exists():
            self.stdout.write(self.style.ERROR("Ya existen datos DEMO. Usa --delete primero."))
            return

        proveedor = Proveedor.objects.create(
            nombre="Distribuidora Sur",
            telefono="1155550000",
            informacion_adicional="Proveedor mayorista zona sur",
        )
        self.stdout.write(f"  Proveedor creado: {proveedor.nombre}")

        cat_calzado = Categoria.objects.create(nombre="Calzado Demo", activa=True)
        cat_accesorios = Categoria.objects.create(nombre="Accesorios Demo", activa=True)

        sub_botas = Subcategoria.objects.create(nombre="Botas", categoria=cat_calzado, activa=True)
        sub_sandalias = Subcategoria.objects.create(nombre="Sandalias", categoria=cat_calzado, activa=True)
        sub_carteras = Subcategoria.objects.create(nombre="Carteras", categoria=cat_accesorios, activa=True)
        sub_cinturones = Subcategoria.objects.create(nombre="Cinturones", categoria=cat_accesorios, activa=True)
        self.stdout.write(f"  Categorías creadas: Calzado, Accesorios")

        talles_calzado = []
        for t in ["36", "37", "38", "39", "40"]:
            talle, _ = Talle.objects.get_or_create(nombre=t)
            talles_calzado.append(talle)

        talle_unico, _ = Talle.objects.get_or_create(nombre="Único")

        colores = []
        for c in ["Negro", "Marrón", "Beige", "Blanco"]:
            color, _ = Color.objects.get_or_create(nombre=c)
            colores.append(color)

        productos_data = [
            {"nombre": "Bota Génesis", "codigo": "DEMO-001", "tipo": "Bota caña alta", "tela": "Cuero sintético", "precio": 45000, "sub": sub_botas, "talles": talles_calzado},
            {"nombre": "Bota Luna", "codigo": "DEMO-002", "tipo": "Bota corta", "tela": "Eco cuero", "precio": 38000, "sub": sub_botas, "talles": talles_calzado},
            {"nombre": "Sandalia Sol", "codigo": "DEMO-003", "tipo": "Sandalia plana", "tela": "Cuero", "precio": 28000, "sub": sub_sandalias, "talles": talles_calzado},
            {"nombre": "Cartera Mía", "codigo": "DEMO-004", "tipo": "Cartera mediana", "tela": "Eco cuero", "precio": 32000, "sub": sub_carteras, "talles": [talle_unico]},
            {"nombre": "Cartera Mini", "codigo": "DEMO-005", "tipo": "Cartera pequeña", "tela": "Cuero sintético", "precio": 22000, "sub": sub_carteras, "talles": [talle_unico]},
            {"nombre": "Cinturón Classic", "codigo": "DEMO-006", "tipo": "Cinturón ancho", "tela": "Cuero", "precio": 15000, "sub": sub_cinturones, "talles": [talle_unico]},
        ]

        productos = []
        for data in productos_data:
            producto = Producto.objects.create(
                codigo=data["codigo"],
                nombre=data["nombre"],
                tipo=data["tipo"],
                tela=data["tela"],
                descripcion=f"Producto de alta calidad - {data['tipo']}",
                precio=Decimal(str(data["precio"])),
                stock=0,
                categoria=data["sub"].categoria,
                subcategoria=data["sub"],
                proveedor=proveedor,
                temporada="Otoño-Invierno 2026",
                activo=True,
            )

            total_stock = 0
            for talle in data["talles"]:
                stock = random.randint(3, 10)
                total_stock += stock
                variante = Variante.objects.create(
                    producto=producto,
                    talle=talle,
                    precio=producto.precio,
                    stock=stock,
                    activa=True,
                    qr_code=f"{producto.codigo}-{talle.nombre}-{uuid.uuid4().hex[:6]}",
                )
                variante.colores.set(random.sample(colores, random.randint(2, 4)))

            producto.stock = total_stock
            producto.save(update_fields=["stock"])
            productos.append(producto)

        self.stdout.write(f"  Productos creados: {len(productos)}")

        clientes_data = [
            {"first": "María", "last": "García", "dni": "30000001", "tel": "1155551001"},
            {"first": "Laura", "last": "Rodríguez", "dni": "30000002", "tel": "1155551002"},
            {"first": "Ana", "last": "Martínez", "dni": "30000003", "tel": "1155551003"},
        ]

        clientes = []
        for cd in clientes_data:
            user = User.objects.create_user(
                username=cd["dni"],
                email=f"cliente{cd['dni'][-2:]}@email.com",
                password=cd["dni"],
                first_name=cd["first"],
                last_name=cd["last"],
            )
            cliente = Cliente.objects.create(user=user, dni=cd["dni"], telefono=cd["tel"])
            Direccion.objects.create(
                cliente=cliente,
                etiqueta="Casa",
                calle="Calle 50",
                numero="1234",
                ciudad="La Plata",
                provincia="Buenos Aires",
                codigo_postal="1900",
            )
            clientes.append(cliente)

        self.stdout.write(f"  Clientes creados: {len(clientes)}")

        estados = ["entregado", "entregado", "entregado", "en_preparacion", "pendiente"]
        metodos_pago = ["efectivo", "tarjeta", "mercado_pago", "transferencia"]
        pedidos_creados = 0

        for i, cliente in enumerate(clientes):
            for j in range(2):
                estado = estados[(i + j) % len(estados)]
                dias_atras = random.randint(1, 25)
                fecha = now - timedelta(days=dias_atras)

                variantes_pedido = random.sample(list(Variante.objects.filter(producto__codigo__in=DEMO_CODES)), 2)
                total = sum(v.precio for v in variantes_pedido)
                monto_pagado = total if estado == "entregado" else Decimal("0")

                pedido = Pedido.objects.create(
                    cliente=cliente,
                    total=total,
                    tipo_venta="online",
                    estado=estado,
                    metodo_pago=random.choice(metodos_pago),
                    metodo_entrega="local",
                    monto_pagado=monto_pagado,
                    deuda=total - monto_pagado,
                    fecha_creacion=fecha,
                )
                pedido.created_at = fecha
                pedido.save(update_fields=["created_at"])

                for variante in variantes_pedido:
                    PedidoItem.objects.create(
                        pedido=pedido,
                        variante=variante,
                        cantidad=1,
                        precio_unitario=variante.precio,
                        precio_total=variante.precio,
                    )

                if estado == "entregado":
                    PagoPedido.objects.create(
                        pedido=pedido,
                        monto=total,
                        metodo_pago=random.choice(["efectivo", "tarjeta"]),
                    )

                pedidos_creados += 1

        self.stdout.write(f"  Pedidos creados: {pedidos_creados}")

        ventas_data = [
            {"dias": 1, "metodo": "efectivo"},
            {"dias": 2, "metodo": "tarjeta"},
            {"dias": 3, "metodo": "mercado_pago"},
            {"dias": 5, "metodo": "efectivo"},
            {"dias": 7, "metodo": "tarjeta"},
            {"dias": 10, "metodo": "efectivo"},
            {"dias": 15, "metodo": "mercado_pago"},
            {"dias": 20, "metodo": "tarjeta"},
        ]

        ventas_creadas = 0
        for i, vd in enumerate(ventas_data):
            cliente = clientes[i % len(clientes)]
            fecha = now - timedelta(days=vd["dias"])

            variantes_venta = random.sample(list(Variante.objects.filter(producto__codigo__in=DEMO_CODES)), random.randint(1, 3))
            total = sum(v.precio for v in variantes_venta)

            venta = VentaLocal.objects.create(
                cliente=cliente,
                total=total,
                monto_pagado=total,
                saldo_pendiente=Decimal("0"),
                estado_pago="PAGADO",
                metodo_pago=vd["metodo"],
                metodo_entrega="local",
            )
            venta.created_at = fecha
            venta.save(update_fields=["created_at"])

            for variante in variantes_venta:
                color = variante.colores.first()
                VentaLocalItem.objects.create(
                    venta=venta,
                    producto=variante.producto,
                    variante=variante,
                    color=color.nombre if color else "Sin color",
                    cantidad=1,
                    precio_unitario=variante.precio,
                    subtotal=variante.precio,
                )

            PagoVentaLocal.objects.create(venta=venta, monto=total)
            ventas_creadas += 1

        self.stdout.write(f"  Ventas locales creadas: {ventas_creadas}")

        gastos_data = [
            {"desc": "Compra de materiales", "monto": 8000, "dias": 5},
            {"desc": "Envíos del mes", "monto": 3500, "dias": 3},
            {"desc": "Publicidad Instagram", "monto": 5000, "dias": 7},
            {"desc": "Alquiler local", "monto": 45000, "dias": 1},
            {"desc": "Packaging y bolsas", "monto": 2500, "dias": 10},
            {"desc": "Servicios luz/gas", "monto": 4000, "dias": 15},
        ]

        for gd in gastos_data:
            Gasto.objects.create(
                descripcion=gd["desc"],
                monto=Decimal(str(gd["monto"])),
                fecha=(now - timedelta(days=gd["dias"])).date(),
                observaciones=DEMO_MARKER,
            )

        self.stdout.write(f"  Gastos creados: {len(gastos_data)}")

        self.stdout.write(self.style.SUCCESS("\n--- SEED COMPLETADO ---\n"))
        self.stdout.write(self.style.SUCCESS("Para eliminar los datos después ejecutá:"))
        self.stdout.write(self.style.SUCCESS("  python manage.py seed_demo --delete\n"))
