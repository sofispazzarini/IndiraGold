# Escrita a mano a partir de "makemigrations --dry-run": solo suma "Transferencia" a los medios de pago
# de las ventas en el local (venta y cada cobro). No incluye los "alter id" que makemigrations agrega
# según la versión de Django. Solo cambian las opciones: no toca la base ni los valores guardados.

from django.db import migrations, models


METODOS_PAGO = [
    ('efectivo', 'Efectivo'),
    ('mercado_pago', 'Mercado Pago'),
    ('mercado_pago_qr', 'Mercado Pago QR'),
    ('tarjeta', 'Tarjeta'),
    ('transferencia', 'Transferencia'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0043_costos_de_cobro'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ventalocal',
            name='metodo_pago',
            field=models.CharField(choices=METODOS_PAGO, default='efectivo', max_length=20),
        ),
        migrations.AlterField(
            model_name='pagoventalocal',
            name='metodo_pago',
            field=models.CharField(blank=True, choices=METODOS_PAGO, max_length=20, null=True),
        ),
    ]
