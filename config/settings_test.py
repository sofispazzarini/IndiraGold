"""Pruebas aisladas: nunca utiliza BD, credenciales, correo ni media de producción."""
from .settings import *  # noqa: F403

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
SECRET_KEY = 'solo-para-pruebas-locales-no-usar-en-produccion'
DEBUG = False
SECURE_SSL_REDIRECT = False
SECURE_PROXY_SSL_HEADER = None
ALLOWED_HOSTS = ['testserver', 'indiragold.com.ar', 'www.indiragold.com.ar']
SITE_URL = 'https://www.indiragold.com.ar'
MERCADO_PAGO_ACCESS_TOKEN = 'TEST-sin-acceso-a-red'
MERCADO_PAGO_WEBHOOK_SECRET = ''
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
# Los tests de archivos deben usar TemporaryDirectory + override_settings(MEDIA_ROOT=...).
MEDIA_ROOT = BASE_DIR / '.test-media'  # noqa: F405
