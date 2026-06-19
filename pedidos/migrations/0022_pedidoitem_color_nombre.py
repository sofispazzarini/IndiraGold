from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0021_pedido_descuento'),
    ]

    operations = [
        migrations.AddField(
            model_name='pedidoitem',
            name='color_nombre',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
