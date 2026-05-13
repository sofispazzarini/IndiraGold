from django.core.management.base import BaseCommand
from productos.models import Variante, VarianteColor


class Command(BaseCommand):
    help = 'Genera registros VarianteColor para todas las combinaciones existentes de Variante + Color'

    def add_arguments(self, parser):
        parser.add_argument(
            '--producto',
            type=int,
            help='ID del producto específico (opcional, si no se especifica procesa todos)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula la ejecución sin crear registros',
        )

    def handle(self, *args, **options):
        producto_id = options.get('producto')
        dry_run = options.get('dry_run', False)

        if dry_run:
            self.stdout.write(self.style.WARNING('Modo dry-run: no se crearán registros'))

        variantes = Variante.objects.select_related('producto', 'talle').prefetch_related('colores')

        if producto_id:
            variantes = variantes.filter(producto_id=producto_id)
            self.stdout.write(f'Procesando variantes del producto ID: {producto_id}')
        else:
            self.stdout.write('Procesando todas las variantes...')

        creados = 0
        existentes = 0
        errores = 0

        for variante in variantes:
            for color in variante.colores.all():
                if dry_run:
                    existe = VarianteColor.objects.filter(variante=variante, color=color).exists()
                    if existe:
                        existentes += 1
                        self.stdout.write(f'  [EXISTE] {variante} - {color}')
                    else:
                        creados += 1
                        self.stdout.write(f'  [CREAR] {variante} - {color}')
                else:
                    try:
                        vc, created = VarianteColor.objects.get_or_create(
                            variante=variante,
                            color=color,
                            defaults={'activo': variante.activa}
                        )
                        if created:
                            creados += 1
                            self.stdout.write(self.style.SUCCESS(f'  Creado: {vc}'))
                        else:
                            existentes += 1
                    except Exception as e:
                        errores += 1
                        self.stdout.write(self.style.ERROR(f'  Error en {variante} - {color}: {e}'))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Resumen:'))
        self.stdout.write(f'  - Creados: {creados}')
        self.stdout.write(f'  - Ya existentes: {existentes}')
        if errores:
            self.stdout.write(self.style.ERROR(f'  - Errores: {errores}'))
