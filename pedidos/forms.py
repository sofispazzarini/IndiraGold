from django import forms
from .models import Gasto, ConfiguracionEnvio, ConfiguracionPago


class GastoForm(forms.ModelForm):
    fecha = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))

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
            'flex_activo',
            'flex_gratis',
            'precio_flex',
            'zonas_flex',
            'correo_activo',
            'correo_gratis',
            'precio_correo',
        ]
        widgets = {
            'flex_activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'flex_gratis': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'correo_activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'correo_gratis': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'precio_flex': forms.NumberInput(attrs={
                'class': 'envio-input',
                'step': '0.01',
                'min': '0',
                'placeholder': 'Ej: 2500',
            }),
            'precio_correo': forms.NumberInput(attrs={
                'class': 'envio-input',
                'step': '0.01',
                'min': '0',
                'placeholder': 'Ej: 6500',
            }),
            'zonas_flex': forms.Textarea(attrs={
                'class': 'envio-textarea',
                'rows': 7,
                'placeholder': 'Ej: CABA, La Plata, Quilmes, Berazategui',
            }),
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
