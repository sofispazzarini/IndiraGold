from __future__ import annotations
from .models import Carrito, CarritoItem
from users.models import Cliente
from django.utils import timezone
from productos.models import Variante
SESSION_CART_KEY = "carrito"
SESSION_CART_COLORS_KEY = "carrito_colores"
SESSION_CART_STARTED_AT_KEY = "carrito_started_at"
CART_EXPIRATION_SECONDS = 60 * 60


def _to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_cart_started_at(session) -> int | None:
    return _to_int(session.get(SESSION_CART_STARTED_AT_KEY))


def set_cart_started_at_if_missing(session) -> None:
    if get_cart_started_at(session) is None:
        session[SESSION_CART_STARTED_AT_KEY] = int(timezone.now().timestamp())
        session.modified = True


def clear_cart_session(session) -> None:
    session.pop(SESSION_CART_KEY, None)
    session.pop(SESSION_CART_COLORS_KEY, None)
    session.pop(SESSION_CART_STARTED_AT_KEY, None)
    session.modified = True


def get_cart_seconds_left(session) -> int:
    cart = session.get(SESSION_CART_KEY)
    if not isinstance(cart, dict) or not cart:
        return 0

    started_at = get_cart_started_at(session)
    if started_at is None:
        set_cart_started_at_if_missing(session)
        return CART_EXPIRATION_SECONDS

    elapsed = int(timezone.now().timestamp()) - started_at
    return max(0, CART_EXPIRATION_SECONDS - elapsed)


def expire_cart_if_needed(session) -> bool:
    cart = session.get(SESSION_CART_KEY)
    if not isinstance(cart, dict) or not cart:
        clear_cart_session(session)
        return False

    if get_cart_seconds_left(session) <= 0:
        clear_cart_session(session)
        return True

    return False
from users.models import Cliente

def get_or_create_cart(request):
    """
    Busca el carrito actual del usuario (ya sea logueado o anónimo).
    """
    
    # USUARIO LOGUEADO
    if request.user.is_authenticated:

        cliente, _ = Cliente.objects.get_or_create(user=request.user)

        carrito, _ = Carrito.objects.get_or_create(
            cliente=cliente,
            activo=True
        )

        
        return carrito

    # USUARIO INVITADO
    else:

        session_key = request.session.session_key

        if not session_key:
            request.session.create()
            session_key = request.session.session_key

        carrito, _ = Carrito.objects.get_or_create(
            session_id=session_key,
            activo=True
        )

        return carrito
# carritos/utils.py

def vincular_carrito_con_usuario(request, session_id_previo=None, carrito_sesion=None):
    """
    Vincula el carrito de invitado (sesión) con el carrito del usuario autenticado.
    - Fusiona los items de la sesión temporal con el carrito en BD del usuario
    - Sincroniza la sesión con lo que está en BD
    """
    if not request.user.is_authenticated:
        return
    
    from users.models import Cliente
    from .models import Carrito, CarritoItem
    from productos.models import Variante, Producto

    # 1. Obtener o crear el carrito del usuario autenticado
    cliente, _ = Cliente.objects.get_or_create(user=request.user)
    carrito_user, _ = Carrito.objects.get_or_create(cliente=cliente, activo=True)

    # 2. Si hay un carrito anterior de invitado en la BD, fusionarlo
    if session_id_previo:
        carrito_invitado = Carrito.objects.filter(
            session_id=session_id_previo, 
            cliente=None, 
            activo=True
        ).first()
        if carrito_invitado:
            # Fusionar items del carrito de invitado al carrito del usuario
            for item_invitado in carrito_invitado.items.all():
                item_existente = carrito_user.items.filter(
                    variante=item_invitado.variante
                ).first()
                if item_existente:
                    # Sumar cantidades si ya existe
                    item_existente.cantidad += item_invitado.cantidad
                    item_existente.precio_total = (
                        item_existente.cantidad * item_existente.precio_unitario
                    )
                    item_existente.save()
                else:
                    # Transferir item al carrito del usuario
                    item_invitado.carrito = carrito_user
                    item_invitado.save()
            
            # Desactivar carrito de invitado
            carrito_invitado.activo = False
            carrito_invitado.save()

    # 3. Procesar lo que traía de la sesión temporal (carrito_sesion)
    items_invitado = carrito_sesion or {}
    colores_invitado = request.session.get(SESSION_CART_COLORS_KEY)
    if not isinstance(colores_invitado, dict):
        colores_invitado = {}

    for vid_str, qty in items_invitado.items():
        try:
            qty_int = int(qty)
            if qty_int <= 0:
                continue
            id_int = int(vid_str)
            variante = Variante.objects.filter(id=id_int).first()
            if not variante:
                continue
            # Sumar cantidades solo si es exactamente el mismo variante_id
            item_existente = carrito_user.items.filter(variante=variante).first()
            if item_existente:
                item_existente.cantidad += qty_int
                if colores_invitado.get(str(id_int)):
                    item_existente.color_nombre = colores_invitado.get(str(id_int))
                item_existente.precio_total = item_existente.cantidad * item_existente.precio_unitario
                item_existente.save()
            else:
                CarritoItem.objects.create(
                    carrito=carrito_user,
                    variante=variante,
                    color_nombre=colores_invitado.get(str(id_int)),
                    cantidad=qty_int,
                    precio_unitario=variante.precio,
                    precio_total=qty_int * variante.precio
                )
        except Exception:
            continue
    # Limpiar la sesión después de fusionar
    request.session['carrito'] = {}
    request.session.modified = True

    # 4. SINCRONIZACIÓN CRÍTICA: Actualizar sesión con TODO lo que hay en BD
    # Usar variante_id como key para mantener todas las variantes
    carrito_final = {}
    colores_final = {}
    for item_db in carrito_user.items.all():
        carrito_final[str(item_db.variante.id)] = item_db.cantidad
        if item_db.color_nombre:
            colores_final[str(item_db.variante.id)] = item_db.color_nombre
    request.session['carrito'] = carrito_final
    request.session[SESSION_CART_COLORS_KEY] = colores_final
    request.session.modified = True


def _fusionar_item(carrito_destino, variante, cantidad):
    """
    Función auxiliar para agregar productos al carrito sin duplicar filas.
    Si la variante ya existe, suma la cantidad.
    """
    item, created = CarritoItem.objects.get_or_create(
        carrito=carrito_destino,
        variante=variante,
        defaults={
            'cantidad': 0,
            'precio_unitario': variante.precio,
            'precio_total': 0
        }
    )
    item.cantidad += cantidad
    item.precio_total = item.cantidad * item.precio_unitario
    item.save()
