from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("studio", "0002_videoproject_progress_percent")]

    operations = [
        migrations.AddField(
            model_name="scene",
            name="motion_amount",
            field=models.PositiveSmallIntegerField(default=25),
        ),
    ]