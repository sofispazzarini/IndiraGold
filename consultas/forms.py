from django import forms
from .models import TemaConsulta, Consulta


class TemaConsultaForm(forms.ModelForm):
    class Meta:
        model = TemaConsulta
        fields = ['nombre', 'descripcion', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Título del tema'
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Descripción del tema'
            }),
            'activo': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }


class ConsultaForm(forms.ModelForm):
    class Meta:
        model = Consulta
        fields = ['tema', 'pregunta', 'respuesta', 'orden', 'activa']
        widgets = {
            'tema': forms.Select(attrs={'class': 'form-select'}),
            'pregunta': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': '¿Cuál es la pregunta?'
            }),
            'respuesta': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Respuesta a la pregunta'
            }),
            'orden': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0
            }),
            'activa': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
