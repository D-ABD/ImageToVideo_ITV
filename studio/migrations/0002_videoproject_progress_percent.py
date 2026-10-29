from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("studio", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="videoproject",
            name="progress_percent",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]