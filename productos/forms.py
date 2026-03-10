from django import forms
from .models import Producto

class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        # Esto incluirá todos los campos de tu modelo en el formulario
        fields = '__all__'