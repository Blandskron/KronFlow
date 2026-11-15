# Arquitectura técnica y flujos de extremo a extremo

## 1. Vista general

```text
Internet / navegador
  ├─ Landing Angular 21 + Nginx
  │    └─ contacto público con CSRF ───────────────> Auth Service
  └─ App Angular 21 + Nginx
       ├─ identidad, tenant y configuración ───────> Auth Service
       ├─ leads, conversaciones y analytics ───────> Operational Service
       └─ contexto empresarial y simulación ───────> Agent Core

Auth Service ── token interno ─────────────────────> Operational Service
Agent Core ── token interno y tenant lógico ───────> Operational Service
Operational Service ───────────────────────────────> PostgreSQL public + schema tenant
Auth Service ──────────────────────────────────────> PostgreSQL + Redis

```


## 2. Responsabilidad por repositorio

| Repositorio | Responsabilidad | No le pertenece |
| --- | --- | --- |
| `flowkron-auth-service` | IAM, tenants, RBAC, sesiones, JWT, MFA, credenciales y auditoría | CRM, RAG, WhatsApp y schemas de negocio |
| `flowkron-operational-service` | Runtime tenant, schema físico, datos operacionales y contexto persistente | Identidad humana y emisión de JWT |
| `flowkron-agent-core` | Runtime conversacional, plantillas, extracción, retrieval y respuestas | Provisionar tenant o elegir schema |
| `flowkron-front-app-angular` | Experiencia privada y consumo de APIs | Autoridad de seguridad o persistencia |
| `flowkron-front-landing-angular` | Marketing y contacto público | Autenticación o backend propio |
| `flowkron-api-contracts` | Interfaces compartidas y versionado | Lógica de negocio o modelos ORM |
| `flowkron-deploy` | Composición local | Plataforma productiva |

## 3. Fronteras de confianza

| Llamador | Destino | Identidad utilizada |
| --- | --- | --- |
| Navegador autenticado | Auth, Operational, Agent Core | `Authorization: Bearer <JWT RS256>` y tenant lógico |
| Landing | Auth contacto | Cookie CSRF + `X-CSRFToken` |
| Auth | Operational interno | `X-Internal-Token` |
| Agent Core | Operational interno | `X-Internal-Token` + tenant lógico |
| Gateway futuro | Operational ingest | `X-Tenant-Code` + `X-Ingest-Key` |

El navegador nunca debe conocer `schema_name` ni llamar a `/internal/*`. Los guards Angular ayudan a navegar, pero la autorización real debe ocurrir en los backends.

## 4. Flujo de login y selección de tenant

```text
Usuario -> App -> Auth /login/
Auth -> valida contraseña, email, MFA y memberships
Auth -> crea UserSession
Auth -> emite access/refresh con tenant, roles, permisos y suscripción
App -> guarda tokens/tenant en localStorage
App -> interceptor agrega bearer, tenant y correlation ID
```

La revocación existe en `UserSession`, pero la autenticación JWT estándar no consulta esa tabla en cada request. Refresh reuse tiene soporte incompleto.

## 5. Flujo de provisión tenant

```text
App -> Auth: activar suscripción/provisionar
Auth -> Operational /internal/tenants/provision
Operational -> normaliza slug y crea schema único
Operational -> crea tablas, vistas, funciones y triggers
Operational -> guarda TenantRuntime público
Operational -> devuelve tenant code e ingest key una sola vez
Auth -> guarda proyección TenantOperationalRuntime
```

El proceso usa creación aditiva/idempotente. No existe aún un historial completo de migraciones tenant capaz de resolver alteraciones destructivas o rollback.

## 6. Flujo de lectura operacional

```text
App -> Operational con JWT y X-Tenant-ID
Operational -> valida firma, issuer, audience y tenant del claim
Operational -> exige runtime activo y plan pagado
Operational -> resuelve schema_name guardado
Operational -> aplica schema_translate_map
Operational -> consulta solo tablas del tenant
Operational -> devuelve ApiResponse
```

Actualmente estos routers no aplican `require_permission()` de forma granular.

## 7. Flujo de contexto empresarial

```text
App -> Agent Core: lista/descarga plantilla
App -> Agent Core: upload-file
Agent Core -> valida extensión/tamaño y extrae texto
Agent Core -> genera chunks
Agent Core -> Operational interno: guarda documento/chunks
Operational -> schema_translate_map del tenant
App -> Agent Core: status/simulate
Agent Core -> Operational: retrieve lexical
Agent Core -> LLM opcional o fallback
Agent Core -> App: respuesta, confianza y fuentes
```

En modo integrado, editar/eliminar ciertos documentos, formularios, reglas, historiales y trazas puede estar limitado o devolver `501` porque su adaptador Operational no está completo.

## 8. Flujo WhatsApp actual y objetivo

### Actual

```text
                    -> agente OpenAI
                    -> respuesta Meta / alerta ejecutivo / Calendar
```

### Objetivo

```text
Meta -> gateway normalizador
     -> Agent Core para inteligencia
     -> Operational ingest para datos tenant
     -> Meta para respuesta
```

El objetivo es `PROPOSED`; no debe confundirse con el export actual.

## 9. Puertos locales de referencia

| Componente | Puerto host por defecto |
| --- | --- |
| Auth | `8000` |
| Operational | `8001` |
| Agent Core | `8002` |
| Landing | `8080` |
| App | `8081` |
| PostgreSQL | Publicado por la plantilla local |
| Redis | Publicado por la plantilla local |

Los valores exactos y sus overrides pertenecen a [Deploy Configuration](../../flowkron-deploy/docs/CONFIGURATION.md).

