from django import template
register = template.Library()

@register.filter
def get_proveedor_by_id(proveedores, id):
    for p in proveedores:
        if str(p.id) == str(id):
            return p.nombre
    return ''
