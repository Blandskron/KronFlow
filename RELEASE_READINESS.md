# Release readiness

KronFlow (formerly Flowkron) Community v1.0 (`tenant_schema_v16`, Apache-2.0) has completed all functional implementation and passed full CI validation on `main` (`c821991`, [Validate run `45222208571`](https://github.com/Blandskron/flowkron/actions/runs/45222208571) — builds, PostgreSQL integration suites, repeatable `v3–v16` upgrade matrix, contract validators, security audits, and standard/demo Compose smoke tests).

The [Community v1 release gates](docs/planning/v1/RELEASE_GATES.md) and [implementation traceability](docs/planning/v1/TRACEABILITY.md) define the evidence required for RC promotion and each enabled production channel.

## Validate the release candidate

- Run [Validate](.github/workflows/validate.yml) from a clean checkout. It builds the SPAs, runs service tests and contract checks, audits dependencies and Git history, and starts both Compose variants with isolated, synthetic instances.
- The demo smoke covers CRM and Django admin logins, the demo workspace, document upload and simulation, contact submission, rejection of refresh tokens used as access credentials, and suspension/reactivation. The standard smoke verifies that no superuser exists on first start, uses the console verification email, and creates a new login and workspace.
- Verify the exact archive contains only intended versioned files. Never publish `.env`, signing keys, WhatsApp credentials, local logs, backups or databases. Use [the private security form](https://github.com/Blandskron/flowkron/security/advisories/new) to report problems.
- Both SPA production dependency trees are audited separately from the development toolchain. CI temporarily tracks [the unpatched development advisory for picomatch](https://github.com/advisories/GHSA-fc5q-39xc-vjpf) through an exception scoped to that advisory and expiring on 18 December 2026. Critical and other high-severity findings still fail. Do not expose Angular development servers or accept arbitrary glob patterns in build jobs. Remove the exception when a compatible fix is available.
- Review [third-party licenses and redistribution](THIRD_PARTY.md) and generate inventory and notices for the exact artifact. A preview tag can ship source only. The Baileys image needs a separate distribution review.

## Before hosting or announcing a stable release

- Validate a backup restore and a migration in an isolated deployment. Ensure the IAM private PEM is never mounted into validators. For installations previously running the vulnerable version, inspect archived/deleted workspaces for orphaned Operational runtimes and WhatsApp sessions before re-exposing services. Review old role assignments and invitations, and rotate the JWT key if it may have been exposed.
- Configure TLS, exposed origins and hosts, secrets, Redis/PostgreSQL grants, telemetry and a recovery process. The per-process admission controls complement ingress limits; they do not constitute distributed rate limiting.
- Refresh credentials no longer authenticate to backends. Previously issued access JWTs can keep their claims until expiration in services that verify them locally; plan logout/revocation and role changes with the configured access lifetime in mind.
- Confirm sandbox delivery with authorized Resend, Google and Groq configurations. Test a dedicated WhatsApp account for linking, automatic replies, consent withdrawal, overload and disconnect. WhatsApp turns become durable after Operational admits them. Requests still in the connector's in-memory queue can be lost on restart. See [turn recovery](flowkron-operational-service/docs/TURN_RECOVERY.md).
- Use deployment-specific privacy and retention terms. Workspace deletion stops integrations; it is not a purge of the separately stored CRM data. Define who may authorize retention, export and deletion of that data.
