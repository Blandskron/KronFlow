# Changelog

## Initial release

- Flowkron by BLANDSKRON includes a CRM, public landing, dark and light themes, and reusable brand assets.
- The local stack includes IAM, Operational, Agent Core, the frontends, PostgreSQL, Redis and the Blandskron transactional mail gateway.
- WhatsApp ingestion accepts normalized events from an external adapter. Configure the adapter for inbound events, outbound delivery, consent and handoff.
- The repository includes OpenAPI and JSON Schema contracts, CI, and contribution and security documentation.

### Migrate a prior deployment

1. Back up PostgreSQL, Redis, IAM media and both signing key files. Test restoring into a disposable instance before switching. The default Compose project, DB names and volume names are Flowkron-specific. Restore into the new volumes or intentionally use your original DB with explicit connection settings. Set `FLOWKRON_DATA_DIR` to the location of existing IAM media and signing files if needed.
2. Preserve the existing Django and signing-key encryption secrets. If reusing encrypted signing keys, set `SIGNING_KEY_ENCRYPTION_SALT` to the salt used by the prior installation before starting IAM. Use the new default salt for a fresh installation.
3. The default token issuer and audience are now `flowkron-auth-service` and `flowkron`. Operators can supply custom values consistently across the backends with `JWT_ISSUER` and `JWT_AUDIENCE`. Sign in again after the cutover because the CRM uses Flowkron-specific browser storage keys.
4. If automated superuser setup remains enabled, set `IAM_PLATFORM_TENANT_SLUG` to the existing administrative tenant slug to reuse its membership and roles.
5. Configure and verify mail with a sandbox sender before switching production delivery. Update consumers that match problem-type URIs or JSON Schema IDs by value.
