from django import forms
from .models import Gasto, ConfiguracionEnvio


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
        fields = ['flex_gratis', 'precio_flex', 'zonas_flex']
        widgets = {
            'flex_gratis': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'precio_flex': forms.NumberInput(attrs={
                'class': 'envio-input',
                'step': '0.01',
                'min': '0',
                'placeholder': 'Ej: 2500',
            }),
            'zonas_flex': forms.Textarea(attrs={
                'class': 'envio-textarea',
                'rows': 7,
                'placeholder': 'Ej: CABA, La Plata, Quilmes, Berazategui',
            }),
        }
