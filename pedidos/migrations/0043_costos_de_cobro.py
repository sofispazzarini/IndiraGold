# Escrita a mano a partir de "makemigrations --dry-run": solo los campos de costos de cobro. No incluye
# los "alter id" que makemigrations agrega según la versión de Django.
# - Pago: neto_recibido y retencion_mercado_pago pasan a admitir NULL (= la API no lo informó) y se
#   suman los cargos que paga la clienta y los otros descuentos. No cambia ningún valor guardado.
# - PagoVentaLocal: medio y retención de cada cobro (NULL en los cobros anteriores).
# - ConfiguracionPago: porcentaje propio para Mercado Pago en el local (0 hasta que se cargue).
# Compatible con PostgreSQL y MySQL: AddField/AlterField con campos estándar, sin SQL propio.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0042_cambio_importes_y_usuario'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pago',
            name='retencion_mercado_pago',
            field=models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=10, null=True),
        ),
        migrations.AlterField(
            model_name='pago',
            name='neto_recibido',
            field=models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='pago',
            name='cargos_cliente_mercado_pago',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='pago',
            name='otros_descuentos_mercado_pago',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='pagoventalocal',
            name='metodo_pago',
            field=models.CharField(blank=True, choices=[('efectivo', 'Efectivo'), ('mercado_pago', 'Mercado Pago'), ('mercado_pago_qr', 'Mercado Pago QR'), ('tarjeta', 'Tarjeta')], max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='pagoventalocal',
            name='retencion',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='configuracionpago',
            name='retencion_mercado_pago_presencial_porcentaje',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Porcentaje de retención para ventas del local cobradas con Mercado Pago', max_digits=5),
        ),
    ]
