from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0011_alter_cliente_id_alter_direccion_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='direccion',
            name='etiqueta',
            field=models.CharField(default='Casa', max_length=50),
        ),
    ]
