# Escrita a mano a partir de "makemigrations --dry-run": solo crea el contador de códigos automáticos
# de producto (ART-0001...) y lo deja en el mayor número ART-XXXX que ya exista. No incluye los
# "alter id" que makemigrations agrega según la versión de Django.
# No modifica ningún producto: los códigos existentes quedan exactamente como están.
# Compatible con PostgreSQL y MySQL: CreateModel con clave primaria AutoField explícita e índice
# único en "nombre", y RunPython con el ORM (sin SQL propio).

import re

from django.db import migrations, models

PATRON_CODIGO = re.compile(r'^ART-(\d+)$', re.IGNORECASE)


def iniciar_secuencia(apps, schema_editor):
    Producto = apps.get_model('productos', 'Producto')
    SecuenciaCodigoProducto = apps.get_model('productos', 'SecuenciaCodigoProducto')
    mayor = 0
    for codigo in Producto.objects.filter(codigo__istartswith='ART-').values_list('codigo', flat=True):
        coincidencia = PATRON_CODIGO.match((codigo or '').strip())
        if coincidencia:
            mayor = max(mayor, int(coincidencia.group(1)))
    # get_or_create: si el contador ya existe se conserva (nunca vuelve atrás)
    SecuenciaCodigoProducto.objects.get_or_create(nombre='producto', defaults={'ultimo_numero': mayor})


class Migration(migrations.Migration):

    dependencies = [
        ('productos', '0036_alter_producto_codigo_alter_variante_qr_code'),
    ]

    operations = [
        migrations.CreateModel(
            name='SecuenciaCodigoProducto',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('nombre', models.CharField(max_length=30, unique=True)),
                ('ultimo_numero', models.PositiveIntegerField(default=0)),
            ],
            options={
                'verbose_name': 'Secuencia de códigos de producto',
                'verbose_name_plural': 'Secuencias de códigos de producto',
            },
        ),
        migrations.RunPython(iniciar_secuencia, migrations.RunPython.noop),
    ]
