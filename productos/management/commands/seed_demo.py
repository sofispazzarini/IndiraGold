from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from productos.models import Categoria, Proveedor, Producto


class Command(BaseCommand):
    help = "Crea datos demo (categorías/proveedor/productos) solo si no existen."

    @transaction.atomic
    def handle(self, *args, **options):
        proveedor, _ = Proveedor.objects.get_or_create(
            nombre="Proveedor General",
            defaults={"telefono": "1122334455"},
        )

        categorias = {}
        for nombre in ("Anillos", "Pulseras", "Collares"):
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
        ]

        created = 0
        skipped = 0
        for data in productos_demo:
            codigo = data.pop("codigo")
            defaults = {
                **data,
                "codigo": codigo,
                "proveedor": proveedor,
                "activo": True,
            }
            _, was_created = Producto.objects.get_or_create(codigo=codigo, defaults=defaults)
            if was_created:
                created += 1
            else:
                skipped += 1

        self.stdout.write(self.style.SUCCESS(f"Seed demo listo. Creados: {created}. Ya existían: {skipped}."))
