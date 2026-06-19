from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('productos', '0020_alter_categoria_id_alter_categoriaorden_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='oferta',
            name='categoria',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='ofertas',
                to='productos.categoria',
            ),
        ),
    ]
