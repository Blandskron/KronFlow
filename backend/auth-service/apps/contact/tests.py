from django.test import TestCase
from rest_framework.test import APIClient

from .models import ContactMessage


class ContactApiTests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def _payload(self):
        return {
            "name": "Cliente Ejemplo",
            "email": "cliente@example.com",
            "company": "Empresa Ejemplo",
            "phone": "+56 9 1234 5678",
            "message": "Quiero conocer Flowkron para ventas.",
            "accept_terms": True,
        }

    def test_contact_requires_csrf(self):
        response = self.client.post("/api/v1/contact/messages/", self._payload(), format="json")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(ContactMessage.objects.count(), 0)

    def test_contact_creates_message_with_csrf(self):
        csrf_response = self.client.get("/api/v1/contact/csrf/")
        token = csrf_response.data["data"]["csrfToken"]

        response = self.client.post(
            "/api/v1/contact/messages/",
            self._payload(),
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(ContactMessage.objects.count(), 1)

    def test_contact_rejects_html_payload(self):
        csrf_response = self.client.get("/api/v1/contact/csrf/")
        token = csrf_response.data["data"]["csrfToken"]
        payload = self._payload()
        payload["message"] = "<script>alert(1)</script>"

        response = self.client.post(
            "/api/v1/contact/messages/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ContactMessage.objects.count(), 0)
