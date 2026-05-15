# Generated manually on 2026-05-14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0016_configuracionenvio'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pedido',
            name='metodo_entrega',
            field=models.CharField(choices=[('local', 'Retiro en Local (Gratis)'), ('flex', 'Envio Flex'), ('correo', 'Envio por Correo')], default='local', max_length=20),
        ),
        migrations.AddField(
            model_name='configuracionenvio',
            name='flex_activo',
            field=models.BooleanField(default=True, help_text='Mostrar Envio Flex como opcion en el checkout'),
        ),
        migrations.AlterField(
            model_name='configuracionenvio',
            name='zonas_flex',
            field=models.TextField(blank=True, help_text='Separar zonas con coma. Ej: CABA, La Plata, Quilmes'),
        ),
    ]
