from django.db import models


class ContactMessage(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Nuevo"
        REVIEWED = "reviewed", "Revisado"
        ARCHIVED = "archived", "Archivado"

    name = models.CharField(max_length=120)
    email = models.EmailField()
    company = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    message = models.TextField(max_length=2000)
    accept_terms = models.BooleanField(default=False)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.NEW)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "iam_contact_message"
        indexes = [
            models.Index(fields=["email", "created_at"], name="iam_contact_email_created_idx"),
            models.Index(fields=["status", "created_at"], name="iam_contact_status_created_idx"),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} - {self.created_at:%Y-%m-%d %H:%M}"
