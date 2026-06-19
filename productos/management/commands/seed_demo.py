import random
import uuid
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from carritos.models import Carrito, CarritoItem
from consultas.models import Consulta, TemaConsulta
from home.models import SlideCarrousel
from pedidos.models import (
    ConfiguracionEnvio,
    Gasto,
    Pago,
    PagoVentaLocal,
    Pedido,
    PedidoItem,
    VentaLocal,
    VentaLocalItem,
)
from productos.models import (
    Categoria,
    CategoriaOrden,
    CategoriaOrdenProducto,
    Color,
    ImagenProducto,
    Medida,
    Oferta,
    Producto,
    Proveedor,
    Subcategoria,
    Talle,
    TipoMedida,
    Variante,
    VarianteColor,
)
from users.models import Cliente, Direccion


class Command(BaseCommand):
    help = "Carga datos demo completos para IndiraGold"

    PRODUCT_IMAGE_SIZE = (1200, 1600)
    SLIDE_IMAGE_SIZE = (1800, 720)
    TECH_IMAGE_SIZE = (1000, 1250)

    def _image_file(self, title, subtitle, palette, size, filename):
        img = Image.new("RGB", size, palette["bg"])
        draw = ImageDraw.Draw(img)
        w, h = size

        draw.rectangle([0, 0, w, h], fill=palette["bg"])
        draw.ellipse([-w * 0.25, h * 0.05, w * 0.65, h * 0.65], fill=palette["soft"])
        draw.rectangle([w * 0.08, h * 0.08, w * 0.92, h * 0.92], outline=palette["line"], width=max(4, w // 180))
        draw.line([w * 0.14, h * 0.72, w * 0.86, h * 0.22], fill=palette["line"], width=max(3, w // 260))

        try:
            title_font = ImageFont.truetype("arial.ttf", max(34, w // 16))
            sub_font = ImageFont.truetype("arial.ttf", max(20, w // 34))
        except OSError:
            title_font = ImageFont.load_default()
            sub_font = ImageFont.load_default()

        title_box = draw.textbbox((0, 0), title, font=title_font)
        title_w = title_box[2] - title_box[0]
        draw.text(((w - title_w) / 2, h * 0.43), title, fill=palette["text"], font=title_font)

        sub_box = draw.textbbox((0, 0), subtitle, font=sub_font)
        sub_w = sub_box[2] - sub_box[0]
        draw.text(((w - sub_w) / 2, h * 0.5), subtitle, fill=palette["text"], font=sub_font)

        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=88, optimize=True)
        return ContentFile(buffer.getvalue(), name=filename)

    def _create_product_images(self, producto, data, index):
        palettes = [
            {"bg": "#f4ebe2", "soft": "#e4c7b5", "line": "#b8922a", "text": "#2b2118"},
            {"bg": "#efe7dd", "soft": "#d6d8cf", "line": "#7f8a73", "text": "#26251f"},
            {"bg": "#f2eeee", "soft": "#d9a6a6", "line": "#8f2f4b", "text": "#211a1c"},
            {"bg": "#e9edf0", "soft": "#c9d6df", "line": "#335c67", "text": "#172026"},
            {"bg": "#f7f1df", "soft": "#ead49b", "line": "#b8922a", "text": "#251f17"},
        ]
        palette = palettes[index % len(palettes)]

        for number, label in enumerate(["Portada", "Detalle", "Look"], start=1):
            image = self._image_file(
                data["nombre"],
                f"{label} - {data['tela']}",
                palette,
                self.PRODUCT_IMAGE_SIZE,
                f"{producto.codigo.lower()}-{number}.jpg",
            )
            ImagenProducto.objects.create(
                producto=producto,
                imagen=image,
                es_portada=(number == 1),
            )

        tech = self._image_file(
            "Ficha tecnica",
            f"{data['tipo']} | {data['tela']}",
            palette,
            self.TECH_IMAGE_SIZE,
            f"{producto.codigo.lower()}-ficha.jpg",
        )
        producto.imagen_tecnica.save(tech.name, tech, save=True)

    def _create_slide(self, title, subtitle, order, palette):
        image = self._image_file(
            title,
            subtitle,
            palette,
            self.SLIDE_IMAGE_SIZE,
            f"slide-demo-{order}.jpg",
        )
        return SlideCarrousel.objects.create(
            imagen=image,
            titulo=title,
            subtitulo=subtitle,
            link="/#catalogo",
            orden=order,
            activo=True,
        )

    @transaction.atomic
    def handle(self, *args, **kwargs):
        random.seed(24)

        self.stdout.write(self.style.WARNING("\n--- Limpiando base de datos demo ---\n"))

        PagoVentaLocal.objects.all().delete()
        VentaLocalItem.objects.all().delete()
        VentaLocal.objects.all().delete()
        Pago.objects.all().delete()
        PedidoItem.objects.all().delete()
        Pedido.objects.all().delete()
        CarritoItem.objects.all().delete()
        Carrito.objects.all().delete()
        Gasto.objects.all().delete()

        Oferta.objects.all().delete()
        CategoriaOrdenProducto.objects.all().delete()
        CategoriaOrden.objects.all().delete()
        VarianteColor.objects.all().delete()
        Variante.objects.all().delete()
        Medida.objects.all().delete()
        ImagenProducto.objects.all().delete()
        Producto.objects.all().delete()
        Subcategoria.objects.all().delete()
        Categoria.objects.all().delete()
        Proveedor.objects.all().delete()
        Color.objects.all().delete()
        Talle.objects.all().delete()
        TipoMedida.objects.all().delete()

        Consulta.objects.all().delete()
        TemaConsulta.objects.all().delete()
        SlideCarrousel.objects.all().delete()
        ConfiguracionEnvio.objects.all().delete()

        Direccion.objects.all().delete()
        Cliente.objects.all().delete()
        User.objects.filter(
            username__in=["admin_demo", "40111220", "40111221", "40111222", "40111223"]
        ).delete()

        self.stdout.write(self.style.SUCCESS("Base demo limpiada correctamente.\n"))

        admin = User.objects.create_superuser(
            username="admin_demo",
            email="admin@indiragold.test",
            password="1234",
            first_name="Admin",
        )

        talles = [
            Talle.objects.create(nombre=nombre)
            for nombre in ["XS", "S", "M", "L", "XL", "XXL"]
        ]

        color_data = [
            "Negro",
            "Blanco",
            "Beige",
            "Bordeaux",
            "Rosa",
            "Chocolate",
            "Verde oliva",
            "Azul noche",
        ]
        colores = [Color.objects.create(nombre=nombre) for nombre in color_data]

        for nombre, descripcion in [
            ("Alto", "Medida vertical de la prenda"),
            ("Ancho", "Ancho de busto o cintura segun prenda"),
            ("Largo", "Largo total de la prenda"),
            ("Tiro", "Medida de tiro para pantalones"),
        ]:
            TipoMedida.objects.create(nombre=nombre, descripcion=descripcion)

        proveedores = [
            Proveedor.objects.create(
                nombre="Boutique Indira",
                telefono="2215550101",
                informacion_adicional="Proveedor principal de colecciones urbanas.",
            ),
            Proveedor.objects.create(
                nombre="Atelier Dorado",
                telefono="2215550102",
                informacion_adicional="Produccion limitada y prendas de noche.",
            ),
            Proveedor.objects.create(
                nombre="Textiles Serena",
                telefono="2215550103",
                informacion_adicional="Telas premium, lino, saten y crepe.",
            ),
        ]

        categorias_data = {
            "Indumentaria": ["Remeras", "Tops", "Camisas", "Blazers"],
            "Vestidos": ["Vestidos cortos", "Vestidos largos"],
            "Pantalones": ["Sastreros", "Jeans", "Palazzos"],
            "Accesorios": ["Carteras", "Cinturones"],
        }
        categorias = {}
        subcategorias = {}
        for cat_name, sub_names in categorias_data.items():
            categoria = Categoria.objects.create(nombre=cat_name, activa=True)
            categorias[cat_name] = categoria
            for sub_name in sub_names:
                subcategorias[sub_name] = Subcategoria.objects.create(
                    nombre=sub_name,
                    categoria=categoria,
                    activa=True,
                )

        productos_data = [
            {
                "codigo": "IND-100",
                "nombre": "Remera Aura",
                "tipo": "Remera manga corta",
                "tela": "Algodon pima",
                "precio": "18500",
                "sub": "Remeras",
                "temporada": "Verano 2026",
                "descripcion": "Basica premium con calce relajado, ideal para todos los dias.",
                "avios": "Etiqueta tejida, costuras reforzadas",
                "etiquetas": "basico,algodon,nuevo",
            },
            {
                "codigo": "IND-101",
                "nombre": "Vestido Serena",
                "tipo": "Vestido midi",
                "tela": "Saten elastizado",
                "precio": "42000",
                "sub": "Vestidos largos",
                "temporada": "Fiesta",
                "descripcion": "Vestido satinado con caida suave y espalda delicada.",
                "avios": "Cierre invisible, breteles regulables",
                "etiquetas": "fiesta,saten,elegante",
            },
            {
                "codigo": "IND-102",
                "nombre": "Blazer Monaco",
                "tipo": "Blazer sastrero",
                "tela": "Crepe premium",
                "precio": "68000",
                "sub": "Blazers",
                "temporada": "Invierno 2026",
                "descripcion": "Blazer estructurado con forreria interna y boton metalizado.",
                "avios": "Botones dorados, hombreras livianas",
                "etiquetas": "sastreria,oficina,noche",
            },
            {
                "codigo": "IND-103",
                "nombre": "Top Olivia",
                "tipo": "Top escote cuadrado",
                "tela": "Morley soft",
                "precio": "21000",
                "sub": "Tops",
                "temporada": "Verano 2026",
                "descripcion": "Top elastizado de calce firme para combinar con tiro alto.",
                "avios": "Terminaciones al tono",
                "etiquetas": "top,morley,casual",
            },
            {
                "codigo": "IND-104",
                "nombre": "Pantalon Siena",
                "tipo": "Pantalon sastrero",
                "tela": "Lino blend",
                "precio": "39000",
                "sub": "Sastreros",
                "temporada": "Capsula neutros",
                "descripcion": "Pantalon tiro alto con pinzas y pierna recta.",
                "avios": "Broche interno, presillas",
                "etiquetas": "sastrero,lino,neutro",
            },
            {
                "codigo": "IND-105",
                "nombre": "Camisa Vienna",
                "tipo": "Camisa oversize",
                "tela": "Poplin premium",
                "precio": "33000",
                "sub": "Camisas",
                "temporada": "Todo el ano",
                "descripcion": "Camisa amplia con cuello clasico y punos anchos.",
                "avios": "Botones nacarados",
                "etiquetas": "camisa,poplin,oversize",
            },
            {
                "codigo": "IND-106",
                "nombre": "Jean Roma",
                "tipo": "Jean wide leg",
                "tela": "Denim rigido",
                "precio": "44500",
                "sub": "Jeans",
                "temporada": "Denim",
                "descripcion": "Jean de tiro alto con pierna ancha y lavado azul medio.",
                "avios": "Remaches metalicos, boton jeanero",
                "etiquetas": "denim,wideleg,urbano",
            },
            {
                "codigo": "IND-107",
                "nombre": "Cartera Lirio",
                "tipo": "Cartera mini",
                "tela": "Eco cuero",
                "precio": "29500",
                "sub": "Carteras",
                "temporada": "Accesorios",
                "descripcion": "Cartera mini con correa regulable y herrajes dorados.",
                "avios": "Cierre metalico, forro interno",
                "etiquetas": "cartera,accesorio,dorado",
            },
        ]

        productos = []
        for index, data in enumerate(productos_data):
            subcategoria = subcategorias[data["sub"]]
            producto = Producto.objects.create(
                codigo=data["codigo"],
                nombre=data["nombre"],
                tipo=data["tipo"],
                tela=data["tela"],
                descripcion=data["descripcion"],
                precio=Decimal(data["precio"]),
                stock=0,
                categoria=subcategoria.categoria,
                subcategoria=subcategoria,
                proveedor=proveedores[index % len(proveedores)],
                temporada=data["temporada"],
                avios=data["avios"],
                etiquetas=data["etiquetas"],
                activo=True,
            )

            total_stock = 0
            for talle in talles[:5]:
                stock = random.randint(4, 18)
                total_stock += stock
                variante = Variante.objects.create(
                    producto=producto,
                    talle=talle,
                    precio=producto.precio,
                    stock=stock,
                    activa=True,
                    qr_code=f"QR-{producto.codigo}-{talle.nombre}-{uuid.uuid4().hex[:8]}",
                )
                colores_variante = random.sample(colores, random.randint(2, 4))
                variante.colores.set(colores_variante)

                medida = Medida.objects.create(
                    alto=Decimal(55 + talles.index(talle) * 2),
                    ancho=Decimal(42 + talles.index(talle) * 2),
                    largo=Decimal(58 + talles.index(talle) * 2),
                    tiro=Decimal(28 + talles.index(talle)) if "Pantalon" in producto.tipo or "Jean" in producto.tipo else None,
                )
                variante.medidas.add(medida)

                for color in colores_variante:
                    VarianteColor.objects.create(
                        variante=variante,
                        color=color,
                        qr_code=f"VC-{producto.codigo}-{talle.nombre}-{color.id}-{uuid.uuid4().hex[:8]}",
                    )

            producto.stock = total_stock
            producto.save(update_fields=["stock"])
            self._create_product_images(producto, data, index)
            productos.append(producto)

        oferta = Oferta.objects.create(
            nombre="Lanzamiento Indira",
            descuento=15,
            aplicar_a_todos=False,
            activa=True,
            fecha_inicio=timezone.now() - timedelta(days=3),
            fecha_fin=timezone.now() + timedelta(days=30),
        )
        oferta.productos.set(productos[:4])

        for nombre, descripcion, seleccion in [
            ("Novedades", "Ultimos ingresos de la tienda.", productos[:6]),
            ("Mas vendidos", "Prendas elegidas por nuestras clientas.", productos[1:7]),
            ("Capsula oficina", "Looks comodos y pulidos para todos los dias.", [productos[2], productos[4], productos[5], productos[6]]),
        ]:
            cat_orden = CategoriaOrden.objects.create(
                nombre=nombre,
                descripcion=descripcion,
                activo=True,
            )
            for producto in seleccion:
                CategoriaOrdenProducto.objects.create(
                    categoria_orden=cat_orden,
                    producto=producto,
                )

        self._create_slide(
            "Nueva coleccion",
            "Sastreria suave, tonos neutros y brillo justo",
            1,
            {"bg": "#efe7dd", "soft": "#dcc5ad", "line": "#b8922a", "text": "#211a14"},
        )
        self._create_slide(
            "Looks de fiesta",
            "Vestidos y accesorios para salir",
            2,
            {"bg": "#efe9ea", "soft": "#d5a0a8", "line": "#8f2f4b", "text": "#21161a"},
        )
        self._create_slide(
            "Ofertas activas",
            "Hasta 15% off en seleccionados",
            3,
            {"bg": "#edf1ed", "soft": "#c5d3c1", "line": "#6f7f5d", "text": "#182016"},
        )

        temas = [
            (
                "Compras",
                "Informacion para comprar en la tienda online.",
                [
                    ("Como elijo el talle?", "En cada producto podes consultar la ficha tecnica y la tabla de medidas."),
                    ("Puedo cambiar una prenda?", "Si, los cambios se coordinan dentro de los 15 dias con la prenda sin uso."),
                ],
            ),
            (
                "Envios",
                "Opciones de entrega disponibles.",
                [
                    ("Tienen retiro en local?", "Si, podes retirar gratis por el local una vez confirmado el pedido."),
                    ("Hacen envio Flex?", "Si, Flex esta disponible para zonas cargadas en la configuracion de envios."),
                ],
            ),
        ]
        for tema_index, (nombre, descripcion, faqs) in enumerate(temas, start=1):
            tema = TemaConsulta.objects.create(nombre=nombre, descripcion=descripcion, activo=True)
            for faq_index, (pregunta, respuesta) in enumerate(faqs, start=1):
                Consulta.objects.create(
                    tema=tema,
                    pregunta=pregunta,
                    respuesta=respuesta,
                    orden=(tema_index * 10) + faq_index,
                    activa=True,
                )

        ConfiguracionEnvio.objects.create(
            id=1,
            flex_activo=True,
            precio_flex=Decimal("3500"),
            flex_gratis=False,
            zonas_flex="La Plata, CABA, Quilmes, Berisso, Ensenada",
        )

        clientes_data = [
            ("martina_demo", "Martina", "Perez", "martina@test.com", "40111220", "221555660"),
            ("lucia_demo", "Lucia", "Fernandez", "lucia@test.com", "40111221", "221555661"),
            ("sofia_demo", "Sofia", "Gomez", "sofia@test.com", "40111222", "221555662"),
            ("martina_mail_demo", "Martina", "Colombo", "martinanataliacolombo@gmail.com", "40111223", "221555663"),
        ]
        clientes = []
        for _username, first_name, last_name, email, dni, telefono in clientes_data:
            user = User.objects.create_user(
                username=dni,
                email=email,
                password=dni,
                first_name=first_name,
                last_name=last_name,
            )
            cliente = Cliente.objects.create(user=user, dni=dni, telefono=telefono, deuda_total=0)
            clientes.append(cliente)
            Direccion.objects.create(
                cliente=cliente,
                etiqueta="Casa",
                calle="Calle 50",
                numero="1234",
                ciudad="La Plata",
                provincia="Buenos Aires",
                codigo_postal="1900",
                referencia="Porton verde",
            )
            Direccion.objects.create(
                cliente=cliente,
                etiqueta="Trabajo",
                calle="Diagonal 74",
                numero="555",
                ciudad="La Plata",
                provincia="Buenos Aires",
                codigo_postal="1900",
                referencia="Entrada por recepcion",
            )

        estados_demo = ["pendiente", "aceptado", "en_preparacion", "preparando_envio", "enviado", "entregado"]
        for cliente in clientes:
            direccion = cliente.direcciones.first()
            for order_number in range(2):
                metodo = random.choice(["local", "flex", "correo"])
                costo_envio = Decimal("0") if metodo == "local" else Decimal("3500")
                pedido = Pedido.objects.create(
                    cliente=cliente,
                    total=Decimal("0"),
                    tipo_venta="online",
                    estado=estados_demo[(clientes.index(cliente) + order_number) % len(estados_demo)],
                    metodo_entrega=metodo,
                    costo_envio=costo_envio,
                    codigo_postal=direccion.codigo_postal,
                    localidad=direccion.ciudad,
                    calle_numero=f"{direccion.calle} {direccion.numero}",
                    direccion_info=f"{direccion.calle} {direccion.numero}, {direccion.ciudad}, {direccion.provincia}",
                    correo="Correo Argentino" if metodo == "correo" else "",
                    tipo_correo="Sucursal" if metodo == "correo" else "",
                    sucursal_correo="Sucursal centro" if metodo == "correo" else "",
                    direccion=direccion,
                )

                total = Decimal("0")
                for variante in random.sample(list(Variante.objects.filter(stock__gt=0)), 3):
                    cantidad = random.randint(1, 2)
                    subtotal = variante.precio * cantidad
                    PedidoItem.objects.create(
                        pedido=pedido,
                        variante=variante,
                        cantidad=cantidad,
                        precio_unitario=variante.precio,
                        precio_total=subtotal,
                    )
                    total += subtotal

                pedido.total = total + costo_envio
                pedido.save(update_fields=["total"])
                if pedido.estado in ["aceptado", "en_preparacion", "preparando_envio", "enviado", "entregado"]:
                    Pago.objects.create(pedido=pedido, metodo="Mercado Pago", monto=pedido.total)

        for cliente in clientes[:2]:
            carrito = Carrito.objects.create(
                cliente=cliente,
                activo=True,
                expires_at=timezone.now() + timedelta(hours=1),
            )
            for variante in random.sample(list(Variante.objects.filter(stock__gt=0)), 2):
                CarritoItem.objects.create(
                    carrito=carrito,
                    variante=variante,
                    cantidad=1,
                    precio_unitario=variante.precio,
                    precio_total=variante.precio,
                )

        venta = VentaLocal.objects.create(
            cliente=clientes[0],
            total=Decimal("0"),
            monto_pagado=Decimal("0"),
            saldo_pendiente=Decimal("0"),
            estado_pago="PAGADO",
        )
        venta_total = Decimal("0")
        for variante in random.sample(list(Variante.objects.filter(stock__gt=0)), 2):
            subtotal = variante.precio
            VentaLocalItem.objects.create(
                venta=venta,
                producto=variante.producto,
                variante=variante,
                color=variante.colores.first().nombre,
                cantidad=1,
                precio_unitario=variante.precio,
                subtotal=subtotal,
            )
            venta_total += subtotal
        venta.total = venta_total
        venta.monto_pagado = venta_total
        venta.save(update_fields=["total", "monto_pagado"])
        PagoVentaLocal.objects.create(venta=venta, monto=venta_total)

        Gasto.objects.create(
            descripcion="Compra de packaging",
            monto=Decimal("18500"),
            fecha=timezone.localdate(),
            observaciones="Bolsas, stickers y papel seda para pedidos demo.",
        )
        Gasto.objects.create(
            descripcion="Publicidad redes",
            monto=Decimal("32000"),
            fecha=timezone.localdate() - timedelta(days=2),
            observaciones="Campana demo para lanzamiento.",
        )

        self.stdout.write(self.style.SUCCESS("Productos, imagenes, variantes y secciones creadas.\n"))
        self.stdout.write(self.style.SUCCESS("Clientes, pedidos, carrito, ventas y consultas creados.\n"))
        self.stdout.write(self.style.SUCCESS("\n--- SEED COMPLETADO CON EXITO ---\n"))
        self.stdout.write(
            self.style.SUCCESS(
                "Usuarios demo:\n"
                "admin_demo / 1234\n"
                "40111220 / 40111220 (Martina)\n"
                "40111221 / 40111221 (Lucia)\n"
                "40111222 / 40111222 (Sofia)\n"
                "40111223 / 40111223 (Martina Colombo - prueba mail)\n"
            )
        )
