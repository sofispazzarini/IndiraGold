from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('productos', '0016_variantecolor'),
    ]

    operations = [
        migrations.AddField(
            model_name='categoriaorden',
            name='activo',
            field=models.BooleanField(default=True),
        ),
        migrations.AlterModelOptions(
            name='categoriaorden',
            options={'verbose_name': 'Categoría de Orden', 'verbose_name_plural': 'Categorías de Orden'},
        ),
    ]
