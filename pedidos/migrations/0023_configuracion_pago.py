from django.db import migrations, models
import django.db.models.deletion


def crear_configuracion_pago(apps, schema_editor):
    ConfiguracionPago = apps.get_model('pedidos', 'ConfiguracionPago')
    PlanCuotasMercadoPago = apps.get_model('pedidos', 'PlanCuotasMercadoPago')
    configuracion, _ = ConfiguracionPago.objects.get_or_create(pk=1)
    planes = [
        (2, '9.49', True, True, 0),
        (3, '12.19', True, True, 1),
        (6, '19.09', False, False, 2),
        (9, '27.29', False, False, 3),
        (12, '32.29', False, False, 4),
        (18, '41.59', False, False, 5),
    ]
    for cuotas, retencion, sin_interes, activo, orden in planes:
        PlanCuotasMercadoPago.objects.get_or_create(
            configuracion=configuracion,
            cuotas=cuotas,
            defaults={
                'retencion_porcentaje': retencion,
                'sin_interes': sin_interes,
                'activo': activo,
                'orden': orden,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0022_pedidoitem_color_nombre'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConfiguracionPago',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mercado_pago_activo', models.BooleanField(default=True)),
                ('transferencia_activa', models.BooleanField(default=True)),
                ('titular_cuenta', models.CharField(default='Yazmin Miranda Capitanio', max_length=150)),
                ('cuit_cuil', models.CharField(default='27-39554727-0', max_length=30)),
                ('cvu', models.CharField(default='0000003100042870767609', max_length=60)),
                ('alias', models.CharField(default='indiragold.', max_length=80)),
                ('texto_mercado_pago', models.CharField(default='Podes pagar con dinero en cuenta, tarjeta de debito o credito desde Mercado Pago.', max_length=255)),
                ('texto_transferencia', models.CharField(default='Transferi el monto exacto y envianos el comprobante por WhatsApp.', max_length=255)),
            ],
        ),
        migrations.CreateModel(
            name='PlanCuotasMercadoPago',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cuotas', models.PositiveIntegerField()),
                ('sin_interes', models.BooleanField(default=True)),
                ('retencion_porcentaje', models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ('activo', models.BooleanField(default=True)),
                ('orden', models.PositiveIntegerField(default=0)),
                ('configuracion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='planes_cuotas', to='pedidos.configuracionpago')),
            ],
            options={
                'ordering': ['orden', 'cuotas'],
            },
        ),
        migrations.RunPython(crear_configuracion_pago, migrations.RunPython.noop),
    ]
