from django.contrib import admin
from .models import VideoProject, Scene, Voice

class SceneInline(admin.TabularInline):
    model = Scene
    extra = 0

@admin.register(VideoProject)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "ratio", "updated_at")
    inlines = [SceneInline]

@admin.register(Voice)
class VoiceAdmin(admin.ModelAdmin):
    list_display = ("name", "consent_confirmed", "created_at")
