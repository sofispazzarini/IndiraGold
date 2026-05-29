from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0020_pedido_es_regalo'),
    ]

    operations = [
        migrations.AddField(
            model_name='pedido',
            name='codigo_descuento',
            field=models.CharField(blank=True, max_length=40, null=True),
        ),
        migrations.AddField(
            model_name='pedido',
            name='descuento_monto',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='pedido',
            name='descuento_porcentaje',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
