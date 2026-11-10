"""Diagnóstico local, sin red, secretos, cambios de configuración o escrituras en BD."""
from urllib.parse import urlsplit

import django
from PIL import features
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Muestra seguridad y presencia de credenciales; nunca muestra sus valores ni llama APIs.'

    def handle(self, *args, **options):
        self.stdout.write(f'Django: {django.get_version()}')
        for nombre in ('DEBUG', 'SECURE_SSL_REDIRECT', 'CSRF_COOKIE_SECURE', 'SESSION_COOKIE_SECURE',
                       'CSRF_COOKIE_SAMESITE', 'SESSION_COOKIE_SAMESITE', 'CSRF_COOKIE_HTTPONLY',
                       'CSRF_USE_SESSIONS', 'SECURE_PROXY_SSL_HEADER', 'SECURE_REFERRER_POLICY',
                       'CSRF_TRUSTED_ORIGINS', 'ALLOWED_HOSTS'):
            self.stdout.write(f'{nombre}: {getattr(settings, nombre)}')
        self.stdout.write(f'SITE_URL esquema: {urlsplit(settings.SITE_URL).scheme}')
        for nombre in ('MERCADO_PAGO_ACCESS_TOKEN', 'MERCADO_PAGO_WEBHOOK_SECRET'):
            self.stdout.write(f'{nombre}: ' + ('presente (validez no comprobada)' if getattr(settings, nombre, '') else 'ausente'))
        self.stdout.write(f'Codificador WebP: {features.check("webp")}')
        self.stdout.write('No se consultó Mercado Pago ni se modificó ningún dato.')
