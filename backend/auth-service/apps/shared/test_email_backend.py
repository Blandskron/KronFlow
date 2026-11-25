from unittest.mock import Mock, patch

import requests
from django.core.mail import EmailMultiAlternatives, send_mail
from django.test import SimpleTestCase, override_settings

from .email_backend import EmailGatewayError


@override_settings(
    EMAIL_BACKEND="apps.shared.email_backend.EmailGatewayBackend",
    MAIL_GATEWAY_URL="http://gateway:8000/",
    MAIL_INTERNAL_API_KEY="test-gateway-key",
    MAIL_SENDER_KEY="flowkron",
    EMAIL_TIMEOUT=25,
)
class EmailGatewayBackendTests(SimpleTestCase):
    @patch("apps.shared.email_backend.requests.post")
    def test_sends_text_and_html_with_an_authorized_sender_key(self, post):
        post.return_value = Mock(
            status_code=200, **{"json.return_value": {"success": True}}
        )
        email = EmailMultiAlternatives(
            "Welcome",
            "Verify your email",
            "ignored@example.com",
            ["Recipient <person@example.com>"],
        )
        email.attach_alternative("<p>Verify your email</p>", "text/html")

        self.assertEqual(email.send(), 1)
        self.assertEqual(
            post.call_args.args[0], "http://gateway:8000/api/v1/emails/send"
        )
        options = post.call_args.kwargs
        self.assertEqual(
            options["headers"], {"Authorization": "Bearer test-gateway-key"}
        )
        self.assertEqual(options["timeout"], 25)
        self.assertFalse(options["allow_redirects"])
        payload = options["json"]
        self.assertEqual(payload.pop("idempotency_key").split("-")[0], "flowkron")
        self.assertEqual(
            payload,
            {
                "sender_key": "flowkron",
                "to": ["person@example.com"],
                "subject": "Welcome",
                "text": "Verify your email",
                "html": "<p>Verify your email</p>",
            },
        )

    @patch("apps.shared.email_backend.requests.post")
    def test_rejects_unsuccessful_delivery(self, post):
        post.return_value = Mock(status_code=503)
        with self.assertRaisesMessage(EmailGatewayError, "HTTP 503"):
            send_mail("Welcome", "Verify", "from@example.com", ["user@example.com"])

    @patch("apps.shared.email_backend.requests.post", side_effect=requests.Timeout)
    def test_honors_fail_silently_on_transport_error(self, post):
        self.assertEqual(
            send_mail(
                "Welcome",
                "Verify",
                "from@example.com",
                ["user@example.com"],
                fail_silently=True,
            ),
            0,
        )
