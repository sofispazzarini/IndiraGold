from django.core.management.base import BaseCommand, CommandError
from productos.imagenes import TAMANOS, generar_derivadas, nombre_derivada
from productos.models import ImagenProducto


class Command(BaseCommand):
    help = 'Genera copias WebP sin cambiar BD ni originales. Por defecto solo simula.'

    def add_arguments(self, parser):
        modo = parser.add_mutually_exclusive_group()
        modo.add_argument('--aplicar', action='store_true')
        modo.add_argument('--dry-run', action='store_true')
        parser.add_argument('--desde-id', type=int, default=0)
        parser.add_argument('--limite', type=int, default=100)

    def handle(self, *args, **options):
        if options['limite'] < 1 or options['desde_id'] < 0:
            raise CommandError('Usá --limite mayor a cero y --desde-id no negativo.')
        errores = 0
        imagenes = ImagenProducto.objects.filter(pk__gte=options['desde_id']).order_by('pk')[:options['limite']]
        for imagen in imagenes.iterator():
            try:
                archivo = imagen.imagen
                if not archivo or not archivo.storage.exists(archivo.name):
                    raise ValueError('Falta el original; restaurar desde backup.')
                faltan = sum(not archivo.storage.exists(nombre_derivada(archivo, lado)) for lado in TAMANOS)
                if options['aplicar']:
                    generar_derivadas(archivo)
                self.stdout.write(f'id={imagen.pk}: {faltan} copias ' + ('procesadas' if options['aplicar'] else 'pendientes (simulación)'))
            except Exception as error:
                errores += 1
                self.stderr.write(f'id={imagen.pk}: {type(error).__name__}: {error}')
        if errores:
            raise CommandError(f'{errores} imágenes requieren revisión; no se borró ningún original.')
