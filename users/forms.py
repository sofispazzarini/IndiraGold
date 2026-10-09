import re

from django import forms
from django.contrib.auth.models import User
from .models import Cliente, Direccion
from django.core.exceptions import ValidationError
from django.db import transaction


def capitalizar_texto(value):
    return " ".join(part.capitalize() for part in (value or "").strip().split())


# Letras (con acentos y ñ), espacios, apóstrofos y guiones: "María José", "O'Connor", "Pérez-Gil"
PATRON_NOMBRE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ' .\-]+$")
# Solo números, con un + opcional al principio (ej. +5492216375660)
PATRON_TELEFONO = re.compile(r"^\+?\d{6,15}$")


def validar_nombre_persona(valor, campo='nombre', maximo=50):
    """Nombre o apellido: obligatorio, sin números ni símbolos, hasta `maximo` caracteres."""
    valor = capitalizar_texto(valor)
    if not valor:
        raise ValidationError(f'Ingresá el {campo}.')
    if len(valor) > maximo:
        raise ValidationError(f'El {campo} no puede tener más de {maximo} caracteres.')
    if not PATRON_NOMBRE.match(valor):
        raise ValidationError(f'El {campo} solo puede tener letras, espacios, apóstrofos o guiones.')
    return valor


def validar_telefono(valor):
    """Teléfono: números con un + opcional adelante. Espacios, guiones y paréntesis se quitan."""
    valor = re.sub(r"[\s\-()]", "", valor or "")
    if not PATRON_TELEFONO.match(valor):
        raise ValidationError('El teléfono solo puede tener números (y un + al principio), entre 6 y 15 dígitos.')
    return valor


def normalizar_email(email):
    """Los emails se guardan siempre en minúsculas: "Ana@Mail.com" y "ana@mail.com" son el mismo."""
    return (email or "").strip().lower()


def email_en_uso(email, excluir_user_id=None):
    """Si otro usuario ya tiene ese email, sin distinguir mayúsculas (cubre los guardados antes en mayúsculas)."""
    usuarios = User.objects.filter(email__iexact=normalizar_email(email))
    if excluir_user_id:
        usuarios = usuarios.exclude(pk=excluir_user_id)
    return usuarios.exists()


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
def normalizar_provincia(value):
    """Devuelve la provincia con el valor exacto del select (ej. "caba" o "Ciudad Autónoma..."
    -> "CABA", "santiago del estero" -> "Santiago del Estero"). Si no coincide, la deja como vino."""
    texto = " ".join((value or "").strip().split())
    for valor, etiqueta in PROVINCIAS:
        if valor and texto.casefold() in (valor.casefold(), etiqueta.casefold()):
            return valor
    return texto


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

    def __init__(self, *args, password_hash=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Confirmación final del registro: la contraseña llega ya hasheada desde la sesión
        # (nunca se guarda en claro en django_session)
        self.password_hash = password_hash
        if password_hash:
            self.fields['password1'].required = False
            self.fields['password2'].required = False

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
        return validar_nombre_persona(self.cleaned_data['nombre'], 'nombre')

    def clean_apellido(self):
        return validar_nombre_persona(self.cleaned_data['apellido'], 'apellido')

    def clean_telefono(self):
        return validar_telefono(self.cleaned_data['telefono'])

    def clean_etiqueta(self):
        return capitalizar_texto(self.cleaned_data['etiqueta'])

    def clean_calle(self):
        return capitalizar_texto(self.cleaned_data['calle'])

    def clean_ciudad(self):
        return capitalizar_texto(self.cleaned_data['ciudad'])

    def clean_referencia(self):
        return capitalizar_texto(self.cleaned_data.get('referencia', ''))

    def clean_email(self):
        email = normalizar_email(self.cleaned_data['email'])
        if email_en_uso(email):
            raise ValidationError("Ya existe un usuario con este correo.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        if not self.password_hash and cleaned_data.get("password1") != cleaned_data.get("password2"):
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
            password=None if self.password_hash else self.cleaned_data['password1'],
            first_name=nombre,
            last_name=apellido
        )
        if self.password_hash:
            user.password = self.password_hash
            user.save(update_fields=['password'])

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
