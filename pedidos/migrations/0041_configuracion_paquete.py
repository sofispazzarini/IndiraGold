# Escrita a mano a partir de "makemigrations --dry-run": solo crea ConfiguracionPaquete y carga los tres
# tamaños. No incluye los "alter id" que makemigrations agrega según la versión de Django.
# Compatible con PostgreSQL y MySQL: solo CreateModel con campos estándar (clave primaria AutoField
# explícita, índice único en "tamano") y RunPython con el ORM; sin SQL propio ni CheckConstraint.

import django.core.validators
from django.db import migrations, models


# Valores que la app usaba fijos en pedidos/servicios_envio.py (PAQUETES_ENVIO) hasta esta versión. Se
# cargan una sola vez para que las cotizaciones no cambien al migrar; después se editan desde el admin.
PAQUETES_INICIALES = [
    # (tamaño, peso en gramos, alto, ancho, largo en cm)
    ('chico', 200, 3, 20, 25),
    ('mediano', 400, 5, 25, 35),
    ('grande', 800, 10, 35, 45),
]


def cargar_paquetes(apps, schema_editor):
    ConfiguracionPaquete = apps.get_model('pedidos', 'ConfiguracionPaquete')
    for tamano, peso, alto, ancho, largo in PAQUETES_INICIALES:
        # get_or_create: si ya estaba cargado (por ejemplo a mano), se conserva lo que haya
        ConfiguracionPaquete.objects.get_or_create(
            tamano=tamano,
            defaults={'peso_gramos': peso, 'alto_cm': alto, 'ancho_cm': ancho, 'largo_cm': largo},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0040_merge_20261011_1001'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConfiguracionPaquete',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('tamano', models.CharField(choices=[('chico', 'Chico - accesorios, remeras, tops'), ('mediano', 'Mediano - buzos, pantalones, vestidos'), ('grande', 'Grande - camperas, zapatillas, abrigos')], error_messages={'unique': 'Ya existe una configuración para ese tamaño de paquete.'}, max_length=20, unique=True, verbose_name='Tamaño')),
                ('peso_gramos', models.PositiveIntegerField(help_text='Peso total del paquete ya embalado, en gramos.', validators=[django.core.validators.MinValueValidator(1, message='El peso tiene que ser mayor que 0.')], verbose_name='Peso embalado (g)')),
                ('alto_cm', models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1, message='El alto tiene que ser mayor que 0.')], verbose_name='Alto (cm)')),
                ('ancho_cm', models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1, message='El ancho tiene que ser mayor que 0.')], verbose_name='Ancho (cm)')),
                ('largo_cm', models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1, message='El largo tiene que ser mayor que 0.')], verbose_name='Largo (cm)')),
            ],
            options={
                'verbose_name': 'Paquete de envío',
                'verbose_name_plural': 'Paquetes de envío',
                'ordering': ['id'],
            },
        ),
        migrations.RunPython(cargar_paquetes, migrations.RunPython.noop),
    ]
