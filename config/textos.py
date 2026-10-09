import re

# Palabras que no llevan mayúscula en medio de un nombre: "Pérez de la Torre", "Flex CABA y GBA"
CONECTORES = {'de', 'del', 'la', 'las', 'los', 'el', 'y', 'e', 'da', 'di', 'van', 'von'}


def capitalizar_texto(valor):
    """Respeta lo que escribe el usuario. Solo si escribió todo en minúsculas se ponen mayúsculas
    iniciales (sin tocar conectores como "de", "la" o "y", y también después de un apóstrofo o un
    guion: "o'connor" -> "O'Connor"). Nunca pasa a minúsculas lo que se escribió en mayúsculas:
    siglas como CABA o GBA y apellidos como McDonald quedan igual."""
    texto = ' '.join((valor or '').split())
    if not texto or texto != texto.lower():
        return texto
    palabras = []
    for indice, palabra in enumerate(texto.split(' ')):
        if indice > 0 and palabra in CONECTORES:
            palabras.append(palabra)
            continue
        palabras.append(re.sub(r"(^|['’\-])([^\W\d_])", lambda m: m.group(1) + m.group(2).upper(), palabra))
    return ' '.join(palabras)
