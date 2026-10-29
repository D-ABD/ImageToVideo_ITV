from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("studio", "0004_alter_scene_motion")]

    operations = [
        migrations.AlterField(
            model_name="videoproject",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("preparing", "Preparing"),
                    ("prepared", "Prepared"),
                    ("processing", "Processing"),
                    ("ready", "Ready"),
                    ("error", "Error"),
                ],
                default="draft",
                max_length=16,
            ),
        ),
    ]