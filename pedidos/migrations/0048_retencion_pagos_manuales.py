from django.db import migrations, models

ORIGENES = [('al_cobrar', 'Calculada al cobrar'), ('recalculada', 'Recalculada después')]


class Migration(migrations.Migration):
    """Solo agrega columnas nullable: no modifica filas existentes (NULL = retención no calculada)."""

    dependencies = [
        ('pedidos', '0047_descuentos_venta_local'),
    ]

    operations = [
        migrations.AddField(
            model_name='pagopedido',
            name='retencion_porcentaje',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AddField(
            model_name='pagopedido',
            name='retencion',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='pagopedido',
            name='retencion_origen',
            field=models.CharField(blank=True, choices=ORIGENES, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='pagoventalocal',
            name='retencion_porcentaje',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AddField(
            model_name='pagoventalocal',
            name='retencion_origen',
            field=models.CharField(blank=True, choices=ORIGENES, max_length=20, null=True),
        ),
    ]
