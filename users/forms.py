from django import forms
from django.contrib.auth.models import User
from .models import Cliente, Direccion
from django.core.exceptions import ValidationError
from django.db import transaction


def capitalizar_texto(value):
    return " ".join(part.capitalize() for part in (value or "").strip().split())


PROVINCIAS = [
    ("", "Seleccioná una provincia"),
    ("Buenos Aires", "Buenos Aires"),
    ("CABA", "Ciudad Autónoma de Buenos Aires"),
    ("Catamarca", "Catamarca"),
    ("Chaco", "Chaco"),
    ("Chubut", "Chubut"),
    ("Córdoba", "Córdoba"),
    ("Corrientes", "Corrientes"),
    ("Entre Ríos", "Entre Ríos"),
    ("Formosa", "Formosa"),
    ("Jujuy", "Jujuy"),
    ("La Pampa", "La Pampa"),
    ("La Rioja", "La Rioja"),
    ("Mendoza", "Mendoza"),
    ("Misiones", "Misiones"),
    ("Neuquén", "Neuquén"),
    ("Río Negro", "Río Negro"),
    ("Salta", "Salta"),
    ("San Juan", "San Juan"),
    ("San Luis", "San Luis"),
    ("Santa Cruz", "Santa Cruz"),
    ("Santa Fe", "Santa Fe"),
    ("Santiago del Estero", "Santiago del Estero"),
    ("Tierra del Fuego", "Tierra del Fuego"),
    ("Tucumán", "Tucumán"),
]
class RegistroUsuarioForm(forms.ModelForm):
    nombre = forms.CharField(label='Nombre', max_length=150)
    apellido = forms.CharField(label='Apellido', max_length=150)
    email = forms.EmailField(label='Correo electrónico')
    password1 = forms.CharField(label='Contraseña', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirmar contraseña', widget=forms.PasswordInput)

    dni = forms.CharField(label='DNI', max_length=8)
    telefono = forms.CharField(label='Teléfono', max_length=20)

    # 🔹 Campos de dirección
    etiqueta = forms.CharField(label='Etiqueta', max_length=50)
    calle = forms.CharField(label='Calle', max_length=100)
    numero = forms.CharField(label='Número', max_length=10)
    ciudad = forms.CharField(label='Ciudad', widget=forms.Select(attrs={'id': 'id_ciudad'}))
    codigo_postal = forms.CharField(label='Código Postal', max_length=10)
    referencia = forms.CharField(label='Referencia', max_length=255, required=False)
    provincia = forms.ChoiceField(
        choices=PROVINCIAS,
        label="Provincia"
    )
    class Meta:
        model = Cliente
        fields = ['dni', 'telefono']
    def clean_codigo_postal(self):
        cp = self.cleaned_data['codigo_postal']

        if not cp.isdigit():
            raise forms.ValidationError("El código postal debe contener solo números.")

        if len(cp) != 4:
            raise forms.ValidationError("El código postal debe tener 4 dígitos.")

        return cp
    def clean_dni(self):
        dni = self.cleaned_data['dni']

        if not dni.isdigit():
            raise forms.ValidationError("El DNI debe contener solo números.")

        if len(dni) not in [7, 8]:
            raise forms.ValidationError("El DNI debe tener 7 u 8 dígitos.")

        if User.objects.filter(username=dni).exists() or Cliente.objects.filter(dni=dni).exists():
            raise forms.ValidationError("Ya existe un cliente con este DNI.")

        return dni
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

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email=email).exists():
            raise ValidationError("Ya existe un usuario con este correo.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("password1") != cleaned_data.get("password2"):
            raise ValidationError("Las contraseñas no coinciden.")
        return cleaned_data
    @transaction.atomic #esto hace que si falla el guardado de la direccion, no se crea ningun user ni cliente
    def save(self, commit=True):
        dni = self.cleaned_data['dni']
        nombre = self.cleaned_data['nombre']
        apellido = self.cleaned_data['apellido']

        # Crear usuario
        user = User.objects.create_user(
            username=dni,
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password1'],
            first_name=nombre,
            last_name=apellido
        )

        # Crear cliente
        cliente = Cliente.objects.create(
            user=user,
            dni=dni,
            telefono=self.cleaned_data['telefono']
        )

        # 🔹 Crear dirección asociada
        Direccion.objects.create(
            cliente=cliente,
            etiqueta=self.cleaned_data['etiqueta'],
            calle=self.cleaned_data['calle'],
            numero=self.cleaned_data['numero'],
            ciudad=self.cleaned_data['ciudad'],
            provincia=self.cleaned_data['provincia'],
            codigo_postal=self.cleaned_data['codigo_postal'],
            referencia=self.cleaned_data.get('referencia', '')
        )

        return cliente
