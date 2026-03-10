from django.views.generic import TemplateView
from productos.models import Producto, Categoria

class HomePublicaView(TemplateView):
    template_name = 'home_publico.html'
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['productos'] = Producto.objects.filter(activo=True)
        ctx['categorias'] = Categoria.objects.all()
        return ctx