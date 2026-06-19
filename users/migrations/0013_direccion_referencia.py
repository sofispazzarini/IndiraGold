from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0012_direccion_etiqueta'),
    ]

    operations = [
        migrations.AddField(
            model_name='direccion',
            name='referencia',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
