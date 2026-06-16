from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('productos', '0022_oferta_codigo_cupon'),
    ]

    operations = [
        migrations.AddField(
            model_name='producto',
            name='tamano_paquete',
            field=models.CharField(
                choices=[
                    ('chico', 'Chico'),
                    ('mediano', 'Mediano'),
                    ('grande', 'Grande'),
                ],
                default='mediano',
                max_length=20,
            ),
        ),
    ]
