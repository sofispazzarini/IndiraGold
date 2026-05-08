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

IndiraGold © 2026