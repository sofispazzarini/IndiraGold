from django import forms
from .models import SlideCarrousel


class SlideCarrouselForm(forms.ModelForm):
    class Meta:
        model = SlideCarrousel
        fields = ['imagen', 'titulo', 'subtitulo', 'link', 'orden', 'activo']
        widgets = {
            'titulo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Título (opcional)'}),
            'subtitulo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Subtítulo (opcional)'}),
            'link': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://...'}),
            'orden': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
