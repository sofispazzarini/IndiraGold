from __future__ import annotations

from django.utils import timezone

SESSION_CART_KEY = "carrito"
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
