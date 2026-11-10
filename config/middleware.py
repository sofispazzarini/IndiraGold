from django.template.loader import render_to_string
from django.utils.cache import add_never_cache_headers
from django.conf import settings


class FormulariosSegurosMiddleware:
    """Evita reutilizar HTML con tokens de otra sesión en caches intermedias."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if settings.CSRF_COOKIE_NAME in response.cookies or request.path.startswith(
            ('/users/', '/pedidos/', '/carritos/', '/admin/')
        ):
            add_never_cache_headers(response)
        return response


class PaginaError405Middleware:
    """Las vistas con require_POST / require_GET responden 405 sin contenido y el navegador
    muestra "Esta página no funciona". Si el pedido es una navegación (acepta HTML), se
    muestra templates/405.html con el diseño de la tienda."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            response.status_code == 405
            and not response.content
            and 'text/html' in request.headers.get('Accept', '')
        ):
            response.content = render_to_string('405.html', request=request)
            response['Content-Type'] = 'text/html; charset=utf-8'
        return response
