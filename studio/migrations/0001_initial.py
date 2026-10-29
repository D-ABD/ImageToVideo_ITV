import django.utils.timezone
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="Voice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80)),
                ("sample", models.FileField(upload_to="voices/")),
                ("consent_confirmed", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
            ],
        ),
        migrations.CreateModel(
            name="VideoProject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(default="Nouveau projet", max_length=120)),
                ("ratio", models.CharField(choices=[("9:16", "Vertical 9:16"), ("16:9", "Horizontal 16:9")], default="9:16", max_length=4)),
                ("subtitles_enabled", models.BooleanField(default=True)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("processing", "Processing"), ("ready", "Ready"), ("error", "Error")], default="draft", max_length=16)),
                ("status_message", models.CharField(blank=True, max_length=240)),
                ("video", models.FileField(blank=True, upload_to="videos/")),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("selected_voice", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="projects", to="studio.voice")),
            ],
        ),
        migrations.CreateModel(
            name="Scene",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.ImageField(upload_to="scenes/")),
                ("position", models.PositiveIntegerField(default=0)),
                ("page_number", models.PositiveIntegerField(default=1)),
                ("narration_text", models.TextField(blank=True)),
                ("motion", models.CharField(choices=[("still", "Image fixe"), ("zoom_in", "Zoom avant lent"), ("zoom_out", "Zoom arrière lent")], default="zoom_in", max_length=12)),
                ("audio", models.FileField(blank=True, upload_to="narrations/")),
                ("subtitle_data", models.JSONField(blank=True, default=list)),
                ("duration_seconds", models.FloatField(default=0)),
                ("cache_key", models.CharField(blank=True, max_length=64)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scenes", to="studio.videoproject")),
            ],
            options={"ordering": ["position", "id"]},
        ),
    ]
