from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

from productos.models import Variante, VarianteColor
from productos.stock import repartir_stock_en_colores, sincronizar_stock_variante


class Command(BaseCommand):
    help = (
        'Repara talles cuyo stock no coincide con la suma de sus colores. '
        'Si todos los colores están en 0 y el talle tiene stock (por ejemplo, después de abrir '
        '"Ver QRs" antes del fix QA-014), reparte el stock del talle entre sus colores; '
        'en cualquier otro caso deja el talle igual a la suma de sus colores.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Muestra los cambios sin guardarlos')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        reparados = 0

        variantes = Variante.objects.select_related('producto', 'talle').filter(
            variante_colores__activo=True
        ).distinct()

        with transaction.atomic():
            for variante in variantes:
                colores = VarianteColor.objects.filter(variante=variante, activo=True).select_related('color')
                suma = colores.aggregate(total=Sum('stock'))['total'] or 0
                if suma == variante.stock:
                    continue

                reparados += 1
                if suma == 0 and variante.stock > 0:
                    reparto = repartir_stock_en_colores(variante.stock, [vc.color for vc in colores])
                    detalle = ', '.join(f'{vc.color.nombre}={reparto[vc.color_id]}' for vc in colores)
                    self.stdout.write(f'  {variante}: colores en 0, se reparte {variante.stock} -> {detalle}')
                    if not dry_run:
                        for vc in colores:
                            vc.stock = reparto[vc.color_id]
                            vc.save(update_fields=['stock'])
                else:
                    self.stdout.write(f'  {variante}: talle {variante.stock} -> suma de colores {suma}')

                if not dry_run:
                    sincronizar_stock_variante(variante)

            if dry_run:
                transaction.set_rollback(True)

        modo = ' (dry-run, sin guardar)' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(f'Talles reparados: {reparados}{modo}'))
