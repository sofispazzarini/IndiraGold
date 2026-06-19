from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0023_configuracion_pago'),
    ]

    operations = [
        migrations.AddField(
            model_name='pago',
            name='mercado_pago_payment_id',
            field=models.CharField(blank=True, max_length=80, null=True),
        ),
        migrations.AddField(
            model_name='pago',
            name='cuotas',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='pago',
            name='retencion_mercado_pago',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='pago',
            name='neto_recibido',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='pago',
            name='detalle_mercado_pago',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
