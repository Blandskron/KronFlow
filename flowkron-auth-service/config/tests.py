from django.test import SimpleTestCase


class UrlFallbackTests(SimpleTestCase):
    def test_unknown_route_redirects_to_api_docs(self):
        response = self.client.get("/ruta-no-autorizada/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/api/docs/")
