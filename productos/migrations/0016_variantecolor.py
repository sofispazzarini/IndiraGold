from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('productos', '0015_alter_categoria_id_alter_categoriaorden_id_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='VarianteColor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('qr_code', models.CharField(blank=True, max_length=100, unique=True)),
                ('activo', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('color', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='productos.color')),
                ('variante', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='variante_colores', to='productos.variante')),
            ],
            options={
                'verbose_name': 'Variante Color',
                'verbose_name_plural': 'Variantes Color',
                'unique_together': {('variante', 'color')},
            },
        ),
    ]
