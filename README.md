IndiraGold - Proyecto web
Proyecto web desarrollado con Django para la gestión de productos, ventas, clientes y consultas de Indira Gold.

📌 Tecnologías utilizadas
Python 3.12

Django

PostgreSQL

pgAdmin

Bootstrap 5 / CSS

GitHub

📁 Estructura del proyecto
users → Gestión de usuarios, clientes y direcciones.

productos → Productos, variantes, talles, colores, categorías y proveedores.

carritos → Sistema de carrito de compras.

pedidos → Gestión de pedidos, pagos y gastos.

consultas → Mensajería entre usuarios y administración.

⚙️ Requisitos previos
Asegúrate de tener instalado:

Python 3.12

PostgreSQL & pgAdmin 4

Git

🚀 Instalación y puesta en marcha
1️⃣ Clonar el repositorio
git clone https://github.com/sofispazzarini/IndiraGold.git
cd IndiraGold
2️⃣ Crear entorno virtual

python -m venv venv
Activarlo:

Windows: venv\Scripts\activate

Mac/Linux: source venv/bin/activate

3️⃣ Instalar dependencias

pip install -r requirements.txt
Si el archivo no existe, instalar manualmente:

pip install django psycopg2-binary python-dotenv
4️⃣ Configurar variables de entorno
Crear un archivo .env en la raíz del proyecto con el siguiente contenido:

Fragmento de código
DB_NAME=indiragold_db
DB_USER=postgres
DB_PASSWORD=tu_password
DB_HOST=localhost
DB_PORT=5432

# Configuración de Mail (Opcional para desarrollo)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=tu_correo@gmail.com
EMAIL_HOST_PASSWORD=tu_contraseña_de_aplicacion
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=tu_correo@gmail.com

5️⃣ Crear la base de datos
Desde pgAdmin, crea una nueva base de datos llamada: indiragold_db.

6️⃣ Migraciones
Prepara la estructura de la base de datos:

python manage.py makemigrations
python manage.py migrate

7️⃣ Cargar datos de prueba (Seed)
¡Importante! Para tener el catálogo, clientes y proveedores cargados automáticamente, ejecuta:

python manage.py seed_demo
Este comando poblará la base de datos con categorías, productos (Remeras Aura), variantes y un cliente de prueba para que puedas ver el dashboard funcionando inmediatamente.

8️⃣ Crear superusuario
Para acceder al panel de administración de Django:

python manage.py createsuperuser
9️⃣ Correr servidor

python manage.py runserver
Accede a: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

📧 Notas sobre el envío de mails
Si usas Gmail para las notificaciones, recordá generar una contraseña de aplicación desde la configuración de seguridad de tu cuenta de Google. No uses tu contraseña normal.
````md
## 💳 Integración con Mercado Pago

El proyecto utiliza integración con Mercado Pago Checkout Pro para procesar pagos online.

### 1️⃣ Crear cuenta de desarrollador

Ingresar a:

https://www.mercadopago.com.ar/developers/panel

Crear una aplicación nueva:

- Tipo: Ventas online
- Plataforma: Sitio web propio / Django

---

### 2️⃣ Obtener credenciales TEST

Mercado Pago proporcionará:

- Public Key
- Access Token

⚠️ Para desarrollo utilizar únicamente las credenciales TEST.

---

### 3️⃣ Configurar variables de entorno

Agregar al archivo `.env`:

```env
MERCADO_PAGO_ACCESS_TOKEN=TEST-xxxxxxxx
````

⚠️ El archivo `.env` no debe subirse a GitHub.

---

### 4️⃣ Instalar dependencias

```bash
pip install mercadopago
pip install python-decouple
```

Si se agregan nuevas dependencias:

```bash
pip freeze > requirements.txt
```

---

### 5️⃣ Configurar `settings.py`

```python
from decouple import config

MERCADO_PAGO_ACCESS_TOKEN = config('MERCADO_PAGO_ACCESS_TOKEN')
```

---

### 6️⃣ Funcionamiento

Cuando el usuario presiona el botón "PAGAR AHORA":

1. Django crea una preferencia de pago.
2. Mercado Pago genera el checkout seguro.
3. El usuario es redirigido a Mercado Pago.
4. Luego de finalizar el pago, Mercado Pago redirecciona nuevamente al sitio.

---

```
```
IndiraGold © 2026