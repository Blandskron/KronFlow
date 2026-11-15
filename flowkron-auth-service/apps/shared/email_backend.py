import uuid
from email.utils import getaddresses

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class EmailGatewayError(RuntimeError):
    """The transactional gateway did not accept the message."""


class EmailGatewayBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages or []:
            if not message.recipients():
                continue
            try:
                self._send(message)
            except EmailGatewayError:
                if not self.fail_silently:
                    raise
            else:
                sent += 1
        return sent

    def _send(self, message):
        if not all(
            (
                settings.MAIL_GATEWAY_URL,
                settings.MAIL_INTERNAL_API_KEY,
                settings.MAIL_SENDER_KEY,
            )
        ):
            raise EmailGatewayError("Email gateway configuration is incomplete.")
        if (
            message.cc
            or message.bcc
            or message.attachments
            or len(message.reply_to or []) > 1
        ):
            raise EmailGatewayError(
                "Email gateway does not support this message format."
            )

        payload = {
            "sender_key": settings.MAIL_SENDER_KEY,
            "to": [address for _, address in getaddresses(message.to)],
            "subject": message.subject,
            "idempotency_key": f"flowkron-{uuid.uuid4()}",
            ("html" if message.content_subtype == "html" else "text"): message.body,
        }
        for content, content_type in getattr(message, "alternatives", ()):
            if content_type == "text/html":
                payload["html"] = content
        if message.reply_to:
            payload["reply_to"] = getaddresses(message.reply_to)[0][1]

        try:
            response = requests.post(
                f"{settings.MAIL_GATEWAY_URL.rstrip('/')}/api/v1/emails/send",
                json=payload,
                headers={"Authorization": f"Bearer {settings.MAIL_INTERNAL_API_KEY}"},
                timeout=settings.EMAIL_TIMEOUT,
                allow_redirects=False,
            )
        except requests.RequestException:
            raise EmailGatewayError("Email gateway request failed.") from None
        if not 200 <= response.status_code < 300:
            raise EmailGatewayError(
                f"Email gateway returned HTTP {response.status_code}."
            )
        try:
            accepted = response.json()
        except ValueError:
            raise EmailGatewayError(
                "Email gateway returned an invalid response."
            ) from None
        if not isinstance(accepted, dict) or accepted.get("success") is not True:
            raise EmailGatewayError("Email gateway did not accept the message.")
