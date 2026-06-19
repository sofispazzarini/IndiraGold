from django import forms
from .models import Cliente, Direccion
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


from .forms import PROVINCIAS, capitalizar_texto

class RegistroManualClienteForm(forms.ModelForm):
    dni = forms.CharField(label='DNI', max_length=8, required=True)
    email = forms.EmailField(label='Correo electrónico')
    nombre = forms.CharField(label='Nombre', max_length=150)
    apellido = forms.CharField(label='Apellido', max_length=150)
    telefono = forms.CharField(label='Teléfono', max_length=20)
    etiqueta = forms.CharField(label='Etiqueta', max_length=50)
    referencia = forms.CharField(label='Referencia', max_length=255, required=False)
    calle = forms.CharField(label='Calle', max_length=100)
    numero = forms.CharField(label='Número', max_length=10)
    ciudad = forms.CharField(label='Ciudad', max_length=50)
    provincia = forms.ChoiceField(choices=PROVINCIAS, label='Provincia')
    codigo_postal = forms.CharField(label='Código Postal', max_length=10)

    class Meta:
        model = Cliente
        fields = ['dni', 'telefono']


    def clean_dni(self):
        dni = self.cleaned_data['dni']
        if not dni.isdigit():
            raise forms.ValidationError("El DNI debe contener solo números.")
        if len(dni) not in [7, 8]:
            raise forms.ValidationError("El DNI debe tener 7 u 8 dígitos.")
        if User.objects.filter(username=dni).exists() or Cliente.objects.filter(dni=dni).exists():
            raise forms.ValidationError("Ya existe un cliente con este DNI.")
        return dni

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email=email).exists():
            raise ValidationError("Ya existe un usuario con este correo.")
        return email

    def clean_nombre(self):
        return capitalizar_texto(self.cleaned_data['nombre'])

    def clean_apellido(self):
        return capitalizar_texto(self.cleaned_data['apellido'])

    def clean_etiqueta(self):
        return capitalizar_texto(self.cleaned_data['etiqueta'])

    def clean_calle(self):
        return capitalizar_texto(self.cleaned_data['calle'])

    def clean_ciudad(self):
        return capitalizar_texto(self.cleaned_data['ciudad'])

    def clean_referencia(self):
        return capitalizar_texto(self.cleaned_data.get('referencia', ''))


class EditarClienteForm(forms.ModelForm):
    nombre = forms.CharField(label='Nombre completo', max_length=150)
    email = forms.EmailField(label='Correo electrónico', disabled=True)
    telefono = forms.CharField(label='Teléfono', max_length=20)

    class Meta:
        model = Cliente
        fields = ['telefono']

    def __init__(self, *args, **kwargs):
        user_instance = kwargs.pop('user_instance', None)
        super().__init__(*args, **kwargs)
        if user_instance:
            self.fields['nombre'].initial = user_instance.first_name
            self.fields['email'].initial = user_instance.email
        self.fields['nombre'].widget.attrs['class'] = 'form-control'
        self.fields['email'].widget.attrs['class'] = 'form-control'
        self.fields['telefono'].widget.attrs['class'] = 'form-control'

    def clean_email(self):
        email = self.cleaned_data['email']
        user_qs = User.objects.filter(email=email)
        if self.instance and self.instance.user:
            user_qs = user_qs.exclude(pk=self.instance.user.pk)
        if user_qs.exists():
            raise ValidationError('Ya existe un usuario con este correo.')
        return email


class NuevaDireccionForm(forms.ModelForm):
    class Meta:
        model = Direccion
        fields = ['etiqueta', 'calle', 'numero', 'ciudad', 'provincia', 'codigo_postal', 'referencia']
        widgets = {
            'etiqueta': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Casa, Trabajo'}),
            'calle': forms.TextInput(attrs={'class': 'form-control'}),
            'numero': forms.TextInput(attrs={'class': 'form-control'}),
            'ciudad': forms.TextInput(attrs={'class': 'form-control'}),
            'provincia': forms.TextInput(attrs={'class': 'form-control'}),
            'codigo_postal': forms.TextInput(attrs={'class': 'form-control'}),
            'referencia': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Porton verde, timbre roto'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        etiqueta = cleaned_data.get('etiqueta')
        calle = cleaned_data.get('calle')
        numero = cleaned_data.get('numero')
        ciudad = cleaned_data.get('ciudad')
        provincia = cleaned_data.get('provincia')
        codigo_postal = cleaned_data.get('codigo_postal')
        cliente = self.initial.get('cliente')
        if cliente:
            nueva_clave = Direccion.clave_unica(
                etiqueta,
                calle,
                numero,
                ciudad,
                provincia,
                codigo_postal,
                cleaned_data.get('referencia', ''),
            )
            for direccion in cliente.direcciones.all():
                if self.instance and self.instance.pk == direccion.pk:
                    continue
                if direccion.clave_normalizada == nueva_clave:
                    raise forms.ValidationError('Esta dirección ya está registrada para este cliente.')
        if False and Direccion.objects.filter(
            cliente=cliente,
            etiqueta=etiqueta,
            calle=calle,
            numero=numero,
            ciudad=ciudad,
            provincia=provincia,
            codigo_postal=codigo_postal
        ).exists():
            raise forms.ValidationError('Esta dirección ya está registrada para este cliente.')
        return cleaned_data

    def clean_etiqueta(self):
        return capitalizar_texto(self.cleaned_data['etiqueta'])

    def clean_calle(self):
        return capitalizar_texto(self.cleaned_data['calle'])

    def clean_ciudad(self):
        return capitalizar_texto(self.cleaned_data['ciudad'])

    def clean_provincia(self):
        return capitalizar_texto(self.cleaned_data['provincia'])

    def clean_referencia(self):
        return capitalizar_texto(self.cleaned_data.get('referencia', ''))
