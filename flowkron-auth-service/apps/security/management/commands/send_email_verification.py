from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import UserProfile
from apps.security.services import create_email_token, send_verification_email


class Command(BaseCommand):
    help = "Envia un nuevo token de verificacion de correo a un usuario existente."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--force", action="store_true", help="Envia el token aunque el correo ya este verificado.")
        parser.add_argument("--print-token", action="store_true", help="Genera y muestra el token sin enviar correo.")

    def handle(self, *args, **options):
        email = options["email"].lower()
        user = get_user_model().objects.filter(email__iexact=email).first()
        if not user:
            raise CommandError(f"No existe usuario con email {email}.")

        profile, _ = UserProfile.objects.get_or_create(user=user, defaults={"display_name": user.get_full_name()})
        if profile.email_verified_at and not options["force"]:
            self.stdout.write(self.style.WARNING(f"El correo {email} ya esta verificado. Usa --force para reenviar."))
            return

        if options["print_token"]:
            token = create_email_token(user)
            self.stdout.write(self.style.WARNING("Token generado para entrega manual. No lo compartas por canales inseguros."))
            self.stdout.write(token)
            return

        if not send_verification_email(user):
            raise CommandError(f"No se pudo enviar el token de verificacion a {email}. Revisa la configuracion SMTP.")

        self.stdout.write(self.style.SUCCESS(f"Token de verificacion enviado a {email}."))
