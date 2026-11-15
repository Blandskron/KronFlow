from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_profile_activation_onboarding")]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="google_subject",
            field=models.CharField(blank=True, max_length=255, null=True, unique=True),
        ),
    ]
