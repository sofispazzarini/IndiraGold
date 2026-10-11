from .stock_pedidos import vencer_reservas_si_corresponde


class VencerReservasMiddleware:
    """Libera el stock de los pedidos pendientes que vencieron sin pagarse. Revisa como mucho una
    vez cada 5 minutos por proceso, así no hace falta un cron (también existe el comando
    `python manage.py vencer_pedidos_pendientes` para programarlo aparte)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        vencer_reservas_si_corresponde()
        return self.get_response(request)
