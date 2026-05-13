from django import forms
from .models import TipoMedida, Proveedor, Subcategoria, Producto, Categoria

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
    activo = forms.BooleanField(
        required=False, 
        initial=True, 
        label="Producto Visible en Tienda",
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input', 
            'role': 'switch',
            'id': 'flexSwitchCheckChecked' # Ayuda a que el label lo active al hacer clic
        })
    )
    def __init__(self, *args, **kwargs):
        super(ProductoForm, self).__init__(*args, **kwargs)
        # Hacemos que no sean obligatorios en el form porque los llenamos en la view
        self.fields['activo'].initial = True
        if 'categoria' in self.fields:
            self.fields['categoria'].required = False
        if 'subcategoria' in self.fields:
            self.fields['subcategoria'].required = False
   
    class Meta:
        model = Producto
        fields = [
            'codigo', 'nombre', 'tipo', 'tela', 'temporada', 
            'descripcion', 'avios', 'etiquetas', 'precio', 
            'stock', 'categoria', 'subcategoria', 'proveedor', 'activo','imagen_tecnica'
        ]
        error_messages = {
            'codigo': {
                'unique': "Ya existe un producto cargado con este Código/Artículo. Por favor, verificá e ingresá uno distinto.",
            },
        }
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
            'temporada': forms.TextInput(attrs={'class': 'form-control'}),
            'avios': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'etiquetas': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'imagen_tecnica': forms.ClearableFileInput(attrs={'class': 'd-none', 'id': 'id_imagen_tecnica'}),
            'etiquetas': forms.Textarea(attrs={'class': 'ficha-textarea flex-grow-1', 'id': 'id_etiquetas'}),
        }

    def clean_imagen(self):
        imagen = self.cleaned_data.get('imagen', False)
        clear = self.files.get('imagen-clear') or self.data.get('imagen-clear')
        if imagen and clear:
            raise forms.ValidationError('Por favor, sube una nueva imagen o marca la casilla de borrar, pero no ambas opciones a la vez.')
        return imagen
    def _post_clean(self):
        super()._post_clean()
        # Personalizar el mensaje de error de imagen
        if 'imagen' in self.errors:
            for i, err in enumerate(self.errors['imagen']):
                if 'Please either submit a file or check the clear checkbox, not both.' in err:
                    self.errors['imagen'][i] = 'Por favor, sube una nueva imagen o marca la casilla de borrar, pero no ambas opciones a la vez.'
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
from .models import Variante # Asegurate de importarlo arriba

class VarianteForm(forms.ModelForm):
    class Meta:
        model = Variante
        fields = ['talle'] # SOLO DEJAMOS EL TALLE
        widgets = {
            'talle': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: S, M, XL, 42, Único...'}),
        }

from .models import CategoriaOrden

class CategoriaOrdenForm(forms.ModelForm):
    class Meta:
        model = CategoriaOrden
        fields = ['nombre', 'descripcion', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre de la categoría'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Descripción opcional'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }