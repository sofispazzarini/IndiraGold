from django.core.management.base import BaseCommand

from pedidos.stock_pedidos import reservas_vencidas, vencer_reservas


class Command(BaseCommand):
    help = (
        'Vence los pedidos pendientes que no se pagaron en su plazo y devuelve sus unidades al stock. '
        'La app ya lo hace sola al recibir visitas; este comando sirve para programarlo (cron).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Solo muestra qué pedidos vencería.')

    def handle(self, *args, **options):
        if options['dry_run']:
            ids = list(reservas_vencidas().values_list('pk', flat=True))
            self.stdout.write(f'Pedidos para vencer: {len(ids)} {ids}')
            return
        vencidos = vencer_reservas()
        self.stdout.write(self.style.SUCCESS(f'Pedidos vencidos: {vencidos}'))
