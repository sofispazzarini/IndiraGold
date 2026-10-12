# Escrita a mano a partir de "makemigrations --dry-run": solo agrega a Cambio los importes, el usuario y
# el identificador de operación de los cambios de ventas presenciales. No incluye los "alter id" que
# makemigrations agrega según la versión de Django.
# Compatible con PostgreSQL y MySQL: todos los campos admiten NULL (los cambios existentes quedan
# vacíos, sin recalcular nada) y el índice único de operacion_id admite varios NULL en ambos motores.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0041_configuracion_paquete'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='cambio',
            name='precio_devuelto',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='cambio',
            name='precio_entregado',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='cambio',
            name='diferencia',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='cambio',
            name='registrado_por',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cambios_registrados', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='cambio',
            name='operacion_id',
            field=models.CharField(blank=True, max_length=40, null=True, unique=True),
        ),
    ]
