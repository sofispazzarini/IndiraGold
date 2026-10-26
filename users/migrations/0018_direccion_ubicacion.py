# Escrita a mano a partir de "makemigrations --dry-run": solo agrega la ubicación confirmada en el
# mapa (latitud, longitud y cómo se confirmó). No incluye los "alter id" que makemigrations agrega
# según la versión de Django.
# Campos opcionales: las direcciones existentes quedan sin coordenadas y sin cambios.
# Compatible con PostgreSQL y MySQL.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0017_alter_cliente_id_alter_direccion_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='direccion',
            name='latitud',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name='direccion',
            name='longitud',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name='direccion',
            name='ubicacion_origen',
            field=models.CharField(
                blank=True,
                choices=[('', 'Sin ubicar'), ('automatica', 'Verificada automáticamente'), ('manual', 'Confirmada a mano en el mapa')],
                default='',
                max_length=12,
            ),
        ),
    ]
