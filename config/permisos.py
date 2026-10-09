from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect


def admin_required(view_func):
    """Vistas del panel: solo administradores (superusuario).
    - Sin sesión: al login de la tienda, que después vuelve a la página pedida (?next=).
    - Con sesión de cliente: a la tienda con el aviso "No tenés permisos" (antes veía el login como
      si no hubiera entrado, o el login de "Administración de Django")."""
    @wraps(view_func)
    def vista(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), '/users/login/')
        if not request.user.is_superuser:
            messages.error(request, 'No tenés permisos para ver esa página.')
            return redirect('home:home')
        return view_func(request, *args, **kwargs)
    return vista
