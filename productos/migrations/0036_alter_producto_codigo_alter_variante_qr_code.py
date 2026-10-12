from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('productos', '0035_alter_categoria_id_alter_categoriaorden_id_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='variante',
            name='qr_code',
            field=models.CharField(blank=True, max_length=100, unique=True),
        ),
    ]
