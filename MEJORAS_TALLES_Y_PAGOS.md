# Talles múltiples y descuentos por medio de pago

## Implementación

- Catálogo: desplegable de checkboxes; muestra productos con al menos un talle seleccionado con stock. Conserva categoría, color y búsqueda, la selección desde la bienvenida y agrega limpiar talles o todos los filtros. El desplegable admite teclado, Escape, clic fuera y pantallas móviles.
- Administración: en **Configurar pagos → Descuentos por método de pago**, porcentajes independientes de transferencia y efectivo entre 0 y 100, con dos decimales. Solo superusuarios, mediante el decorador existente `admin_required`.
- Precios orientativos sin envío en catálogo, destacados, ofertas, detalle y relacionados. Solo se anuncian porcentajes positivos; no se anuncia transferencia si está desactivada.
- Checkout: recalcula al cambiar medio de pago, envío o cupón. Muestra subtotal, envío, cupón si existe, porcentaje e importe por pago y total. Si falta cotizar el correo, el resumen aclara que el envío está pendiente.
- Backend: `pedidos/descuentos.py` centraliza el cálculo con Decimal y redondeo HALF_UP a centavos. Usa precios y envío validados en servidor; ignora los importes o porcentajes que intente enviar el cliente.
- Se conservan ofertas y cupones: primero se aplica el cupón a los productos y después el descuento del medio seleccionado sobre productos netos más envío. Los descuentos de efectivo y transferencia nunca se suman.
- El pedido conserva el porcentaje y monto de pago además de sus campos existentes de cupón, medio de pago y total. La configuración futura no modifica pedidos existentes. La edición administrativa reutiliza el porcentaje histórico.
- El detalle administrativo y ticket muestran el descuento guardado. Los ítems enviados a Mercado Pago o su QR suman el total persistido; si el redondeo unitario del cupón genera diferencias, se envía una línea con el importe total de la compra.

## Base de datos

No hay modelos ni relaciones nuevas. `ConfiguracionPago` agrega `descuento_transferencia_porcentaje` y `descuento_efectivo_porcentaje`. `Pedido` agrega `descuento_pago_porcentaje` y `descuento_pago_monto`. Todos empiezan en cero para conservar pedidos anteriores.

Con el entorno virtual activo:

```powershell
python manage.py migrate
python manage.py runserver
```

La migración nueva es `pedidos/0045_descuentos_metodo_pago.py`. No hace falta ejecutar `makemigrations`. No se aplicó la migración a tu base durante el desarrollo.

## Prueba desde la web

1. Ingresar como administradora, abrir **Configurar pagos**, configurar transferencia 10% y efectivo 15%, guardar. Probar también 0% y valores inválidos.
2. Abrir la tienda como cliente o invitado y seleccionar dos talles. Combinar categoría, color y búsqueda; desmarcar talles y usar los botones de limpieza. Probar el desplegable también en celular.
3. Revisar debajo del precio del catálogo y detalle los importes por pago; por ejemplo, un producto de $50.000 muestra $45.000 por transferencia y $42.500 en efectivo.
4. Agregar productos y entrar al checkout como cliente. Con retiro en local, alternar Mercado Pago, transferencia y efectivo. Cada selección reemplaza el descuento anterior.
5. Para productos por $50.000 y envío cotizado en $8.000, elegir transferencia: descuento $5.800 y total $52.200. Cambiar envío y verificar el recálculo. No se debe usar un costo de correo ingresado manualmente: el sistema toma la cotización del servidor.
6. Confirmar el pedido, comprobar importe y descuento en su detalle, cambiar la configuración administrativa y verificar que el pedido conserve sus valores.
7. Comprobar que un cliente no puede acceder a la configuración administrativa.

## Flujo de pagos conservado

El efectivo ya estaba limitado al retiro en local: sigue así. La fórmula soporta descontar envío también con efectivo, pero no se habilitaron combinaciones que antes estaban prohibidas. Habilitar efectivo con envío requeriría una decisión de negocio adicional.

Se mantienen los estados, la reserva de stock y la confirmación manual de transferencia y efectivo, incluso con descuento del 100%. Las APIs de pago y correo se simulan en las pruebas; no se realizan cobros reales.

## Verificación automatizada

- `python manage.py test` ejecuta las pruebas de Django usando una base de pruebas según la configuración del entorno.
- `node --test tests/frontend.test.cjs` ejecuta los filtros combinados y cálculos de checkout de JavaScript.
- La suite de descuentos compara 180 combinaciones de importes de frontend y backend si Node está disponible.

Las verificaciones de desarrollo usaron SQLite en memoria, sin tocar la base local. Las pruebas exclusivas de PostgreSQL/concurrencia se omiten en SQLite; deben ejecutarse contra una base de pruebas PostgreSQL para validar esos bloqueos.

## Archivos

- Catálogo: `home/templates/home_publico.html`, `home/static/home/catalogo_filtros.js`.
- Precios visibles: `home/templates/home/_tarjeta_destacada.html`, `productos/templates/productos/producto_detalle.html`, `pedidos/templatetags/descuentos_pago.py`, `pedidos/templates/pedidos/_descuentos_producto.html`.
- Cálculo/configuración/persistencia: `pedidos/descuentos.py`, `pedidos/models.py`, `pedidos/forms.py`, `pedidos/views.py`, `pedidos/migrations/0045_descuentos_metodo_pago.py`.
- Pantallas de pagos e historial: `pedidos/templates/pedidos/configurar_pagos.html`, `pedidos/templates/pedidos/checkout.html`, `pedidos/static/pedidos/descuentos_pago.js`, `pedidos/templates/pedidos/detalle_pedido.html`, `pedidos/templates/pedidos/ticket_cambio_venta.html`.
- Pruebas: `pedidos/tests_descuentos_pago.py`, `tests/frontend.test.cjs`, y datos de formulario actualizados en `pedidos/tests_costos_cobro.py`.


## Presentación responsive de las promociones

La tarjeta de catálogo, destacados, novedades y ofertas usa ahora `home/templates/home/_tarjeta_producto.html`. Búsqueda y filtros mantienen esas mismas tarjetas. La plantilla `_tarjeta_destacada.html` agrega únicamente el contenedor del carrusel.

El componente `pedidos/templates/pedidos/_descuentos_producto.html` se comparte con el detalle y los relacionados. En el detalle incluye el título “Promociones disponibles” y explica que el checkout descuenta también el envío. Sus estilos están en `pedidos/static/pedidos/descuentos_producto.css`, cargados desde `templates/base_publica.html`: textos sin recortes, saltos de línea, tamaños fluidos y separación de precio, promociones y botones. Las tarjetas de una fila conservan su altura y alineación.

No se agregaron modelos ni migraciones para este ajuste visual. Sigue siendo necesaria la migración `0045` si todavía no se aplicó.

Las variantes actuales no modifican el precio: se cobra `precio_unitario_vigente`, que toma el precio vigente del producto y sus ofertas. La copia histórica `Variante.precio` no se utiliza para cambiar lo cobrado por talle o color. Una prueba verifica que las promociones sigan coherentes aunque esa copia esté desactualizada; no se agregó una nueva regla de precios por variante.

Las pruebas adicionales verifican la presencia de ambos medios en todas las tarjetas, destacados/novedades/ofertas y detalle, la ausencia con porcentajes cero, la actualización al recargar y la composición con ofertas de catálogo.

Para repetir la comprobación visual automatizada, instalar Playwright en el entorno de desarrollo y ejecutar, desde la raíz:

```powershell
python -m pip install playwright
python tests/verificar_promociones_responsive.py
```

Usa Chrome instalado, datos ficticios y SQLite en memoria. Puede indicarse otra ruta de Chrome mediante `INDIRA_CHROME`. No usa tu base local ni realiza pagos. Comprueba 48 escenarios: catálogo/detalle a 320, 375, 414, 768, 1024 y 1440 píxeles, con dos descuentos, solo transferencia, solo efectivo y ninguno; incluye interacción con búsqueda, limpieza, talles y modal de carrito. Verifica desbordamientos, contención y alineación y guarda capturas temporales de celular/escritorio. Las fuentes externas se bloquean durante esta comprobación para no depender de la red.
