from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import UserProfile


@receiver(pre_save, sender=get_user_model())
def remember_previous_email(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_email = ""
        return
    instance._previous_email = sender.objects.filter(pk=instance.pk).values_list("email", flat=True).first() or ""


@receiver(post_save, sender=get_user_model())
def ensure_profile(sender, instance, created, **kwargs):
    profile, _ = UserProfile.objects.get_or_create(user=instance, defaults={"display_name": instance.get_full_name()})
    previous_email = getattr(instance, "_previous_email", "") or ""
    email_changed = bool(instance.email and previous_email.lower() != instance.email.lower())
    should_verify_email = created or email_changed
    if getattr(instance, "_skip_email_verification", False):
        return
    if not should_verify_email or not instance.email or not instance.is_active or instance.is_superuser:
        return

    if getattr(settings, "IAM_AUTO_VERIFY_USER_EMAIL", False):
        if not profile.email_verified_at:
            profile.email_verified_at = timezone.now()
            profile.save(update_fields=["email_verified_at", "updated_at"])
        return

    if profile.email_verified_at:
        profile.email_verified_at = None
        profile.save(update_fields=["email_verified_at", "updated_at"])

    def send_created_user_verification():
        from apps.audit.models import AuditLog
        from apps.audit.services import audit
        from apps.security.services import send_verification_email

        if created:
            audit(AuditLog.Event.USER_CREATED, user=instance)
        send_verification_email(instance)

    transaction.on_commit(send_created_user_verification)
