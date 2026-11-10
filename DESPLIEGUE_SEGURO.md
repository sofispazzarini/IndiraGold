# IndiraGold: diagnóstico y despliegue del 10/11/2026

## Qué está confirmado

- Los POST fallidos del access.log de Instagram usan **HTTP con www**. El error.log correspondiente dice `CSRF cookie not set`. La comprobación pública del 10/11/2026, aproximadamente 15:53 de Argentina, obtuvo:

  | Entrada al login | Respuesta |
  | --- | --- |
  | `http://indiragold.com.ar/users/login/` | 301 a HTTPS con www, servido por Cloudflare |
  | `https://indiragold.com.ar/users/login/` | 301 a HTTPS con www, servido por Cloudflare |
  | `http://www.indiragold.com.ar/users/login/` | **200**, servido por PythonAnywhere, cookie CSRF con `Secure` |
  | `https://www.indiragold.com.ar/users/login/` | 200, cookie CSRF con `Secure` |

  Una cookie Secure no se establece/envía normalmente por HTTP. La tienda estaba sirviendo formularios por un transporte donde sus cookies no funcionan. No es necesario permitir Instagram como origen CSRF ni desactivar Secure/SameSite para solucionarlo.
- Login, registro, confirmar dirección, checkout y formularios del carrito contienen tokens. Una revisión de todos los bloques `<form method=post>` del repositorio no encontró bloques sin token. Hay formularios construidos por JS, además de los HTML: el script común actualiza cuerpo y encabezado de los fetch del mismo origen.
- El carrito reenviaba el formulario después de errores de fetch, incluidos los 403. Los pares de POST rechazados del log coinciden con ese comportamiento. Ahora muestra el error y no repite una operación cuyo resultado podría ser incierto.
- Mercado Pago rechazó una preferencia con `unit_price invalid` el 07/11. Se puede reproducir un precio cero en una línea con descuento del 100% o redondeo a cero. Las líneas se validan y agrupan por el total positivo cuando hace falta. **No se conoce el payload de aquel intento**, así que esa causa concreta del rechazo histórico sigue sin demostrarse. Tampoco hay evidencia en los logs entregados de credenciales inválidas.
- Antes no había receptor de webhooks ni `notification_url`: si el cliente cerraba Mercado Pago sin volver, no se confirmaba automáticamente el pedido reservado.
- Las tarjetas servían originales y el log muestra PNG de 12–27 MB. También hay muchas consultas repetidas del catálogo; se precargan imágenes, talles y colores sin modificar filtros ni reglas de stock.

## Hipótesis y límites

- `CSRF token from POST incorrect` en confirmar dirección indica un token distinto del de la cookie/sesión. Rotación al iniciar sesión, otra pestaña o HTML antiguo son hipótesis; no hay evidencia que identifique cuál ocurrió. El script toma la cookie vigente al enviar y las respuestas con formularios no se cachean.
- Los rechazos `no Referer` de `/` cercanos a exploraciones de `.env`/`.git` pueden ser sondeos automáticos. Se conserva la validación de Origin/Referer; no se aceptan POST sin procedencia válida.
- Un 499 y `OSError: write error` son compatibles con conexiones cerradas por el cliente/proxy. No prueban corrupción de datos ni un error de Django. El HTML de la home también tarda segundos en varios ejemplos: las imágenes no explican por sí solas ese tiempo. Se redujeron consultas repetidas; hace falta medir de nuevo en el servidor.
- Los 404 de archivos de producto/carrousel existentes requieren comprobar el mapeo `/media/`, MEDIA_ROOT y backups. Este cambio no inventa ni reemplaza imágenes faltantes.
- No se accedió al settings, WSGI, variables ni base de PythonAnywhere. La existencia de una variable local no verifica su valor ni su validez en el servidor. No se ejecutaron pagos reales.
- No se puede certificar Safari/Instagram reales desde una simulación de navegador. Repetir la comprobación manual en iPhone y Android después de desplegar.

## Cambios y archivos

| Archivos | Cambio |
| --- | --- |
| `config/settings.py`, `.env.example` | HTTPS obligatorio por defecto con DEBUG=False; proxy opcional; error CSRF; secreto de webhook por entorno. Sin ampliar dominios/cookies a comodines. |
| `config/middleware.py`, `config/seguridad.py`, `templates/403_csrf.html` | HTML con cookies y zonas de cuenta sin caché; 403 JSON para AJAX y recarga mediante GET para formularios. |
| `home/static/home/csrf.js`, `templates/base.html`, `templates/base_publica.html`, `templates/basico.html` | Token vigente en formularios y fetch del mismo origen; nunca se envía a APIs externas. Sin reintentos automáticos de POST. |
| `home/templates/home_publico.html`, `productos/templates/productos/producto_detalle.html` | No reenviar carrito tras errores de red o rechazo. |
| `users/views.py` | Eliminar exención CSRF de la verificación de email: su JS ya mandaba el token. |
| `pedidos/mercado_pago.py`, `pedidos/views.py`, `pedidos/urls.py` | Validación de precios/URLs; manejar fallos de transporte; webhook HMAC; confirmación compartida con bloqueo del pedido. |
| `pedidos/models.py`, `pedidos/migrations/0046_pedido_mercado_pago_referencia.py` | Referencia exacta persistida del intento de pago, única y nullable para conservar pedidos existentes. |
| `productos/imagenes.py`, `productos/models.py`, `productos/templatetags/imagenes_producto.py` | Copias WebP de 480/960/1600 px, EXIF corregido, transparencia, originales conservados. |
| `productos/management/commands/optimizar_imagenes_productos.py` | Procesamiento manual por lotes, simulación por defecto; no cambia BD ni elimina archivos. |
| `home/templates/home/_tarjeta_producto.html`, `productos/templates/productos/productos_por_subcategoria.html`, `productos/views.py` | Imágenes reducidas en catálogo y AJAX, srcset y lazy loading. El detalle principal no lleva lazy. |
| `home/views.py`, `productos/models.py` | Aprovechar la precarga de imágenes/variantes; conservar elección de portada y cálculo del stock. |
| `pedidos/management/commands/diagnosticar_tienda.py` | Diagnóstico sin secretos, sin red y sin cambios de datos. |
| `config/settings_test*.py`, `config/tests_seguridad.py`, `pedidos/tests_mercado_pago.py`, `productos/tests_imagenes.py`, `tests/frontend.test.cjs` | Entornos aislados y nuevas pruebas de regresión. |
| `pedidos/tests.py`, `pedidos/tests_costos_cobro.py`, `tests/verificar_promociones_responsive.py` | Simulaciones con moneda ARS y prueba visual aislada de HTTPS obligatorio. |

## Reglas de pagos conservadas y correcciones justificadas

Se mantienen descuentos, cuotas, reservas, vencimiento y aprobación manual del QR. Los pagos tardíos sin stock o para pedidos cancelados siguen registrados con aviso para intervención; no se reactiva una venta cancelada automáticamente.

La confirmación nueva exige `approved`, referencia exacta, moneda ARS y monto exacto. Antes toleraba hasta $1 menos y no comprobaba moneda: se elimina esa tolerancia para no saldar una deuda con un pago incorrecto. El total comercial del pedido no cambia. Un total cero no se envía al proveedor: se solicita elegir otro medio existente; no se cobra un importe inventado.

Solo el nuevo webhook usa `csrf_exempt`: es una comunicación entre servidores, sin cookie de sesión, autenticada por HMAC SHA-256 con comparación constante. Login, registro, carrito y checkout siguen protegidos por CsrfViewMiddleware. El webhook consulta el pago real con la API; nunca acepta estado, monto o referencia enviados por el navegador. Repeticiones/retorno comparten el bloqueo del pedido y no duplican pago ni descuento de stock.

El webhook queda deshabilitado (503) sin secreto. No se incluye `notification_url` en las preferencias hasta configurar ese secreto. Pedidos previos sin referencia persistida y QR no se asocian a ciegas desde notificaciones: conciliación manual. Los retornos antiguos autenticados conservan su ruta; los links históricos `carrito_...` requieren la referencia que estaba en la sesión. Reembolsos/contracargos no cambian automáticamente ventas o stock; requieren revisión del proveedor y administración.

## Acción urgente en PythonAnywhere (sin esperar al código)

En **Web → aplicación www.indiragold.com.ar → Security**, activar **Force HTTPS**, después de comprobar el certificado válido. Conservar las redirecciones actuales del dominio sin www. Es necesario cubrir el dominio www directamente: hoy el apex pasa por Cloudflare, pero www responde desde PythonAnywhere. Esto corrige la entrada HTTP identificada aun antes de desplegar el resto.

Actualizar el enlace de Instagram y enlaces promocionales a `https://www.indiragold.com.ar/` conservando los parámetros UTM que se necesiten. No usar HTTP.

Comprobar sin enviar formularios (Bash):

```bash
curl -sSI http://www.indiragold.com.ar/users/login/
curl -sSI http://indiragold.com.ar/users/login/
curl -sSI https://indiragold.com.ar/users/login/
curl -sSI https://www.indiragold.com.ar/users/login/
```

Las tres primeras deben redirigir al HTTPS correspondiente; la última debe mostrar 200 y cookie Secure. No publicar la salida completa con cookies.

## Variables y configuración del servidor

Conservar SECRET_KEY actual, credenciales y sesiones. **No reemplazar config/settings.py por el local.** Comparar el diff e incorporar únicamente los nuevos bloques y la entrada `config.middleware.FormulariosSegurosMiddleware` inmediatamente después de SecurityMiddleware. El resto del servidor puede contener rutas/DB/estáticos/correo específicos.

En el entorno que carga el WSGI (y también en las consolas de mantenimiento), revisar:

```dotenv
DEBUG=False
ALLOWED_HOSTS=indiragold.com.ar,www.indiragold.com.ar
SITE_URL=https://www.indiragold.com.ar
SECURE_SSL_REDIRECT=True
TRUST_X_FORWARDED_PROTO=False
```

Agregar a ALLOWED_HOSTS otros hosts verificados que ya se usen; no borrar configuraciones particulares. CSRF_TRUSTED_ORIGINS no reemplaza ALLOWED_HOSTS y no resuelve cookies ausentes. Los POST al mismo host HTTPS funcionan sin agregar orígenes. Si la integración existente exige solicitudes entre ambos hosts, usar únicamente `https://indiragold.com.ar,https://www.indiragold.com.ar`; nunca comodines, HTTP ni instagram.com. Lo preferible es servir formularios y acciones en el mismo host.

Mantener CSRF_COOKIE_SECURE=True, SESSION_COOKIE_SECURE=True y SameSite=Lax. Conservar cookies host-only; no ensanchar CSRF_COOKIE_DOMAIN/SESSION_COOKIE_DOMAIN para resolver este incidente. Si el servidor ya usa CSRF_USE_SESSIONS o CSRF_COOKIE_HTTPONLY, comprobarlo con el diagnóstico antes de cambiarlo: el código conserva el token del formulario si la cookie no puede leerse por JS.

No habilitar `TRUST_X_FORWARDED_PROTO` a ciegas. Verificar que Django ve `request.is_secure()` verdadero al recibir HTTPS y que no hay bucles. Si hay un proxy adicional, confirmar que elimina el encabezado externo y establece `X-Forwarded-Proto` de forma fiable antes de configurar `SECURE_PROXY_SSL_HEADER`. No activar USE_X_FORWARDED_HOST ni cambiar HSTS para este arreglo.

En Mercado Pago Developers, revisar la aplicación/credencial que ya usa el comercio. El **secreto de firma Webhooks es distinto del access token**. Si se habilita la confirmación automática, cargar `MERCADO_PAGO_WEBHOOK_SECRET` de esa aplicación en el entorno, configurar tópico **payment** y URL `https://www.indiragold.com.ar/pedidos/mercado-pago/webhook/`. No cambiar el token existente ni ejecutar un cobro de prueba real. El simulador sin un pago real consultable no puede confirmar un pedido.

## Despliegue con respaldo y settings preservado

Ejecutar desde una consola Bash de PythonAnywhere con el **virtualenv existente** de la pestaña Web activado y dentro de la ruta real del proyecto. No se inventan usuario, directorio, rama, WSGI ni virtualenv del servidor. Sustituir el SHA por el commit revisado que contenga estos cambios.

1. Revisar el estado y crear un respaldo privado fuera del repositorio y del directorio servido:

```bash
git status --short
umask 077
BACKUP_DIR="$HOME/indira-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"
export BACKUP_DIR
cp config/settings.py "$BACKUP_DIR/settings.py"
if [ -f .env ]; then cp .env "$BACKUP_DIR/env"; fi
git rev-parse HEAD > "$BACKUP_DIR/revision.txt"
python -m pip freeze > "$BACKUP_DIR/requirements-instalados.txt"
python manage.py diagnosticar_tienda
```

El último comando estará disponible cuando se instale el código nuevo; antes de eso omitirlo. Si `git status` muestra cambios locales, revisarlos y respaldarlos antes de integrar. No usar reset --hard, clean, seed_demo ni flush.

2. Backup PostgreSQL y archivos, usando las rutas/credenciales reales de Django sin imprimirlas. Este bloque **solo crea backups**, no restaura ni migra nada. Requiere pg_dump instalado, compatible con el servidor y espacio suficiente:

```bash
python manage.py shell <<'PY'
import os, subprocess, tarfile
from pathlib import Path
from django.conf import settings
destino = Path(os.environ['BACKUP_DIR'])
db = settings.DATABASES['default']
assert db['ENGINE'] == 'django.db.backends.postgresql', 'Verificar el motor real antes de continuar'
env = os.environ.copy()
for opcion, variable in [('HOST','PGHOST'), ('PORT','PGPORT'), ('USER','PGUSER'), ('PASSWORD','PGPASSWORD')]:
    if db.get(opcion): env[variable] = str(db[opcion])
subprocess.run(['pg_dump', '--format=custom', '--file=' + str(destino / 'postgresql.dump'),
                '--dbname=' + str(db['NAME'])], env=env, check=True)
with tarfile.open(destino / 'media.tar.gz', 'w:gz') as tar:
    tar.add(settings.MEDIA_ROOT, arcname='media')
print('Backups creados; verificar que ambos archivos tienen contenido y guardar una copia externa privada.')
PY
```

Si DATABASES contiene opciones PostgreSQL especiales (SSL, service, etc.), usar el procedimiento de backup ya validado para esa conexión. No avanzar si falla el backup. Para un backup consistente de BD y archivos, pausar brevemente las escrituras administrativas durante la copia.

3. Revisar e instalar el código. Este método aplica un parche sin sobrescribir settings ni descartar cambios del servidor. Requiere que HEAD sea la versión desplegada; si el código servidor ya diverge, comparar y resolver antes, sin forzar:

```bash
REVISION=REEMPLAZAR_POR_SHA_REVISADO
git fetch origin
git diff HEAD "$REVISION" -- config/settings.py
git diff --binary HEAD "$REVISION" -- . ':(exclude)config/settings.py' > "$BACKUP_DIR/codigo.patch"
git apply --check "$BACKUP_DIR/codigo.patch"
```

Solo si la revisión y `--check` pasan, en una ventana breve de mantenimiento:

```bash
git apply "$BACKUP_DIR/codigo.patch"
```

Incorporar manualmente el diff de settings y revisar variables como se explica arriba. Este procedimiento deja HEAD sin avanzar y los cambios visibles en el árbol: registrar el SHA desplegado en el registro de releases y no reaplicar el parche. Si se usa un proceso propio de despliegue por releases, usar ese proceso conservando las mismas exclusiones. No hacer un pull que sobrescriba settings.

No hace falta actualizar Django, SDK o todo requirements.txt para este cambio. Revisar las versiones instaladas; la versión local de prueba es Django 6.0.1/Pillow 13.0.0. Evitar `pip install -U` en producción.

4. Verificar el esquema y aplicar **solo la migración aditiva de pedidos**. No ejecutar makemigrations en producción:

```bash
python manage.py check
python manage.py diagnosticar_tienda
python manage.py showmigrations pedidos
python manage.py migrate pedidos 0046_pedido_mercado_pago_referencia --plan
python manage.py sqlmigrate pedidos 0046_pedido_mercado_pago_referencia
```

Revisar que 0045 y sus dependencias ya estén aplicadas. Si el plan incluye migraciones históricas pendientes, detenerse y revisarlas. Con el esquema previo correcto:

```bash
python manage.py migrate pedidos 0046_pedido_mercado_pago_referencia
python manage.py collectstatic --noinput
python manage.py check --deploy
```

0046 agrega un campo nullable único a pedidos, sin borrar ni transformar registros. Puede tomar un bloqueo breve de la tabla: ejecutarlo en baja actividad y antes de recargar los workers nuevos. Revisar advertencias de check --deploy: no cambiar SECRET_KEY ni HSTS automáticamente.

En la pestaña Web comprobar los mapeos `/static/` → STATIC_ROOT y `/media/` → MEDIA_ROOT reales. Recargar la aplicación con **Reload** (no se conoce la ruta real del WSGI para inventar un `touch`). Las variables de la consola no se propagan automáticamente a workers WSGI: confirmar que ambos cargan el mismo entorno.

5. Imágenes antiguas: **no se ejecuta automáticamente**. Primero comprobar espacio y una muestra:

```bash
python manage.py optimizar_imagenes_productos --dry-run --limite 20
```

Después de revisar la simulación, generar voluntariamente ese lote y comprobar visualmente catálogo/detalle:

```bash
python manage.py optimizar_imagenes_productos --aplicar --limite 20
```

Continuar por lotes con `--desde-id ID --limite 100`. El límite es por filas ordenadas por ID, no por IDs consecutivos. No borrar originales; los faltantes se reportan y se restauran desde backup. La versión usa nombres de archivo inmutables de Storage; si se reemplazan bytes externamente bajo el mismo nombre, las derivadas quedan antiguas: subir como imagen nueva para asignar otro nombre.

## Verificación posterior y recuperación

Repetir los cuatro curl, abrir el enlace de Instagram **desde cero** (cerrar la página HTTP antigua), probar login/registro/código/dirección, variantes y filtros, carrito invitado → login → checkout, descuentos/transferencia/efectivo y administración. Usar cuentas/datos de prueba conocidos. Verificar nuevas copias WebP en Network y cookie Secure sobre HTTPS. No comprar con una tarjeta real para esta revisión. La prueba integral del proveedor debe hacerse con cuentas/credenciales de prueba separadas de producción.

Mirar nuevos logs: no deberían repetirse `CSRF cookie not set` para las navegaciones HTTPS recién iniciadas. Un POST que ya estaba abierto en HTTP puede ser rechazado; no reenviarlo automáticamente. Los navegadores internos y Safari no comparten necesariamente cookies: iniciar sesión de nuevo es normal al cambiar de navegador.

Si el código falla, detener nuevas escrituras del checkout, desactivar la nueva URL en Mercado Pago y quitar únicamente el secreto nuevo del entorno, volver a los archivos anteriores desde el parche inverso **primero comprobándolo**:

```bash
git apply --reverse --check "$BACKUP_DIR/codigo.patch"
git apply --reverse "$BACKUP_DIR/codigo.patch"
cp "$BACKUP_DIR/settings.py" config/settings.py
python manage.py collectstatic --noinput
```

Revisar/revertir las variables nuevas manualmente y recargar Web. Mantener **Force HTTPS** activado. Dejar la columna nullable 0046 en la BD: el código anterior la ignora y conserva referencias de pagos. No restaurar un dump antiguo sobre ventas nuevas ni borrar la columna como rollback automático. Revisar pagos pendientes/tardíos con el proveedor y no repetir cobros.

## Pruebas locales reproducibles

Resultado final: **260 pruebas Django aprobadas en PostgreSQL local**, incluidas las de concurrencia; **8 pruebas JavaScript aprobadas**; **48 verificaciones responsive en Chrome sin errores**; `makemigrations --check --dry-run` sin cambios pendientes y `git diff --check` sin errores. La ejecución previa en SQLite también pasó (258 pruebas entonces, con 9 omitidas por requisitos de PostgreSQL/procesos del sandbox). Los mensajes de errores simulados que aparecen durante la suite prueban los caminos de fallo y rollback; no corresponden a operaciones de producción.

```powershell
.\venv\Scripts\python.exe -B manage.py test --settings=config.settings_test --noinput
.\venv\Scripts\python.exe -B manage.py test --settings=config.settings_test_postgresql --noinput
node --test tests/frontend.test.cjs
.\venv\Scripts\python.exe tests/verificar_promociones_responsive.py
.\venv\Scripts\python.exe -B manage.py makemigrations --check --dry-run --settings=config.settings_test
```

La primera suite usa SQLite en memoria, correo en memoria y token ficticio. La segunda solo admite PostgreSQL en localhost y crea una BD con nombre aleatorio `test_indiragold_*` para pruebas de bloqueos/concurrencia; nunca usa tablas de la tienda y elimina solo esa BD al terminar. Necesita un usuario local autorizado a crear bases. No ejecutar settings_test_postgresql en PythonAnywhere. El script responsive usa SQLite en memoria y Chrome headless; no usa la BD de la tienda.

Referencias técnicas: [Django CSRF](https://docs.djangoproject.com/en/6.0/ref/csrf/), [configuración de proxy](https://docs.djangoproject.com/en/6.0/ref/settings/#secure-proxy-ssl-header), [Force HTTPS en PythonAnywhere](https://help.pythonanywhere.com/pages/ForcingHTTPS/), [notificaciones Checkout Pro](https://www.mercadopago.com.ar/developers/en/docs/checkout-pro-preferences/payment-notifications), [preferencias de Mercado Pago](https://www.mercadopago.com.ar/developers/es/reference/online-payments/checkout-pro-preferences/create-preference/post).
