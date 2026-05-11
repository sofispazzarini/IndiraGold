from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render, get_object_or_404

from .forms import TemaConsultaForm, ConsultaForm
from .models import TemaConsulta, Consulta


# === TEMAS ===

@staff_member_required
def gestion_temas(request):
    temas = TemaConsulta.objects.all().order_by('-created_at')
    return render(request, 'consultas/gestion_temas.html', {'temas': temas})


@staff_member_required
def crear_tema(request):
    if request.method == 'POST':
        form = TemaConsultaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Tema creado exitosamente.')
            return redirect('consultas:gestion_temas')
    else:
        form = TemaConsultaForm()
    return render(request, 'consultas/crear_tema.html', {'form': form})


@staff_member_required
def editar_tema(request, tema_id):
    tema = get_object_or_404(TemaConsulta, id=tema_id)
    if request.method == 'POST':
        form = TemaConsultaForm(request.POST, instance=tema)
        if form.is_valid():
            form.save()
            messages.success(request, 'Tema actualizado exitosamente.')
            return redirect('consultas:gestion_temas')
    else:
        form = TemaConsultaForm(instance=tema)
    return render(request, 'consultas/crear_tema.html', {'form': form, 'tema': tema})


@staff_member_required
def eliminar_tema(request, tema_id):
    tema = get_object_or_404(TemaConsulta, id=tema_id)
    if request.method == 'POST':
        nombre = tema.nombre
        tema.delete()
        messages.success(request, f'Tema "{nombre}" eliminado.')
    return redirect('consultas:gestion_temas')


@staff_member_required
def toggle_estado_tema(request, tema_id):
    tema = get_object_or_404(TemaConsulta, id=tema_id)
    if request.method == 'POST':
        tema.activo = not tema.activo
        tema.save()
        estado = 'activado' if tema.activo else 'desactivado'
        messages.success(request, f'Tema "{tema.nombre}" {estado}.')
    return redirect('consultas:gestion_temas')


# === PREGUNTAS FRECUENTES ===

@staff_member_required
def gestion_faqs(request):
    faqs = Consulta.objects.select_related('tema').all()
    return render(request, 'consultas/gestion_faqs.html', {'faqs': faqs})


@staff_member_required
def crear_faq(request):
    if request.method == 'POST':
        form = ConsultaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Pregunta frecuente creada.')
            return redirect('consultas:gestion_faqs')
    else:
        form = ConsultaForm()
    return render(request, 'consultas/crear_faq.html', {'form': form})


@staff_member_required
def editar_faq(request, faq_id):
    faq = get_object_or_404(Consulta, id=faq_id)
    if request.method == 'POST':
        form = ConsultaForm(request.POST, instance=faq)
        if form.is_valid():
            form.save()
            messages.success(request, 'Pregunta frecuente actualizada.')
            return redirect('consultas:gestion_faqs')
    else:
        form = ConsultaForm(instance=faq)
    return render(request, 'consultas/crear_faq.html', {'form': form, 'faq': faq})


@staff_member_required
def eliminar_faq(request, faq_id):
    faq = get_object_or_404(Consulta, id=faq_id)
    if request.method == 'POST':
        faq.delete()
        messages.success(request, 'Pregunta frecuente eliminada.')
    return redirect('consultas:gestion_faqs')


@staff_member_required
def toggle_estado_faq(request, faq_id):
    faq = get_object_or_404(Consulta, id=faq_id)
    if request.method == 'POST':
        faq.activa = not faq.activa
        faq.save()
        estado = 'activada' if faq.activa else 'desactivada'
        messages.success(request, f'Pregunta {estado}.')
    return redirect('consultas:gestion_faqs')
