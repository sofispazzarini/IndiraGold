from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('pedidos', '0045_descuentos_metodo_pago')]
    operations = [migrations.AddField(
        model_name='pedido', name='mercado_pago_referencia',
        field=models.CharField(max_length=100, null=True, blank=True, unique=True, editable=False),
    )]
