# Release readiness

KronFlow (formerly Flowkron) Community v1.0 (`tenant_schema_v22`, Apache-2.0) has completed all functional and privacy/security compliance implementation (Cycles 0–9, `PRV-001`–`PRV-028`) and enforces automated CI validation on `main` (builds, PostgreSQL integration suites, repeatable `v3–v22` upgrade matrix, `privacy-compliance` quality gates, CycloneDX SBOMs, security audits, and standard/demo Compose smoke tests).

See [AGENTS.md](AGENTS.md), [ARCHITECTURE.md](ARCHITECTURE.md), [SECURITY.md](SECURITY.md), and [compliance/DPIA_TEMPLATE_ISO29134.md](compliance/DPIA_TEMPLATE_ISO29134.md) for service boundaries, invariants, incident SLAs, DPIA templates, and CI validation commands.

## Validate the release candidate

- Run [Validate](.github/workflows/validate.yml) from a clean checkout. It builds the SPAs, runs service tests, contract checks, and the dedicated `privacy-compliance` job (PII inventory parity, `pii_scrubber`, Nginx CSP/HSTS, crypto/revocation, ARCOP-B, hash-chain integrity, and incident SLAs), audits dependencies and Git history (`gitleaks`, `pip-audit`, `npm audit`), uploads CycloneDX SBOM artifacts, and starts both Compose variants with isolated, synthetic instances.
- The demo smoke covers CRM and Django admin logins, the demo workspace, document upload and simulation, contact submission, rejection of refresh tokens used as access credentials, and suspension/reactivation. The standard smoke verifies that no superuser exists on first start, uses the console verification email, and creates a new login and workspace.
- Verify the exact archive contains only intended versioned files. Never publish `.env`, signing keys, WhatsApp credentials, local logs, backups or databases. Use [the private security form](https://github.com/Blandskron/KronFlow/security/advisories/new) to report problems.
- Both SPA production and development dependency trees are audited with **zero active advisory exceptions** (`.github/scripts/check-dev-audit.mjs`). Any high or critical advisory fails CI. CycloneDX SBOM artifacts are generated automatically on every push/PR (`PRV-027`).
- Review [third-party licenses and redistribution](THIRD_PARTY.md) and verify the generated SBOM artifacts against the exact release archive. A preview tag can ship source only. The Baileys image needs a separate distribution review.

## Encrypted Backup/Restore & Tombstone Reconciliation Drill (`FK-15` / `PRV-028`)

Automated verification runs in `backend/operational-service/tests/test_operational_restore.py` (`test_restore_reapplies_erasure_tombstones_with_zero_pii_resurrection`) against PostgreSQL 18 in CI. Before promoting a production deployment, operators must execute and archive an isolated restore drill recording commit SHA, dump checksum, measured RPO/RTO, and zero PII resurrection:

1. Create an encrypted PostgreSQL custom dump (`pg_dump --format=custom`) and store its SHA-256 checksum separately from the encryption key.
2. Restore into an isolated target database (`pg_restore --exit-on-error --single-transaction --no-owner --no-privileges`).
3. Reapply the post-backup erasure ledger so previously erased subjects are never resurrected:
   ```sh
   python backend/operational-service/scripts/reapply_erasure_tombstones.py
   ```
4. Verify audit chain integrity via `GET /api/v1/operational/log-limpiezas/verify-chain` and confirm `reapplied_clients` / zero residual PII.

## External Go/No-Go Gates Before Production (`PRV-029` / `QG-9`)

Technical gates `QG-0` through `QG-8` are enforced in code and CI. The following organizational, legal, and external sandbox gates must be completed and archived by the deployment operator outside the public repository prior to announcing a stable production service:

- [ ] **Legal & Policy Sign-off:** Legal review and publication of deployment-specific Privacy Policy (layered ISO/IEC 29184 notice in `frontend/landing`) and Terms of Service, plus designation of DPO (`dpo_contact_email`) and jurisdiction (`privacy_jurisdiction`) per tenant.
- [ ] **DPIA Approval:** Completed and signed [DPIA Template (`ISO/IEC 29134:2023`)](compliance/DPIA_TEMPLATE_ISO29134.md) covering conversational AI, Voice/Twilio, omnichannel messaging, and international transfers.
- [ ] **Subprocessor Contracts (DPAs / SCCs / TIAs):** Executed Data Processing Agreements, Standard Contractual Clauses, and Transfer Impact Assessments for enabled subprocessors (Groq, Resend, Meta, Twilio, Google, Shopify, Mercado Pago, HubSpot) before enabling them in `/api/v1/operational/subprocessors`.
- [ ] **External Sandbox Homologation (`FK-14`):** Validated delivery and opt-out flows with authorized Resend, Google, Twilio, and Groq accounts, plus a dedicated authorized WhatsApp account testing linking, automatic replies, consent withdrawal, overload, and disconnect (see [backend/baileys-services/README.md](backend/baileys-services/README.md)).
- [ ] **Infrastructure Hardening & `FK-15` Drill Minutes:** Configured TLS, exposed origins/hosts, secret rotation, Redis/PostgreSQL grants, ingress rate limits, JWT key isolation (IAM private PEM never mounted into validators), and signed technical minutes of the isolated `FK-15` backup/restore + tombstone drill.
