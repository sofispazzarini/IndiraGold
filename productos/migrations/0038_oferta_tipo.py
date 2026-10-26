# Escrita a mano a partir de "makemigrations --dry-run": solo agrega Oferta.tipo (descuento/aumento).
# No incluye los "alter id" que makemigrations agrega según la versión de Django.
# Las ofertas y cupones existentes quedan como "descuento", es decir, igual que ahora.
# Compatible con PostgreSQL y MySQL: AddField con default (sin SQL propio).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('productos', '0037_secuencia_codigo_producto'),
    ]

    operations = [
        migrations.AddField(
            model_name='oferta',
            name='tipo',
            field=models.CharField(
                choices=[('descuento', 'Descuento'), ('aumento', 'Aumento')],
                default='descuento',
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name='oferta',
            name='descuento',
            field=models.PositiveIntegerField(help_text='Porcentaje de descuento o de aumento, según el tipo'),
        ),
    ]
