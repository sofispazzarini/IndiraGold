from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0013_direccion_referencia'),
        ('pedidos', '0018_pedido_deuda_pedido_es_presencial_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='ventalocal',
            name='direccion',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='users.direccion',
            ),
        ),
        migrations.AddField(
            model_name='ventalocal',
            name='es_regalo',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='ventalocal',
            name='metodo_entrega',
            field=models.CharField(
                choices=[('local', 'Retiro en local'), ('envio', 'Con envio')],
                default='local',
                max_length=20,
            ),
        ),
    ]
