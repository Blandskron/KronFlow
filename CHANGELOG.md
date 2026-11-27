# Changelog

## Unreleased

- **Platform Phases 1–8 (`tenant_schema_v17`–`v21`, repeatable upgrade `v3–v21`):**
  - Durable Outbox worker (`worker.py` + `outbox_dispatcher.py`), scheduled campaign auto-promotion, opaque self-service unsubscribe tokens, and end-to-end delivery dispatch.
  - Multi-agent platform with immutable revisions, scoped RAG/rules/traces, persistent setup-chat, bounded specialist handoff with HITL fallback, and `/app/agents` + `/app/conversations` UI.
  - Declarative DAG workflow engine (`/app/workflows`, compiler, dry-run simulation, waiting timers, and transactional wait cancellation on reply/opt-out/erasure).
  - Tool Hub + bidirectional MCP JSON-RPC 2.0 (`POST /api/v1/mcp` + SSRF/allowlist remote MCP client `/api/v1/mcp-clients`), signed embeddable webchat, SHA-256 private attachments, and `/app/tools` UI.
  - Omnichannel Meta webhooks (HMAC-SHA256), outbound connectors (WhatsApp Cloud, Google Calendar OAuth, HubSpot), Shopify & Mercado Pago commerce reconciliation/refunds with per-currency KPIs, Twilio voice sessions + Media Streams WebSocket (`barge-in`/HITL/privacy), authorized contact merge (`/app/contacts/:id`), campaign audience preview (`/app/campaigns`), and IAM TOTP MFA enrollment UI (`/app/settings`).
- **Monorepo reorganization & documentation consolidation:**
  - Reorganized services under `backend/` (`agent-core`, `auth-service`, `baileys-services`, `mail-service`, `operational-service`), frontends under `frontend/` (`app`, `landing`), and Compose deployment under `deploy/`, removing the legacy `flowkron-` directory and service name prefixes.
  - Absorbed API contract boundaries and conventions into [`ARCHITECTURE.md`](ARCHITECTURE.md), retired `flowkron-api-contracts/`, removed completed planning roadmaps and stale audit snapshots, added the 10-screenshot platform gallery to [`README.md`](README.md), and verified cross-repository documentation links.
- **Rebranding & Design System KronFlow — Intelligent CRM (`By BLANDSKRON`):**
  - Renombrado integral de producto e interfaz de *Flowkron* a **KronFlow — Intelligent CRM** (`Smart conversations. Seamless automation.`), incorporando la skill auditada `ui-ux-pro-max` y un kit SVG original en `assets/brand/`.
  - Evolución del Design System unificado (`tokens.css`, `reset.css`, `primitives.css`) con paleta Teal/Esmeralda/Cyan, tipografía `Sora` + `Inter` + `JetBrains Mono`, retícula arquitectónica y Floating Glassmorphism (dark mode por defecto).
  - Selectores Angular migrados de `flowkron-*` a `kronflow-*`, corrección de íconos en sidebar, dock móvil deslizable y rediseño integral de Landing y `index.html`.
- **Community v1.0 & POST-v1 backend (`tenant_schema_v9`–`v16`, repeatable upgrade `v3–v16`):**
  - Durable action outbox (`FK-03`) with transactional enqueue, payload-hash conflict detection, `SKIP LOCKED` claims, `unknown` lease recovery and effect verification.
  - Persistent channel/purpose consent ledger and transactional worker send authorization serialized with concurrent suppressions (`FK-04`).
  - Human-in-the-loop conversation control (`FK-06`, `FK-19`) with compare-and-swap claims, single active operator, idempotent outbox replies (`202`), resolution, return-to-AI and tenant/conversation AI policy enforcement.
  - Commercial pipeline (`FK-29`) with editable stages, optimistic versioning, atomic stage/close events and multi-tenant isolation.
  - Typed AI action proposals and versioned human review (`FK-17`, `FK-18`) with expiration and at-most-once execution.
  - Multichannel contact points, repeatable collision-quarantining backfill, public capture forms (`FK-28`), scoped `leads:create` credentials (`FK-12`), and versioned domain events with forward replay and monotonic checkpoints (`FK-10`).
  - Campaigns and templates (`FK-30`), delegated channel connections (`FK-24`) and conversation-linked email (`FK-23`) with HTML sanitization, deduplicated approval snapshots, stub dispatch worker, durable unsubscribes and receipts.
  - Consolidated event-calibrated KPIs (`FK-09`), scoped conversation memory (`FK-20`), confirmed contact enrichment (`FK-21`), external notification deliveries (`FK-25`), tenant AI usage/cost ledger (`FK-26`), and privacy export/erasure/retention sweeps (`FK-27`).
  - Reliable HTTPS webhooks with SSRF guard and HMAC-SHA256 signing (`FK-11`), private resource-scoped attachments with retention (`FK-13`), and double-book-safe conversational scheduling (`FK-22`).

- Operational response metadata now uses the resolved IAM tenant ID for successful requests and errors, including private WhatsApp ingestion. Unverified tenant headers never populate identity metadata (FK-09).

- FK-02 persists WhatsApp turn stages, prepared replies and human handoffs in Operational. The connector resumes recoverable stages and retries acknowledgement persistence without retransmitting. Uncertain sends are observable and require evidence-based reconciliation. Existing installations must migrate to `tenant_schema_v4` before enabling the new connector; see [turn recovery and rollout](backend/operational-service/docs/TURN_RECOVERY.md).

- Added the cross-project evolution analysis and 27 prioritized Flowkron tasks, including supervised agent actions, effective AI controls, conversation memory, confirmed lead updates, scheduling, business email, delegated integrations, notifications, agent evaluation and the data privacy lifecycle. Reference implementations are excluded from the repository.

- FK-01 persists external/provider message identity, direction, channel, type, reported status and recording time in the active inbox table. Operational contracts advance to `v0.4.0`. Existing installations must apply the additive `tenant_schema_v3` migration before serving the new message model; see the [migration and rollback procedure](backend/operational-service/docs/MESSAGE_IDENTITY.md). Historical IDs are not reconstructed, and concurrent retries no longer create duplicate messages.

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

1. Back up PostgreSQL, Redis, IAM media and both signing key files. Test restoring into a disposable instance before switching. Preserve the existing database URLs and IAM secrets. If using the legacy `FLOWKRON_JWT_MOUNT` for the private directory, leave `FLOWKRON_JWT_PUBLIC_MOUNT` on its separate default volume or set it to a different directory containing only the public PEM. Never mount the private directory in a verifier. Relative mount paths are resolved from `deploy/compose`. For standalone Agent Core provide `INTERNAL_TOKEN` explicitly and use `deploy/data/jwt-public` for the public PEM.
2. Preserve the existing Django and signing-key encryption secrets. If reusing encrypted signing keys, set `SIGNING_KEY_ENCRYPTION_SALT` to the salt used by the prior installation before starting IAM. Use the new default salt for a fresh installation.
3. The default token issuer and audience are now `flowkron-auth-service` and `flowkron`. Operators can supply custom values consistently across the backends with `JWT_ISSUER` and `JWT_AUDIENCE`. Sign in again after the cutover because the CRM uses Flowkron-specific browser storage keys.
4. If automated superuser setup remains enabled, set `IAM_PLATFORM_TENANT_SLUG` to the existing administrative tenant slug to reuse its membership and roles.
5. Configure and verify mail with a sandbox sender before switching production delivery. Update consumers that match problem-type URIs or JSON Schema IDs by value.
