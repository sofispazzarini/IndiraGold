from django.urls import path

from . import views

app_name = 'consultas'

urlpatterns = [
    # Temas
    path('admin/temas/', views.gestion_temas, name='gestion_temas'),
    path('admin/temas/crear/', views.crear_tema, name='crear_tema'),
    path('admin/temas/crear-ajax/', views.crear_tema_ajax, name='crear_tema_ajax'),
    path('admin/temas/<int:tema_id>/editar/', views.editar_tema, name='editar_tema'),
    path('admin/temas/<int:tema_id>/eliminar/', views.eliminar_tema, name='eliminar_tema'),
    path('admin/temas/<int:tema_id>/toggle/', views.toggle_estado_tema, name='toggle_estado_tema'),

    # FAQs
    path('admin/faqs/', views.gestion_faqs, name='gestion_faqs'),
    path('admin/faqs/crear/', views.crear_faq, name='crear_faq'),
    path('admin/faqs/<int:faq_id>/editar/', views.editar_faq, name='editar_faq'),
    path('admin/faqs/<int:faq_id>/eliminar/', views.eliminar_faq, name='eliminar_faq'),
    path('admin/faqs/<int:faq_id>/toggle/', views.toggle_estado_faq, name='toggle_estado_faq'),
]
