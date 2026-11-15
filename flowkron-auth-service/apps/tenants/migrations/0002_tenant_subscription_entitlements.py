from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tenant",
            name="plan",
            field=models.CharField(
                choices=[("free", "Free"), ("starter", "Starter"), ("pro", "Pro"), ("enterprise", "Enterprise")],
                default="free",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="subscription_status",
            field=models.CharField(
                choices=[
                    ("free", "Free"),
                    ("trialing", "Trialing"),
                    ("active", "Active"),
                    ("past_due", "Past due"),
                    ("canceled", "Canceled"),
                    ("unpaid", "Unpaid"),
                ],
                default="free",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="subscription_provider",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="tenant",
            name="subscription_external_id",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="tenant",
            name="subscription_current_period_end",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
