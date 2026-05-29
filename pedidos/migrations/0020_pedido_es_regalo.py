from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0019_ventalocal_entrega_regalo'),
    ]

    operations = [
        migrations.AddField(
            model_name='pedido',
            name='es_regalo',
            field=models.BooleanField(default=False),
        ),
    ]
