from __future__ import annotations
import re
from .models import Carrito, CarritoItem
from users.models import Cliente
from django.utils import timezone
from productos.models import Variante

SESSION_CART_KEY = "carrito"
SESSION_CART_COLORS_KEY = "carrito_colores"
SESSION_CART_STARTED_AT_KEY = "carrito_started_at"
SESSION_CART_ITEM_KEY_SEPARATOR = "::"
CART_EXPIRATION_SECONDS = 60 * 60


def _normalize_hex(val: str | None) -> str | None:
    """Return a normalized hex color string like '#aabbcc' or None if invalid."""
    if not val:
        return None
    v = str(val).strip()
    m = re.match(r'^#?([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$', v)
    if not m:
        return None
    return f"#{m.group(1).lower()}"


def _normalize_color_token(value) -> str:
    if value is None:
        return ""
    token = str(value).strip().lower()
    if not token:
        return ""
    token = re.sub(r"[^a-z0-9#]+", "_", token)
    return token.strip("_")


def _make_cart_item_key(variante_id, color_nombre=None, color_hex=None) -> str:
    base_key = str(int(variante_id))
    color_token = _normalize_color_token(color_hex or color_nombre)
    return f"{base_key}{SESSION_CART_ITEM_KEY_SEPARATOR}{color_token}" if color_token else base_key


def _parse_cart_item_key(key) -> tuple[int | None, str]:
    raw_key = str(key or "")
    if SESSION_CART_ITEM_KEY_SEPARATOR in raw_key:
        variante_part, color_token = raw_key.split(SESSION_CART_ITEM_KEY_SEPARATOR, 1)
    else:
        variante_part, color_token = raw_key, ""

    try:
        variante_id = int(variante_part)
    except (TypeError, ValueError):
        return None, ""

    return variante_id, color_token


def _to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def obtener_o_crear_carrito(request):
    if request.user.is_authenticated:
        carrito, _ = Carrito.objects.get_or_create(cliente=request.user)
        return carrito

    # 1. Forzar a Django a generar una clave de sesión si no existe
    if not request.session.session_key:
        request.session.save()

    session_id = request.session.session_key

    # 2. Obtener o crear el carrito asociado a la session_key fija
    carrito, _ = Carrito.objects.get_or_create(session_id=session_id)
    return carrito

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


def get_or_create_cart(request):
    """
    Busca el carrito actual del usuario (ya sea logueado o anónimo).
    Retorna None para administradores.
    """

    # USUARIO LOGUEADO
    if request.user.is_authenticated:
        # Los administradores no tienen carrito
        if request.user.is_superuser or request.user.is_staff:
            return None

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
                    variante=item_invitado.variante,
                    color_nombre=item_invitado.color_nombre or None,
                    color_hex=item_invitado.color_hex or None,
                ).first()
                if item_existente:
                    # Sumar cantidades si ya existe (mismo variante + mismo color)
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

    for cart_key, qty in items_invitado.items():
        try:
            qty_int = int(qty)
            if qty_int <= 0:
                continue

            # Parsear la clave de sesión para extraer variante_id
            variante_id, _color_token = _parse_cart_item_key(cart_key)
            if not variante_id:
                continue

            variante = Variante.objects.select_related('producto').filter(id=variante_id).first()
            if not variante:
                continue

            # Extraer info de color del dict de colores (con compatibilidad hacia atrás)
            color_data = colores_invitado.get(str(cart_key)) or {}
            if isinstance(color_data, str):
                # Compatibilidad: formato viejo era solo string
                color_data = {"nombre": color_data, "hex": None}

            color_nombre = color_data.get("nombre") or None
            color_hex = _normalize_hex(color_data.get("hex")) or None

            # Buscar item existente considerando variante + color
            item_existente = carrito_user.items.filter(
                variante=variante,
                color_nombre=color_nombre,
                color_hex=color_hex,
            ).first()

            if item_existente:
                item_existente.cantidad += qty_int
                item_existente.precio_total = item_existente.cantidad * item_existente.precio_unitario
                item_existente.save()
            else:
                precio = variante.precio or variante.producto.precio or 0
                CarritoItem.objects.create(
                    carrito=carrito_user,
                    variante=variante,
                    color_nombre=color_nombre,
                    color_hex=color_hex,
                    cantidad=qty_int,
                    precio_unitario=precio,
                    precio_total=qty_int * precio
                )
        except Exception:
            continue
    # Limpiar la sesión después de fusionar
    request.session['carrito'] = {}
    request.session.modified = True

    # 4. SINCRONIZACIÓN CRÍTICA: Actualizar sesión con TODO lo que hay en BD
    # Usar formato consistente: variante_id::color_token como key
    carrito_final = {}
    colores_final = {}
    for item_db in carrito_user.items.all():
        item_key = _make_cart_item_key(item_db.variante.id, item_db.color_nombre, item_db.color_hex)
        carrito_final[item_key] = item_db.cantidad
        colores_final[item_key] = {
            "nombre": item_db.color_nombre,
            "hex": item_db.color_hex,
        }
    request.session['carrito'] = carrito_final
    request.session[SESSION_CART_COLORS_KEY] = colores_final
    request.session.modified = True
