import smtplib

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Prueba conexion y autenticacion SMTP con la configuracion efectiva de Django."

    def add_arguments(self, parser):
        parser.add_argument("--send-to", help="Email destino para enviar un mensaje de prueba despues del login SMTP.")

    def handle(self, *args, **options):
        self.stdout.write(f"EMAIL_HOST={settings.EMAIL_HOST}")
        self.stdout.write(f"EMAIL_PORT={settings.EMAIL_PORT}")
        self.stdout.write(f"EMAIL_USE_TLS={settings.EMAIL_USE_TLS}")
        self.stdout.write(f"EMAIL_USE_SSL={settings.EMAIL_USE_SSL}")
        self.stdout.write(f"EMAIL_TIMEOUT={settings.EMAIL_TIMEOUT}")
        self.stdout.write(f"EMAIL_HOST_USER={settings.EMAIL_HOST_USER}")
        self.stdout.write(f"DEFAULT_FROM_EMAIL={settings.DEFAULT_FROM_EMAIL}")
        self.stdout.write(f"EMAIL_HOST_PASSWORD_SET={bool(settings.EMAIL_HOST_PASSWORD)}")
        self.stdout.write(f"EMAIL_HOST_PASSWORD_LEN={len(settings.EMAIL_HOST_PASSWORD or '')}")

        try:
            if settings.EMAIL_USE_SSL:
                smtp = smtplib.SMTP_SSL(settings.EMAIL_HOST, settings.EMAIL_PORT, timeout=settings.EMAIL_TIMEOUT)
            else:
                smtp = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT, timeout=settings.EMAIL_TIMEOUT)
            with smtp:
                smtp.ehlo()
                if settings.EMAIL_USE_TLS:
                    smtp.starttls()
                    smtp.ehlo()
                smtp.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
                self.stdout.write(self.style.SUCCESS("SMTP_LOGIN_OK"))
                if options.get("send_to"):
                    subject = "Prueba SMTP Flowkron"
                    body = "Prueba de envio SMTP desde flowkron-auth-service."
                    message = (
                        f"From: {settings.DEFAULT_FROM_EMAIL}\r\n"
                        f"To: {options['send_to']}\r\n"
                        f"Subject: {subject}\r\n"
                        "\r\n"
                        f"{body}\r\n"
                    )
                    smtp.sendmail(settings.DEFAULT_FROM_EMAIL, [options["send_to"]], message)
                    self.stdout.write(self.style.SUCCESS(f"SMTP_SEND_OK {options['send_to']}"))
        except smtplib.SMTPAuthenticationError as exc:
            raise CommandError(f"SMTP_AUTH_FAILED code={exc.smtp_code} message={exc.smtp_error!r}") from exc
        except Exception as exc:
            raise CommandError(f"SMTP_TEST_FAILED {exc.__class__.__name__}: {exc}") from exc
