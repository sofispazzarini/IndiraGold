from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0024_pago_mercado_pago_detalle'),
    ]

    operations = [
        migrations.AddField(
            model_name='configuracionenvio',
            name='correo_activo',
            field=models.BooleanField(default=False, help_text='Mostrar Andreani/Correo Argentino como opcion en el checkout'),
        ),
        migrations.AddField(
            model_name='configuracionenvio',
            name='correo_gratis',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='configuracionenvio',
            name='precio_correo',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.CreateModel(
            name='EnvioPedido',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('proveedor', models.CharField(choices=[('andreani', 'Andreani'), ('correo_argentino', 'Correo Argentino'), ('flex', 'Envio Flex')], max_length=30)),
                ('tipo_entrega', models.CharField(choices=[('domicilio', 'A domicilio'), ('sucursal', 'Retiro en sucursal')], default='domicilio', max_length=20)),
                ('estado', models.CharField(choices=[('pendiente', 'Pendiente de generar etiqueta'), ('etiqueta_generada', 'Etiqueta generada'), ('despachado', 'Despachado'), ('en_transito', 'En transito'), ('entregado', 'Entregado'), ('error', 'Error al generar envio')], default='pendiente', max_length=30)),
                ('costo', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('tracking', models.CharField(blank=True, max_length=120, null=True)),
                ('sucursal', models.CharField(blank=True, max_length=255, null=True)),
                ('etiqueta', models.FileField(blank=True, null=True, upload_to='etiquetas_envio/')),
                ('respuesta_api', models.JSONField(blank=True, default=dict)),
                ('error', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('pedido', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='envio', to='pedidos.pedido')),
            ],
        ),
    ]
