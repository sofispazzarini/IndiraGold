from django import forms
from .models import TipoMedida, Proveedor

# Formulario para tipos de medida globales
class TipoMedidaForm(forms.ModelForm):
    class Meta:
        model = TipoMedida
        fields = ['nombre', 'descripcion']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre de la medida'}),
            'descripcion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Descripción opcional'}),
        }

# Formulario para proveedor con selección de medidas
class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ['nombre', 'telefono', 'informacion_adicional']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control'}),
            'informacion_adicional': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Otra información opcional'}),
        }
from django import forms
from .models import Subcategoria
class SubcategoriaSoloNombreForm(forms.ModelForm):
    class Meta:
        model = Subcategoria
        fields = ['nombre']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre de la subcategoría'})
        }

    def __init__(self, *args, **kwargs):
        self.categoria = kwargs.pop('categoria', None)
        super().__init__(*args, **kwargs)

    def clean_nombre(self):
        nombre = self.cleaned_data['nombre'].strip()
        if self.categoria:
            if Subcategoria.objects.filter(nombre__iexact=nombre, categoria=self.categoria).exists():
                raise forms.ValidationError('Ya existe una subcategoría con ese nombre en esta categoría.')
        return nombre

from django import forms
from .models import Producto

class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = ['codigo', 'nombre', 'tipo', 'tela', 'descripcion', 'precio', 'stock', 'categoria', 'subcategoria', 'proveedor', 'activo']
        widgets = {
            'codigo': forms.TextInput(attrs={'class': 'form-control'}),
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'tipo': forms.TextInput(attrs={'class': 'form-control'}),
            'tela': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'precio': forms.NumberInput(attrs={'class': 'form-control'}),
            'stock': forms.NumberInput(attrs={'class': 'form-control'}),
            'categoria': forms.Select(attrs={'class': 'form-control'}),
            'subcategoria': forms.Select(attrs={'class': 'form-control'}),
            'proveedor': forms.Select(attrs={'class': 'form-control'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
from django import forms
from .models import Categoria, Subcategoria

class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ['nombre']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre de la categoría'})
        }

    def clean_nombre(self):
        nombre = self.cleaned_data['nombre'].strip()
        if Categoria.objects.filter(nombre__iexact=nombre).exists():
            raise forms.ValidationError("Ya existe una categoría con ese nombre.")
        return nombre

class SubcategoriaForm(forms.ModelForm):
    class Meta:
        model = Subcategoria
        fields = ['categoria', 'nombre']
        widgets = {
            'categoria': forms.Select(attrs={'class': 'form-control'}),
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre de la subcategoría'})
        }
