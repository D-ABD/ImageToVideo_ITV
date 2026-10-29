from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from studio import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.home, name="home"),
    path("projects/create/", views.create_project, name="create_project"),
    path("projects/<int:project_id>/", views.project_detail, name="project_detail"),
    path("projects/<int:project_id>/scenes/<int:scene_id>/save/", views.save_scene, name="save_scene"),
    path("projects/<int:project_id>/scenes/reorder/", views.reorder_scenes, name="reorder_scenes"),
    path("projects/<int:project_id>/scenes/<int:scene_id>/delete/", views.delete_scene, name="delete_scene"),
    path("voices/create/", views.create_voice, name="create_voice"),
    path("projects/<int:project_id>/prepare-audio/", views.prepare_audio, name="prepare_audio"),
    path("projects/<int:project_id>/generate/", views.generate, name="generate"),
    path("projects/<int:project_id>/status/", views.project_status, name="project_status"),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
