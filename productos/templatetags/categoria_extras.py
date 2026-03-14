from django import template

register = template.Library()

@register.filter
def get_cat_id(categories, nombre):
    for cat in categories:
        if cat.nombre.lower() == nombre.lower():
            return cat.id
    return ''