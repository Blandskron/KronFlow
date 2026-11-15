# Overview para desarrolladores

## 1. Sistema


```text
Landing -> Auth
App -> Auth + Operational + Agent Core
Auth -> Operational
Agent Core -> Operational
Auth -> PostgreSQL + Redis
Operational -> PostgreSQL public + schema tenant
```

## 2. Repositorios

| Repositorio | Tecnología | Responsabilidad |
| --- | --- | --- |
| `flowkron-auth-service` | Django/DRF | Usuarios, JWT, tenants, RBAC, sesiones, MFA, credenciales y audit |
| `flowkron-operational-service` | FastAPI/SQLAlchemy | Runtime tenant, schema físico, datos operacionales, analytics e ingest |
| `flowkron-agent-core` | FastAPI/SQLAlchemy | Contexto empresarial, documentos, retrieval y runtime conversacional |
| `flowkron-front-app-angular` | Angular 21 | UI privada |
| `flowkron-front-landing-angular` | Angular 21 | UI pública y contacto |
| `flowkron-api-contracts` | OpenAPI/JSON Schema | Contratos compartidos |
| `flowkron-deploy` | Docker Compose | Integración local |

## 3. Estado técnico

| Capacidad | Estado |
| --- | --- |
| IAM, tenants y RBAC en Auth | `IMPLEMENTED` |
| Runtime/schema por tenant | `IMPLEMENTED` con migraciones parciales |
| Leads, conversaciones y analytics | `PARTIAL` |
| Agent Core/contexto | `PARTIAL` |
| UI privada | `PARTIAL` |
| Workflow WhatsApp | `PARTIAL`, modo SQL legacy |
| Contratos compartidos | `PARTIAL` |
| Docker local | `IMPLEMENTED` |
| CI/CD, observabilidad, backup/restore y producción | `NOT_IMPLEMENTED` |

## 4. Decisiones que no deben romperse

- Auth es owner de identidad; Operational es owner del schema tenant.
- Ningún frontend envía `schema_name`.
- Operational resuelve tenant y usa `schema_translate_map`.
- Agent Core no provisiona schemas ni accede a PostgreSQL en modo integrado.
- `X-Internal-Token` protege interfaces internas.
- JWT productivo debe ser RS256 emitido por Auth.

## 5. Limitaciones importantes

- Operational no aplica RBAC granular por endpoint.
- `/api/v1/agents` de Operational es stub.
- Conversaciones del dashboard son de solo lectura.
- Workflows UI es una vista derivada, no motor.
- Integraciones/notificaciones UI son placeholders.
- Agent Core integrado no soporta completamente todas las rutas stateful.
- No hay migraciones tenant completas ni rollback.
- No hay E2E integrado de todos los servicios.

## 6. Dónde empezar

1. Lea `AGENTS.md` y `docs/README.md` del repositorio que modificará.
2. Revise el contrato en `flowkron-api-contracts`.
4. Ejecute validaciones proporcionales.
5. Actualice documentación propietaria y transversal.

## 7. Prioridad técnica recomendada

1. Tests cross-tenant y autorización Operational.
2. Migraciones tenant versionadas.
3. Staging, CI/CD, secrets y TLS.
4. Backups/restore y observabilidad.
6. E2E integrado y cierre de stubs.
