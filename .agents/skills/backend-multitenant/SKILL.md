---
name: backend-multitenant
description: Guidelines and verification workflows for modifying KronFlow backend microservices (operational-service, auth-service, agent-core, mail-service, baileys-services), PostgreSQL 18 schema-per-tenant models, repeatable migrations, outbox workers, and RBAC boundaries.
---

# Backend Multi-Tenant Skill — KronFlow

Use this skill whenever editing `backend/operational-service`, `backend/auth-service`, `backend/agent-core`, `backend/mail-service`, or `backend/baileys-services`.

## 1. Service Ownership Rules

- **`backend/auth-service` (Django 5 / DRF):** Owns users, memberships, plans, RBAC, MFA TOTP, RS256 JWT issuance, signing keys, and service accounts. Never stores tenant CRM tables.
- **`backend/operational-service` (FastAPI / PG 18):** Owns `public` runtime metadata (`tenant_runtime`, `migration_registry`, `system_events`, `webchat_widgets`, `channel_webhook_routes`, `capture_access`) and all per-tenant schemas (`tenant_schema_v21`). Also runs the durable outbox worker (`app/worker.py` + `app/services/outbox_dispatcher.py`).
- **`backend/agent-core` (FastAPI):** Channel-agnostic AI runtime, document extraction, RAG, and simulator. In production (`PERSISTENCE_MODE=operational`), it delegates storage/retrieval to Operational over `/internal/*` and never creates tenant schemas.
- **`backend/mail-service` (FastAPI / Redis):** Transactional email gateway over Resend HTTPS. Uses Redis for distributed idempotency; never accepts SMTP credentials.
- **`backend/baileys-services` (Node 24 / TS):** Optional WhatsApp QR lab connector with durable turn handoff to Operational.

## 2. Non-Negotiable Invariants

1. **Tenant isolation:** Always bind tenant queries via `schema_translate_map` (`app/services/tenant_data.py`). Never trust client-supplied `schema_name` and never interpolate SQL identifiers without `sanitize_schema_name`.
2. **Auth boundaries:**
   - Dashboard routes require RS256 access JWT (`refresh` tokens must be rejected) and explicit permission resolvers (`users.read`, `crm.manage`, `agents.create`, `audit.read`).
   - `/internal/*` routes require `X-Internal-Token` and must never be called by frontends.
   - Public webhooks (Meta, Shopify, Mercado Pago, Twilio, Resend) must verify HMAC/provider signatures and deduplicate by `(provider, external_event_id)`.
3. **Repeatable migrations:** Any new tenant table or column must be additive, idempotent, registered in `app/tenant_models/__init__.py`, migrated in `tenant_provisioning_service.py`, reflected in `TENANT_MIGRATION_VERSION` (`app/core/config.py`), and covered by `tests/test_tenant_upgrade_matrix.py`.
4. **Durable effects & privacy:** Outbound sends go through `action_outbox_jobs` with `SKIP LOCKED` leases and payload-hash conflict checks. Privacy erasure (`/erase`) and opt-outs (`contact_suppressions`) must cancel waiting workflows and redact personal data transactionally.
5. **Synthetic test tokens:** Use low-entropy, clearly synthetic test strings in unit/integration tests so `gitleaks` does not flag false positives.

## 3. Verification Checklist

Run from the modified service directory:

- **`backend/auth-service`:**
  ```powershell
  ruff check --select E9,F63,F7,F82 .
  python manage.py check
  python manage.py test
  ```
- **`backend/operational-service`:**
  ```powershell
  ruff check --select E9,F63,F7,F82 .
  python -m unittest discover -s tests -v
  python -c "from app.main import app; assert app.openapi()['paths']"
  ```
- **`backend/agent-core` / `backend/mail-service`:**
  ```powershell
  ruff check --select E9,F63,F7,F82 .
  python -m pytest -q
  ```
- **`backend/baileys-services`:**
  ```powershell
  npm test
  ```
