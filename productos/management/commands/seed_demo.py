from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from productos.models import Categoria, Proveedor, Producto, Talle, Color, Medida, Variante


class Command(BaseCommand):
    help = "Crea datos demo (categorías/proveedor/productos) solo si no existen."

    @transaction.atomic
    def handle(self, *args, **options):
        proveedor, _ = Proveedor.objects.get_or_create(
            nombre="Proveedor General",
            defaults={"telefono": "1122334455"},
        )

        categorias = {}
        for nombre in ("Anillos", "Pulseras", "Collares", "Remeras", "Pantalones", "Buzos"):
            cat, _ = Categoria.objects.get_or_create(nombre=nombre, defaults={"activa": True})
            # En caso de que existan viejas sin 'activa' seteada, dejamos el valor actual.
            if hasattr(cat, "activa") and cat.activa is False:
                cat.activa = True
                cat.save(update_fields=["activa"])
            categorias[nombre] = cat

        productos_demo = [
            {
                "codigo": "ANI-001",
                "nombre": "Anillo Dorado",
                "tipo": "Anillo",
                "tela": "Acero",
                "descripcion": "Anillo de acero dorado",
                "precio": "15000.00",
                "stock": 10,
                "categoria": categorias["Anillos"],
            },
            {
                "codigo": "ANI-002",
                "nombre": "Anillo Minimalista",
                "tipo": "Anillo",
                "tela": "Acero",
                "descripcion": "Anillo minimalista, ideal para uso diario.",
                "precio": "12000.00",
                "stock": 6,
                "categoria": categorias["Anillos"],
            },
            {
                "codigo": "PUL-001",
                "nombre": "Pulsera Eslabones",
                "tipo": "Pulsera",
                "tela": "Acero",
                "descripcion": "Pulsera de eslabones con acabado brillante.",
                "precio": "18000.00",
                "stock": 3,
                "categoria": categorias["Pulseras"],
            },
            {
                "codigo": "COL-001",
                "nombre": "Collar Dije",
                "tipo": "Collar",
                "tela": "Acero",
                "descripcion": "Collar con dije, diseño elegante.",
                "precio": "21000.00",
                "stock": 0,
                "categoria": categorias["Collares"],
            },
            {
                "codigo": "REM-001",
                "nombre": "Remera Básica Blanca",
                "tipo": "Remera",
                "tela": "Algodón",
                "descripcion": "Remera clásica de algodón, calce regular.",
                "precio": "18500.00",
                "stock": 0,
                "categoria": categorias["Remeras"],
            },
            {
                "codigo": "PAN-001",
                "nombre": "Pantalón Cargo Verde",
                "tipo": "Pantalón",
                "tela": "Gabardina",
                "descripcion": "Pantalón cargo de gabardina, cómodo para uso diario.",
                "precio": "32900.00",
                "stock": 0,
                "categoria": categorias["Pantalones"],
            },
            {
                "codigo": "BUZ-001",
                "nombre": "Buzo Oversize Negro",
                "tipo": "Buzo",
                "tela": "Frisa",
                "descripcion": "Buzo oversize con interior suave.",
                "precio": "27900.00",
                "stock": 0,
                "categoria": categorias["Buzos"],
            },
        ]

        created = 0
        skipped = 0
        productos_by_code: dict[str, Producto] = {}
        for data in productos_demo:
            codigo = data.pop("codigo")
            defaults = {
                **data,
                "codigo": codigo,
                "proveedor": proveedor,
                "activo": True,
            }
            producto, was_created = Producto.objects.get_or_create(codigo=codigo, defaults=defaults)
            productos_by_code[codigo] = producto
            if was_created:
                created += 1
            else:
                skipped += 1

        talles = {}
        for nombre in ("S", "M", "L"):
            talle, _ = Talle.objects.get_or_create(nombre=nombre)
            talles[nombre] = talle

        colores = {}
        for nombre in ("Blanco", "Negro", "Verde"):
            color, _ = Color.objects.get_or_create(nombre=nombre)
            colores[nombre] = color

        medidas = {
            "S": Medida.objects.get_or_create(alto="65.00", ancho="48.00", largo="66.00", tiro=None)[0],
            "M": Medida.objects.get_or_create(alto="68.00", ancho="51.00", largo="69.00", tiro=None)[0],
            "L": Medida.objects.get_or_create(alto="71.00", ancho="54.00", largo="72.00", tiro=None)[0],
            "P-S": Medida.objects.get_or_create(alto=None, ancho="38.00", largo="98.00", tiro="28.00")[0],
            "P-M": Medida.objects.get_or_create(alto=None, ancho="40.00", largo="101.00", tiro="29.50")[0],
            "P-L": Medida.objects.get_or_create(alto=None, ancho="42.00", largo="104.00", tiro="31.00")[0],
        }

        variantes_demo = [
            # Remera
            {
                "producto": "REM-001",
                "talle": "S",
                "color": "Blanco",
                "medida": "S",
                "stock": 4,
                "precio": "18500.00",
                "qr": "REM001-S-BLANCO",
            },
            {
                "producto": "REM-001",
                "talle": "M",
                "color": "Blanco",
                "medida": "M",
                "stock": 5,
                "precio": "18500.00",
                "qr": "REM001-M-BLANCO",
            },
            {
                "producto": "REM-001",
                "talle": "L",
                "color": "Negro",
                "medida": "L",
                "stock": 3,
                "precio": "18900.00",
                "qr": "REM001-L-NEGRO",
            },
            # Pantalón
            {
                "producto": "PAN-001",
                "talle": "S",
                "color": "Verde",
                "medida": "P-S",
                "stock": 2,
                "precio": "32900.00",
                "qr": "PAN001-S-VERDE",
            },
            {
                "producto": "PAN-001",
                "talle": "M",
                "color": "Verde",
                "medida": "P-M",
                "stock": 4,
                "precio": "32900.00",
                "qr": "PAN001-M-VERDE",
            },
            {
                "producto": "PAN-001",
                "talle": "L",
                "color": "Negro",
                "medida": "P-L",
                "stock": 1,
                "precio": "33900.00",
                "qr": "PAN001-L-NEGRO",
            },
            # Buzo
            {
                "producto": "BUZ-001",
                "talle": "S",
                "color": "Negro",
                "medida": "S",
                "stock": 3,
                "precio": "27900.00",
                "qr": "BUZ001-S-NEGRO",
            },
            {
                "producto": "BUZ-001",
                "talle": "M",
                "color": "Negro",
                "medida": "M",
                "stock": 3,
                "precio": "27900.00",
                "qr": "BUZ001-M-NEGRO",
            },
            {
                "producto": "BUZ-001",
                "talle": "L",
                "color": "Blanco",
                "medida": "L",
                "stock": 2,
                "precio": "28500.00",
                "qr": "BUZ001-L-BLANCO",
            },
        ]

        variantes_creadas = 0
        variantes_existentes = 0
        for row in variantes_demo:
            producto = productos_by_code.get(row["producto"])
            if not producto:
                continue

            _, variante_creada = Variante.objects.get_or_create(
                qr_code=row["qr"],
                defaults={
                    "producto": producto,
                    "talle": talles[row["talle"]],
                    "color": colores[row["color"]],
                    "medida": medidas[row["medida"]],
                    "stock": row["stock"],
                    "precio": row["precio"],
                    "activa": True,
                },
            )
            if variante_creada:
                variantes_creadas += 1
            else:
                variantes_existentes += 1

        for codigo in ("REM-001", "PAN-001", "BUZ-001"):
            producto = productos_by_code.get(codigo)
            if not producto:
                continue
            stock_total = sum(producto.variantes.filter(activa=True).values_list("stock", flat=True))
            if producto.stock != stock_total:
                producto.stock = stock_total
                producto.save(update_fields=["stock"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed demo listo. Productos creados: {created}. Productos existentes: {skipped}. "
                f"Variantes creadas: {variantes_creadas}. Variantes existentes: {variantes_existentes}."
            )
        )
