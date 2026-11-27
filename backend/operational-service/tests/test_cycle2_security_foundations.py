"""Cycle 2 (PRV-006, PRV-007, PRV-008, PRV-009 / QG-2) verification tests."""

from pathlib import Path
import unittest

import app.public_models  # noqa: F401
from app.core.config import Settings
from app.core.crypto import (
    ENCRYPTED_PREFIX,
    compute_blind_index,
    decrypt_value,
    encrypt_value,
    is_encrypted,
    rotate_ciphertext,
)
from app.core.database import Base
from app.core.security import REVOCATION_KEY_PREFIX, is_jwt_revoked


REPO_ROOT = Path(__file__).resolve().parents[3]


class _FakeRedis:
    def __init__(self, store: dict[str, str] | None = None, *, fail: bool = False):
        self.store = dict(store or {})
        self.fail = fail

    def mget(self, keys: list[str]) -> list[str | None]:
        if self.fail:
            raise ConnectionError("synthetic redis outage")
        return [self.store.get(k) for k in keys]


class Cycle2SecurityFoundationsTests(unittest.TestCase):
    def test_prv006_nginx_configs_enforce_strict_csp_and_hsts(self):
        for rel in ("frontend/app/nginx.conf", "frontend/landing/nginx.conf"):
            content = (REPO_ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("Content-Security-Policy", content, f"Missing CSP in {rel}")
            self.assertIn("Strict-Transport-Security", content, f"Missing HSTS in {rel}")
            self.assertNotIn("unsafe-eval", content, f"unsafe-eval must not appear in {rel}")
            self.assertIn("object-src 'none'", content, f"Missing object-src 'none' in {rel}")
            self.assertIn("frame-ancestors 'self'", content, f"Missing frame-ancestors in {rel}")
            self.assertGreaterEqual(
                content.count("Content-Security-Policy"),
                2,
                f"CSP must be present in both server and /index.html blocks in {rel}",
            )

    def test_prv007_jwt_fast_revocation_via_redis_and_safe_fallback(self):
        settings = Settings(_env_file=None, redis_url="")
        claims = {"jti": "jti-1", "session_id": "42", "user_id": "7", "tenant_id": "99", "iat": 1000}

        # Clean Redis -> not revoked.
        self.assertFalse(is_jwt_revoked(claims, settings, redis_client=_FakeRedis({})))

        # Revoked by jti.
        self.assertTrue(
            is_jwt_revoked(claims, settings, redis_client=_FakeRedis({f"{REVOCATION_KEY_PREFIX}jti:jti-1": "1"}))
        )
        # Revoked by session_id.
        self.assertTrue(
            is_jwt_revoked(claims, settings, redis_client=_FakeRedis({f"{REVOCATION_KEY_PREFIX}session:42": "1"}))
        )
        # Revoked by user epoch (iat <= revoked_at).
        self.assertTrue(
            is_jwt_revoked(claims, settings, redis_client=_FakeRedis({f"{REVOCATION_KEY_PREFIX}user:7": "1000"}))
        )
        # Token issued AFTER user epoch is allowed.
        self.assertFalse(
            is_jwt_revoked(claims, settings, redis_client=_FakeRedis({f"{REVOCATION_KEY_PREFIX}user:7": "999"}))
        )
        # Revoked by tenant suspension epoch.
        self.assertTrue(
            is_jwt_revoked(claims, settings, redis_client=_FakeRedis({f"{REVOCATION_KEY_PREFIX}tenant:99": "1005"}))
        )
        # Safe fallback when Redis is unreachable.
        self.assertFalse(is_jwt_revoked(claims, settings, redis_client=_FakeRedis(fail=True)))

    def test_prv008_envelope_encryption_rotation_and_blind_index(self):
        key_v1 = "synthetic-test-key-v1"
        key_v2 = "synthetic-test-key-v2"

        raw_rut = "12.345.678-5"
        ct_v1 = encrypt_value(raw_rut, keys=[key_v1])
        self.assertIsNotNone(ct_v1)
        self.assertTrue(is_encrypted(ct_v1))
        self.assertTrue(ct_v1.startswith(ENCRYPTED_PREFIX))
        self.assertNotIn(raw_rut, ct_v1)
        self.assertEqual(decrypt_value(ct_v1, keys=[key_v1]), raw_rut)

        # Key rotation: MultiFernet decrypts v1 with [key_v2, key_v1] and rotates to key_v2.
        self.assertEqual(decrypt_value(ct_v1, keys=[key_v2, key_v1]), raw_rut)
        ct_v2 = rotate_ciphertext(ct_v1, keys=[key_v2, key_v1])
        self.assertTrue(is_encrypted(ct_v2))
        self.assertEqual(decrypt_value(ct_v2, keys=[key_v2]), raw_rut)

        # Legacy plaintext passes through decrypt_value safely.
        self.assertEqual(decrypt_value("legacy-plain-token", keys=[key_v2]), "legacy-plain-token")

        # Blind index normalizes RUT formats and is deterministic per key/purpose.
        idx_a = compute_blind_index("12.345.678-5", purpose="rut", key="blind-key-1")
        idx_b = compute_blind_index("12345678-5", purpose="rut", key="blind-key-1")
        idx_other = compute_blind_index("12345678-5", purpose="rut", key="blind-key-2")
        self.assertEqual(idx_a, idx_b)
        self.assertEqual(len(idx_a), 64)
        self.assertNotEqual(idx_a, idx_other)

    def test_prv009_all_tenant_scoped_public_tables_carry_auth_tenant_id(self):
        tenant_scoped_public_tables = (
            "public.webchat_widgets",
            "public.channel_webhook_routes",
            "public_capture_forms",
            "public_unsubscribe_tokens",
            "scoped_integration_credentials",
            "system_events",
            "billing_reference",
            "tenant_runtime",
        )
        for table_name in tenant_scoped_public_tables:
            self.assertIn(table_name, Base.metadata.tables, f"Expected public table {table_name}")
            col_names = {c.name for c in Base.metadata.tables[table_name].columns}
            self.assertIn("auth_tenant_id", col_names, f"Table {table_name} missing auth_tenant_id isolation column")


if __name__ == "__main__":
    unittest.main()
