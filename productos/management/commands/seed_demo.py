
import random
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth.models import User

from productos.models import (
    Categoria,
    Subcategoria,
    Producto,
    Proveedor,
    Variante,
    Color,
    Talle
)

from users.models import (
    Cliente,
    Direccion
)

from pedidos.models import (
    Pedido,
    PedidoItem
)

from carritos.models import (
    Carrito,
    CarritoItem
)


class Command(BaseCommand):

    help = 'Carga datos demo completos para IndiraGold'

    @transaction.atomic
    def handle(self, *args, **kwargs):

        self.stdout.write(
            self.style.WARNING(
                '\n--- Limpiando base de datos demo ---\n'
            )
        )

        # LIMPIAR DATOS
        PedidoItem.objects.all().delete()
        Pedido.objects.all().delete()

        CarritoItem.objects.all().delete()
        Carrito.objects.all().delete()

        Variante.objects.all().delete()
        Producto.objects.all().delete()

        Subcategoria.objects.all().delete()
        Categoria.objects.all().delete()

        Proveedor.objects.all().delete()

        Color.objects.all().delete()
        Talle.objects.all().delete()

        Direccion.objects.all().delete()
        Cliente.objects.all().delete()

        User.objects.filter(
            username__in=[
                'martina_demo',
                'lucia_demo',
                'sofia_demo'
            ]
        ).delete()

        self.stdout.write(
            self.style.SUCCESS(
                'Base demo limpiada correctamente.\n'
            )
        )

        # ======================================================
        # TALLES
        # ======================================================

        talles_nombres = ['XS', 'S', 'M', 'L', 'XL']

        talles = []

        for nombre in talles_nombres:

            talle = Talle.objects.create(
                nombre=nombre
            )

            talles.append(talle)

        # ======================================================
        # COLORES
        # ======================================================

        colores_nombres = [
            'Negro',
            'Blanco',
            'Beige',
            'Bordeaux',
            'Rosa'
        ]

        colores = []

        for nombre in colores_nombres:

            color = Color.objects.create(
                nombre=nombre
            )

            colores.append(color)

        # ======================================================
        # PROVEEDORES
        # ======================================================

        proveedor = Proveedor.objects.create(
            nombre='Proveedor Boutique Indira'
        )

        # ======================================================
        # CATEGORIAS
        # ======================================================

        categoria = Categoria.objects.create(
            nombre='Indumentaria'
        )

        subcategorias = [
            'Remeras',
            'Vestidos',
            'Blazers',
            'Pantalones',
            'Camisas',
            'Tops'
        ]

        subs = []

        for nombre in subcategorias:

            sub = Subcategoria.objects.create(
                nombre=nombre,
                categoria=categoria
            )

            subs.append(sub)

        # ======================================================
        # PRODUCTOS
        # ======================================================

        productos_data = [

            {
                'nombre': 'Remera Aura',
                'precio': 18500,
                'sub': 'Remeras'
            },

            {
                'nombre': 'Vestido Serena',
                'precio': 42000,
                'sub': 'Vestidos'
            },

            {
                'nombre': 'Blazer Monaco',
                'precio': 68000,
                'sub': 'Blazers'
            },

            {
                'nombre': 'Top Olivia',
                'precio': 21000,
                'sub': 'Tops'
            },

            {
                'nombre': 'Pantalón Siena',
                'precio': 39000,
                'sub': 'Pantalones'
            },

            {
                'nombre': 'Camisa Vienna',
                'precio': 33000,
                'sub': 'Camisas'
            },
        ]

        productos_creados = []

        for i, data in enumerate(productos_data):

            sub = Subcategoria.objects.get(
                nombre=data['sub']
            )

            producto = Producto.objects.create(
                codigo=f'IND-{100+i}',
                nombre=data['nombre'],
                precio=Decimal(data['precio']),
                stock=100,
                categoria=categoria,
                subcategoria=sub,
                proveedor=proveedor
            )

            productos_creados.append(producto)

            # VARIANTES

            for talle in talles:

                variante = Variante.objects.create(
                    producto=producto,
                    talle=talle,
                    precio=Decimal(data['precio']),
                    stock=random.randint(3, 20),
                    activa=True,
                    qr_code=f'QR-{producto.codigo}-{talle.nombre}-{random.randint(1000,9999)}',
                )

                colores_random = random.sample(
                    colores,
                    random.randint(1, 3)
                )

                variante.colores.set(colores_random)

        self.stdout.write(
            self.style.SUCCESS(
                'Productos y variantes creados.\n'
            )
        )

        # ======================================================
        # CLIENTES
        # ======================================================

        clientes_data = [

            {
                'username': 'martina_demo',
                'nombre': 'Martina',
                'email': 'martina@test.com'
            },

            {
                'username': 'lucia_demo',
                'nombre': 'Lucia',
                'email': 'lucia@test.com'
            },

            {
                'username': 'sofia_demo',
                'nombre': 'Sofia',
                'email': 'sofia@test.com'
            }
        ]

        clientes = []

        for i, data in enumerate(clientes_data):

            user = User.objects.create_user(
                username=data['username'],
                email=data['email'],
                password='1234',
                first_name=data['nombre']
            )

            cliente = Cliente.objects.create(
                user=user,
                dni=f'4011122{i}',
                telefono=f'22155566{i}',
                deuda_total=0
            )

            clientes.append(cliente)

            # DIRECCIONES

            Direccion.objects.create(
                cliente=cliente,
                calle='Calle 50',
                numero='1234',
                ciudad='La Plata',
                provincia='Buenos Aires',
                codigo_postal='1900'
            )

            Direccion.objects.create(
                cliente=cliente,
                calle='Diagonal 74',
                numero='555',
                ciudad='La Plata',
                provincia='Buenos Aires',
                codigo_postal='1900'
            )

        self.stdout.write(
            self.style.SUCCESS(
                'Clientes y direcciones creados.\n'
            )
        )

        # ======================================================
        # PEDIDOS
        # ======================================================

        estados_demo = [
            'pendiente',
            'aceptado',
            'en_preparacion',
            'enviado'
        ]

        for cliente in clientes:

            for _ in range(2):

                metodo = random.choice([
                    'local',
                    'domicilio'
                ])

                costo_envio = (
                    Decimal('5000')
                    if metodo == 'domicilio'
                    else Decimal('0')
                )

                pedido = Pedido.objects.create(
                    cliente=cliente,
                    total=0,
                    tipo_venta='online',
                    estado=random.choice(estados_demo),
                    metodo_entrega=metodo,
                    costo_envio=costo_envio,
                    codigo_postal='1900',
                    localidad='La Plata',
                    calle_numero='Calle Demo 123'
                )

                total = Decimal('0')

                variantes = Variante.objects.order_by('?')[:3]

                for variante in variantes:

                    cantidad = random.randint(1, 2)

                    subtotal = (
                        variante.precio * cantidad
                    )

                    PedidoItem.objects.create(
                        pedido=pedido,
                        variante=variante,
                        cantidad=cantidad,
                        precio_unitario=variante.precio,
                        precio_total=subtotal
                    )

                    total += subtotal

                pedido.total = total + costo_envio
                pedido.save()

        self.stdout.write(
            self.style.SUCCESS(
                'Pedidos demo creados.\n'
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                '\n--- SEED COMPLETADO CON ÉXITO ---\n'
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                'Usuarios demo:\n'
                'martina_demo / 1234\n'
                'lucia_demo / 1234\n'
                'sofia_demo / 1234\n'
            )
        )

