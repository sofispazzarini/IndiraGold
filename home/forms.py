from django import forms
from django.core.files.uploadedfile import UploadedFile

from config.imagenes import optimizar_imagen
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

    def clean_imagen(self):
        imagen = self.cleaned_data.get('imagen')
        # Al editar sin elegir otra imagen queda la actual, que no se vuelve a procesar
        if not isinstance(imagen, UploadedFile):
            return imagen
        lista, error = optimizar_imagen(imagen)
        if error:
            raise forms.ValidationError(error)
        return lista
