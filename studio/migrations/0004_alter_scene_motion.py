from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("studio", "0003_scene_motion_amount")]

    operations = [
        migrations.AlterField(
            model_name="scene",
            name="motion",
            field=models.CharField(
                choices=[
                    ("still", "Image fixe"),
                    ("zoom_in", "Zoom avant"),
                    ("zoom_out", "Zoom arrière"),
                    ("pan_left", "Panoramique · gauche"),
                    ("pan_right", "Panoramique · droite"),
                    ("pan_up", "Panoramique · haut"),
                    ("pan_down", "Panoramique · bas"),
                ],
                default="zoom_in",
                max_length=12,
            ),
        ),
    ]