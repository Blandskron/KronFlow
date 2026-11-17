# Changelog

## Unreleased

- IAM binds role and API key writes to the authorized workspace and protects system roles and the last active owner. A workspace must be explicitly suspended or activated; changing `status` through a normal update now returns 400.
- Operational and Agent Core accept IAM access tokens only. CRM reads require `users.read`, lead edits require `crm.manage`, agent configuration and context require `agents.create`, and sensitive audit routes require `audit.read`.
- Suspending or deleting a workspace blocks its Operational runtime and disconnects a configured WhatsApp session. A suspended workspace must be activated before provisioning, and its WhatsApp device must be paired again.
- WhatsApp inbox admission and document extraction have resource limits. Saving consent preserves the contact name.
- Agent Core supports Groq chat completions with a configurable model.
- The Baileys service starts with the local stack, ready for private QR pairing and consent-gated text ingestion.
- A fresh checkout starts without a private env file. Compose generates persistent credentials and provisions the first local workspace.

## Initial release

- Flowkron by BLANDSKRON includes a CRM, public landing, dark and light themes, and reusable brand assets.
- The local stack includes IAM, Operational, Agent Core, the frontends, PostgreSQL, Redis and the Blandskron transactional mail gateway.
- WhatsApp ingestion accepts normalized events from an external adapter. Configure the adapter for inbound events, outbound delivery, consent and handoff.
- The repository includes OpenAPI and JSON Schema contracts, CI, and contribution and security documentation.

### Migrate a prior deployment

1. Back up PostgreSQL, Redis, IAM media and both signing key files. Test restoring into a disposable instance before switching. Preserve the existing database URLs and IAM secrets. If using the legacy `FLOWKRON_JWT_MOUNT` for the private directory, leave `FLOWKRON_JWT_PUBLIC_MOUNT` on its separate default volume or set it to a different directory containing only the public PEM. Never mount the private directory in a verifier. Relative mount paths are resolved from `flowkron-deploy/compose`. For standalone Agent Core provide `INTERNAL_TOKEN` explicitly and use `flowkron-deploy/data/jwt-public` for the public PEM.
2. Preserve the existing Django and signing-key encryption secrets. If reusing encrypted signing keys, set `SIGNING_KEY_ENCRYPTION_SALT` to the salt used by the prior installation before starting IAM. Use the new default salt for a fresh installation.
3. The default token issuer and audience are now `flowkron-auth-service` and `flowkron`. Operators can supply custom values consistently across the backends with `JWT_ISSUER` and `JWT_AUDIENCE`. Sign in again after the cutover because the CRM uses Flowkron-specific browser storage keys.
4. If automated superuser setup remains enabled, set `IAM_PLATFORM_TENANT_SLUG` to the existing administrative tenant slug to reuse its membership and roles.
5. Configure and verify mail with a sandbox sender before switching production delivery. Update consumers that match problem-type URIs or JSON Schema IDs by value.
