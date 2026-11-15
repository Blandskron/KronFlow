# flowkron-api-contracts

Repositorio central de contratos HTTP para todos los servicios de la plataforma Flowkron.
Este repositorio es la fuente de verdad para interfaces, schemas, errores y eventos compartidos.

> **Principio**: El contexto también es arquitectura. Los microservicios no comparten dominio interno — comparten contratos versionados.

## Servicios cubiertos

| Servicio | Tecnología | Spec | Estado |
| --- | --- | --- | --- |
| `flowkron-auth-service` | Django / DRF + RS256 JWT | `openapi/services/auth-service.openapi.yml` | v0.5.0 |
| `flowkron-operational-service` | FastAPI + SQLAlchemy + PostgreSQL multi-schema | `openapi/services/operational-service.openapi.yml` | v0.3.1 |
| `flowkron-agent-core` | FastAPI + Azure OpenAI opcional + RAG lexical/Operational | `openapi/services/agent-core.openapi.yml` | v0.3.1 |
| External WhatsApp adapter (reserved interface) | Channel integration | `openapi/services/whatsapp-gateway.openapi.yml` | v0.2.0 |

## Estructura

```
flowkron-api-contracts/
├── openapi/
│   ├── services/          # Especificaciones OpenAPI 3.1 por servicio
│   ├── common/            # Componentes compartidos: schemas, params, responses, securitySchemes
│   └── bundles/           # Bundles resueltos para tooling (pendiente generar)
├── schemas/               # JSON Schemas reutilizables (AI, events, audit, jobs, response)
├── errors/                # Catálogos de error por dominio (auth, operational, ai, tenant, platform, whatsapp)
├── examples/              # Payloads válidos de request/response
├── docs/                  # Arquitectura, ADRs, runbooks y seguridad
├── scripts/               # Validaciones locales (Python)
└── skills/                # Agent skills (auto-discovery)
```

## Uso rápido

### Validación local (Python — sin dependencias externas)
```powershell
python scripts/validate-json-schemas.py
python scripts/validate-yaml-structure.py
python scripts/validate-agent-docs.py
```

### Lint OpenAPI con Spectral
```bash
npx @stoplight/spectral-cli lint openapi/services/auth-service.openapi.yml
npx @stoplight/spectral-cli lint openapi/services/operational-service.openapi.yml
npx @stoplight/spectral-cli lint openapi/services/agent-core.openapi.yml
```

### Preview de documentación interactiva
```bash
npx @redocly/cli preview-docs openapi/services/auth-service.openapi.yml
npx @redocly/cli preview-docs openapi/services/operational-service.openapi.yml
npx @redocly/cli preview-docs openapi/services/agent-core.openapi.yml
```

### Bundle (resolver $ref externos)
```bash
npx @redocly/cli bundle openapi/services/auth-service.openapi.yml -o openapi/bundles/auth-service.bundle.yml
```

## Mecanismos de autenticación

| Contexto | Header | Emisor |
| --- | --- | --- |
| Dashboard Angular → auth-service / operational / agent-core | `Authorization: Bearer <JWT RS256>` | auth-service |
| External adapter → Ingest endpoints | `X-Tenant-Code` + `X-Ingest-Key` | operational-service (rotable) |
| auth-service → operational-service (internal) | `X-Internal-Token` | variables de entorno compartidas |
| Endpoints JWKS / Contact / Reset / Invitation preview | Sin autenticación | — |

## Reglas duras

- **No agregar** modelos ORM, queries SQL, routers productivos ni lógica de negocio.
- **No agregar** secretos, tokens, llaves privadas ni `.env` con valores reales.
- **Todo cambio breaking** debe registrarse en `CHANGELOG.md` con análisis de impacto.
- **Los prefijos reales** de rutas son `/api/v1/` en todos los servicios.
- **El campo `schema_name`** nunca se acepta en contratos públicos — lo resuelve operational-service internamente.
- `CLAUDE.md` y `GEMINI.md` remiten a `AGENTS.md` sin duplicar reglas.

## Versionado

Ver [VERSIONING.md](./VERSIONING.md) y [CHANGELOG.md](./CHANGELOG.md).

## Reglas de contrato

Ver [CONTRACT.md](./CONTRACT.md).
