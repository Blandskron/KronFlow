import unittest
from types import SimpleNamespace

from starlette.requests import Request

from app.core.contracts import error_envelope, request_meta, success_envelope
from app.core.tenant_resolver import TenantContext


class ContractMetadataTests(unittest.TestCase):
    def request(self):
        request = Request({"type": "http", "method": "GET", "path": "/api/v1/conversations",
                           "headers": [(b"x-tenant-id", b"999"), (b"x-flowkron-tenant", b"999")]})
        request.state.request_id = "synthetic-request"
        request.state.correlation_id = "synthetic-correlation"
        return request

    def envelopes(self, request):
        return (success_envelope({}, 200, request),
                error_envelope(status_code=409, request=request, detail="Synthetic conflict"))

    def test_resolved_operational_tenant_wins_over_principal_and_headers(self):
        request = self.request()
        request.state.tenant = TenantContext(7, "synthetic", "tenant_synthetic", "synthetic", "free", "active")
        request.state.user = SimpleNamespace(tenant_id=8, user_id="user-1")
        for envelope in self.envelopes(request):
            self.assertEqual(envelope["meta"]["tenant_id"], "7")
            self.assertEqual(envelope["meta"]["request_id"], "synthetic-request")
            self.assertEqual(envelope["meta"]["correlation_id"], "synthetic-correlation")

    def test_authenticated_principal_is_available_before_runtime_resolution(self):
        request = self.request()
        request.state.user = SimpleNamespace(tenant_id=8, user_id="user-1")
        for envelope in self.envelopes(request):
            self.assertEqual(envelope["meta"]["tenant_id"], "8")
        self.assertEqual(request_meta(request)["user_id"], "user-1")

    def test_unverified_headers_never_populate_tenant_metadata(self):
        for envelope in self.envelopes(self.request()):
            self.assertIsNone(envelope["meta"]["tenant_id"])

    def test_legacy_tenant_context_shape_remains_supported(self):
        request = self.request()
        request.state.tenant = SimpleNamespace(tenant_id="legacy-tenant")
        self.assertEqual(request_meta(request)["tenant_id"], "legacy-tenant")
