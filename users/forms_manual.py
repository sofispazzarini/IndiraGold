from django import forms
from .models import Cliente, Direccion
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


from .forms import PROVINCIAS

class RegistroManualClienteForm(forms.ModelForm):
    dni = forms.CharField(label='DNI', max_length=8, required=True)
    email = forms.EmailField(label='Correo electrónico')
    nombre = forms.CharField(label='Nombre completo', max_length=150)
    telefono = forms.CharField(label='Teléfono', max_length=20)
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
        if Cliente.objects.filter(dni=dni).exists():
            raise forms.ValidationError("Ya existe un cliente con este DNI.")
        return dni

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email=email).exists():
            raise ValidationError("Ya existe un usuario con este correo.")
        return email
