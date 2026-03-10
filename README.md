# IndiraGold - Proyecto web

Proyecto web desarrollado con Django para la gestión de productos, ventas, clientes y consultas de Indira Gold.

---

## 📌 Tecnologías utilizadas

- Python 3.12
- Django
- PostgreSQL
- pgAdmin
- HTML / CSS (futuro)
- GitHub

---

## 📁 Estructura del proyecto

- users → gestión de usuarios, clientes y direcciones
- productos → productos, variantes, talles, colores, medidas
- carritos → carrito de compras
- pedidos → pedidos, pagos y gastos
- consultas → consultas de usuarios y respuestas del administrador

---

## ⚙️ Requisitos previos

Tener instalado:

- Python 3.12
- PostgreSQL
- pgAdmin
- Git

---

## 🚀 Instalación y puesta en marcha

### 1️⃣ Clonar el repositorio

```bash
git clone https://github.com/sofispazzarini/IndiraGold.git
cd IndiraGold

Paso 2: Craer entorno virtual

python -m venv venv

Activarlo: venv\Scripts\activate

Paso 3: Intslar dependencias
pip install -r requirements.txt
si no existen, instalar manualmente:
pip install django psycopg2-binary python-dotenv

paso 4: configurar variables de entorno
crear un archvio .env en la raiz del proyecto
DB_NAME=indiragold_db
DB_USER=postgres
DB_PASSWORD=tu_password
DB_HOST=localhost
DB_PORT=5432

paso 5:craer la base de datos
Desde pgAdmin crear la base de datos:indiragold_db

paso 6:Migraciones
python manage.py makemigrations
python manage.py migrate

paso 7:cargar datos de prueba
python manage.py loaddata fixtures/datos_iniciales.json

paso 8:crear superusuarios
python manage.py createsuperuser

paso 9:correr servidor
python manage.py runserver

## Configuración de variables de entorno para envío de mails

Para que el envío de correos funcione correctamente, crea un archivo `.env` en la raíz del proyecto y agrega las siguientes variables (ajusta los valores según tu proveedor de correo):

```

EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=tu_correo@gmail.com
EMAIL_HOST_PASSWORD=tu_contraseña_de_aplicacion
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=tu_correo@gmail.com

```

> **Nota:** Si usas Gmail, debes generar una contraseña de aplicación desde la configuración de seguridad de tu cuenta.
```
