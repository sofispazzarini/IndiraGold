from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('productos', '0021_oferta_categoria'),
    ]

    operations = [
        migrations.AddField(
            model_name='oferta',
            name='codigo',
            field=models.CharField(blank=True, max_length=40, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='oferta',
            name='es_cupon',
            field=models.BooleanField(default=False),
        ),
    ]
