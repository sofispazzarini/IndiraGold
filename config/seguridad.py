"""Errores CSRF recuperables sin aceptar ni repetir el POST rechazado."""
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.cache import add_never_cache_headers


def csrf_failure(request, reason=''):
    # Conserva el registro oficial de Django (sin registrar cookies ni tokens).
    # CsrfViewMiddleware registra el motivo al devolver esta respuesta.
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        response = JsonResponse({
            'error': 'csrf_failed',
            'message': 'La página venció. Volvé a cargarla e intentá de nuevo.',
        }, status=403)
    else:
        # Nunca volver por GET a una acción que solo admite POST.
        volver_url = request.path if request.path in (
            '/users/login/', '/users/registro/', '/users/confirmar-direccion/'
        ) else reverse('home:home')
        response = render(request, '403_csrf.html', {'volver_url': volver_url}, status=403)
    add_never_cache_headers(response)
    return response
