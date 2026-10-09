from django import forms
from django.forms import modelformset_factory
from .models import Gasto, ConfiguracionEnvio, ConfiguracionPago, OpcionEnvioFlex


class GastoForm(forms.ModelForm):
    # format ISO: el <input type="date"> solo acepta AAAA-MM-DD (con el formato local quedaba vacío)
    fecha = forms.DateField(widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}))

    class Meta:
        model = Gasto
        fields = ['descripcion', 'monto', 'fecha', 'observaciones']
        widgets = {
            'descripcion': forms.TextInput(attrs={'class': 'form-control'}),
            'monto': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class ConfiguracionEnvioForm(forms.ModelForm):
    class Meta:
        model = ConfiguracionEnvio
        fields = [
            'correo_activo',
        ]
        widgets = {
            'correo_activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ConfiguracionPagoForm(forms.ModelForm):
    class Meta:
        model = ConfiguracionPago
        fields = [
            'mercado_pago_activo',
            'transferencia_activa',
            'titular_cuenta',
            'cuit_cuil',
            'cvu',
            'alias',
            'texto_mercado_pago',
            'texto_transferencia',
        ]
        widgets = {
            'mercado_pago_activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'transferencia_activa': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'titular_cuenta': forms.TextInput(attrs={'class': 'envio-input'}),
            'cuit_cuil': forms.TextInput(attrs={'class': 'envio-input'}),
            'cvu': forms.TextInput(attrs={'class': 'envio-input'}),
            'alias': forms.TextInput(attrs={'class': 'envio-input'}),
            'texto_mercado_pago': forms.TextInput(attrs={'class': 'envio-input'}),
            'texto_transferencia': forms.TextInput(attrs={'class': 'envio-input'}),
        }


class OpcionEnvioFlexForm(forms.ModelForm):
    class Meta:
        model = OpcionEnvioFlex
        fields = ['nombre', 'activo', 'es_gratis', 'precio', 'zonas', 'orden']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'envio-input',
                'placeholder': 'Ej: Flex Gratis CABA',
            }),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'es_gratis': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'precio': forms.NumberInput(attrs={
                'class': 'envio-input',
                'step': '1',
                'min': '0',
                'placeholder': 'Ej: 2500',
            }),
            'zonas': forms.Textarea(attrs={
                'class': 'envio-textarea',
                'rows': 3,
                'placeholder': 'Ej: CABA, Quilmes, Berazategui',
            }),
            'orden': forms.NumberInput(attrs={
                'class': 'envio-input envio-input-sm',
                'min': '0',
                'placeholder': '0',
            }),
        }

    def clean_nombre(self):
        # El modelo guarda el nombre en formato título: se valida igual para que "flex caba"
        # choque con "Flex Caba" acá (mensaje en el form) y no en la base (error 500)
        nombre = (self.cleaned_data.get('nombre') or '').strip().title()
        repetida = OpcionEnvioFlex.objects.filter(nombre__iexact=nombre)
        if self.instance.pk:
            repetida = repetida.exclude(pk=self.instance.pk)
        if repetida.exists():
            raise forms.ValidationError(f'Ya existe una opción de envío llamada "{nombre}".')
        return nombre


OpcionEnvioFlexFormSet = modelformset_factory(
    OpcionEnvioFlex,
    form=OpcionEnvioFlexForm,
    extra=1,
    can_delete=True,
)
