import random
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth.models import User

# Importaciones de tus apps
from productos.models import Categoria, Subcategoria, Producto, Proveedor, Variante, Color, Talle
from users.models import Cliente  

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('--- Iniciando Seed Definitivo ---'))

        with transaction.atomic():
            # 1. USUARIO Y CLIENTE (Campos: dni, telefono, user, deuda_total)
            user_demo, _ = User.objects.get_or_create(
                username="admin_indiragold",
                defaults={'email': "admin@test.com", 'first_name': "Nicolas"}
            )

            cli, _ = Cliente.objects.get_or_create(
                user=user_demo,
                defaults={
                    'dni': "12345678", 
                    'telefono': "221 445-8141",
                    'deuda_total': 0
                }
            )

            # 2. CATEGORÍA Y PRODUCTO
            prov, _ = Proveedor.objects.get_or_create(nombre="Proveedor Indira")
            cat, _ = Categoria.objects.get_or_create(nombre="Indumentaria")
            sub, _ = Subcategoria.objects.get_or_create(nombre="Remeras", categoria=cat)
            
            prod, _ = Producto.objects.get_or_create(
                codigo="AUR-001",
                defaults={
                    'nombre': "Remera Aura",
                    'precio': 15000,
                    'stock': 100,
                    'categoria': cat,
                    'subcategoria': sub,
                    'proveedor': prov
                }
            )

            # 3. VARIANTES (Choices: activa, colores, stock, talle, precio, producto)
            col, _ = Color.objects.get_or_create(nombre="Bordeaux")
            tal, _ = Talle.objects.get_or_create(nombre="L")

            # Primero creamos la variante sin el campo 'colores' (por ser plural/M2M)
            variante, created = Variante.objects.get_or_create(
                producto=prod,
                talle=tal,
                defaults={
                    'precio': 15000,
                    'stock': 20,
                    'activa': True
                }
            )
            
            # Ahora le asignamos el color usando el nombre exacto: 'colores'
            variante.colores.add(col)
            
            if created:
                self.stdout.write(f'Variante para "{prod.nombre}" creada correctamente.')

        self.stdout.write(self.style.SUCCESS('--- ¡Seed cargado con éxito! ---'))