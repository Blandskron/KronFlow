# Integration Map

## Servicios y contratos

| Servicio | Tecnologia | Puerto | Usa contratos | Publica contratos |
| --- | --- | --- | --- | --- |
| `flowkron-auth-service` | Django/DRF + RS256 JWT | 8000 | response, error, contact | OpenAPI IAM completo (auth, users, tenants, rbac, sessions, security, audit) |
| `flowkron-operational-service` | FastAPI + SQLAlchemy + Psycopg | 8001 | response, error, AI, events | OpenAPI operational v0.3.1 (ingest, leads, conversations, analytics, internal context) |
| `flowkron-agent-core` | FastAPI + HTTPX (modo operational) | 8002 | AI request/response, internal context | OpenAPI agent-core v0.3.1 (chat, context, setup, local-only rules/traces) |
| `flowkron-front-landing-angular` | Angular 21 + standalone | - | contact public API, CSRF | - |
| `flowkron-front-app-angular` | Angular 21 + standalone | - | Auth, Operational, Agent Core, errors | - |
| `flowkron-deploy` | Docker Compose | - | Healthcheck endpoints | - |

---

## Flujo de autenticacion

```text
Browser/Mobile
  -> POST /api/v1/auth/login/ (auth-service:8000)
  <- JWT access (RS256) + refresh token

Dashboard Angular
  -> Authorization: Bearer <JWT> (operational-service:8001 / agent-core:8002)
  JWT contiene: tenant_id, roles, permissions, subscription
```

---

## Flujo de ingesta WhatsApp

```text
WhatsApp Cloud API
  -> POST /api/v1/ingest/whatsapp/message (operational-service:8001)
      Headers: X-Tenant-Code + X-Ingest-Key
  <- IngestResponse { lead_id, conversation_id, message_id }

  -> POST /api/v1/agent/messages (agent-core:8002)
      Bearer JWT o X-Tenant-Id (local dev)
  <- AgentMessageResponse { reply, requires_human, actions, confidence, sources }

  -> POST /api/v1/ingest/whatsapp/lead-classification (operational-service:8001)
  -> POST /api/v1/ingest/whatsapp/dashboard-messages (operational-service:8001)
```

---

## Flujo de contexto empresarial

```text
Dashboard Angular (front-app)
  -> /api/v1/context/* (agent-core:8002)
     documentos, status, templates, upload-file

Agent Core (persistence=operational)
  -> /internal/tenants/{id}/context/* (operational-service:8001)
      Header: X-Internal-Token

Operational resuelve schema_name a partir del tenant_id logico.
Persistencia real: business_context_documents y document_chunks en schema tenant.
Re-subidas de un mismo filename generan version=max(version)+1 por tenant.
```

---

## Flujo de aprovisionamiento de tenant

```text
Auth Service (al activar subscription/provisionar runtime)
  -> POST /internal/tenants/provision (operational-service:8001)
      Header: X-Internal-Token
  <- { runtime, ingest_key, created }

```

---

## Reglas de contrato

1. Ningun contrato publico acepta `schema_name`; lo resuelve Operational internamente.
2. El prefijo real de rutas es `/api/v1/` en auth-service, operational-service y agent-core.
3. JWT estandar RS256 emitido por auth-service, verificado por operational-service y agent-core con la clave publica PEM.
4. El claim `tenant_id` viaja en el JWT y Operational/Agent Core lo usan para resolver runtime/tenant.
5. Los endpoints de ingesta se autentican con `X-Tenant-Code` + `X-Ingest-Key`, no JWT.
6. Los endpoints internos usan `X-Internal-Token`; nunca se exponen al cliente.
7. Rutas Agent Core de forms, rules, conversation history y traces son local/stateful o pueden responder 501 en modo integrado.

---

## Tablas de contexto por tenant

| Tabla | Servicio que escribe | Servicio que lee |
| --- | --- | --- |
| `business_context_documents` | Operational via `/internal` | Agent Core via `/internal` |
| `document_chunks` | Operational via `/internal` | Agent Core via `/internal` |
| `document_embeddings` | Operational futuro | Agent Core futuro |
| `tenant_agent_profiles` | Operational | Agent Core |
| `business_context_forms` | Operational estructura futura / Agent Core local | No es flujo productivo integrado actual |
| `leads` | Operational ingest | Dashboard Angular |
| `conversaciones` | Operational ingest | Dashboard Angular |
| `mensajes_dashboard` | Operational ingest | Dashboard Angular |
