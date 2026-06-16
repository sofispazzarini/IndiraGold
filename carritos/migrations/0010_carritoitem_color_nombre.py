from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('carritos', '0009_alter_carrito_id_alter_carritoitem_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='carritoitem',
            name='color_nombre',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
