"""Suite sobre PostgreSQL LOCAL, en una BD temporal nueva y distinta en cada ejecución."""
import uuid
from django.core.exceptions import ImproperlyConfigured
from .settings_test import *  # noqa: F403
from .settings import DATABASES as CONEXION_LOCAL

conexion = dict(CONEXION_LOCAL['default'])
if conexion['ENGINE'] != 'django.db.backends.postgresql' or conexion.get('HOST') not in ('localhost', '127.0.0.1', '::1'):
    raise ImproperlyConfigured('Esta suite solo admite PostgreSQL local; no apuntarla al servidor.')
conexion['NAME'] = 'postgres'
conexion['TEST'] = {'NAME': 'test_indiragold_' + uuid.uuid4().hex[:16]}
DATABASES = {'default': conexion}
