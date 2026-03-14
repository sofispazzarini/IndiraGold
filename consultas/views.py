from django.contrib import messages
from django.shortcuts import redirect


def nueva(request):
	if request.method == 'POST':
		messages.success(request, '¡Gracias por tu consulta! Te responderemos a la brevedad.')
	return redirect('home:home')
