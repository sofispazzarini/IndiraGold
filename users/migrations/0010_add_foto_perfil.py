from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0009_alter_cliente_id_alter_direccion_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='foto_perfil',
            field=models.ImageField(blank=True, null=True, upload_to='perfiles/'),
        ),
    ]
