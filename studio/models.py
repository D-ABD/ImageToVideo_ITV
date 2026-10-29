from django.db import models
from django.utils import timezone

class Voice(models.Model):
    name = models.CharField(max_length=80)
    sample = models.FileField(upload_to="voices/")
    consent_confirmed = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.name

class VideoProject(models.Model):
    STATUS_CHOICES = [(x, x.title()) for x in ("draft", "preparing", "prepared", "processing", "ready", "error")]
    FORMAT_CHOICES = [("9:16", "Vertical 9:16"), ("16:9", "Horizontal 16:9")]
    title = models.CharField(max_length=120, default="Nouveau projet")
    ratio = models.CharField(max_length=4, choices=FORMAT_CHOICES, default="9:16")
    subtitles_enabled = models.BooleanField(default=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="draft")
    status_message = models.CharField(max_length=240, blank=True)
    progress_percent = models.PositiveSmallIntegerField(default=0)
    selected_voice = models.ForeignKey(Voice, null=True, blank=True, on_delete=models.SET_NULL, related_name="projects")
    video = models.FileField(upload_to="videos/", blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

class Scene(models.Model):
    MOTION_CHOICES = [
        ("still", "Image fixe"),
        ("zoom_in", "Zoom avant"),
        ("zoom_out", "Zoom arrière"),
        ("pan_left", "Panoramique · gauche"),
        ("pan_right", "Panoramique · droite"),
        ("pan_up", "Panoramique · haut"),
        ("pan_down", "Panoramique · bas"),
    ]
    project = models.ForeignKey(VideoProject, on_delete=models.CASCADE, related_name="scenes")
    image = models.ImageField(upload_to="scenes/")
    position = models.PositiveIntegerField(default=0)
    page_number = models.PositiveIntegerField(default=1)
    narration_text = models.TextField(blank=True)
    motion = models.CharField(max_length=12, choices=MOTION_CHOICES, default="zoom_in")
    motion_amount = models.PositiveSmallIntegerField(default=25)
    audio = models.FileField(upload_to="narrations/", blank=True)
    subtitle_data = models.JSONField(default=list, blank=True)
    duration_seconds = models.FloatField(default=0)
    cache_key = models.CharField(max_length=64, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.project.title} — scène {self.position + 1}"
