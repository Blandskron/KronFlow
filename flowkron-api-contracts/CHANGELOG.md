# Changelog

Formato basado en Keep a Changelog y SemVer.

## [Unreleased]

### Added
- Operational `v0.4.0` (FK-01): campos opcionales de identidad de conexión/proveedor, tipo y estado reportado en ingestión; metadatos persistidos y `recorded_at` en lectura de mensajes. Se mantienen requests anteriores y campos de respuesta existentes. `connection_id` solo admite `default`; no se habilitan varias cuentas, multimedia ni recibos de lectura.
- Deduplicación concurrente dentro de la empresa autenticada. Repeticiones nuevas devuelven el ID original; marcadores históricos sin vínculo fiable conservan `message_id: null`. Reutilizar identidad nueva para otro hilo o dirección responde 409. `external_message_id` de lectura ahora refleja la entrada guardada; el fallback interno se conserva para historial no reconstruible. El CRM consume el `id` interno y no requiere cambios.

### Changed
- `operational-service.openapi.yml` sube a `v0.3.1`; documenta auto-versionado de documentos de contexto, acciones deshabilitadas en `context/status` y retrieval lexical sobre chunks activos.
- `agent-core.openapi.yml` sube a `v0.3.1`; alinea schemas reales de setup, reglas y documentos, agrega endpoints faltantes de templates/forms y marca rutas stateful/local-only con respuesta 501 cuando la persistencia se delega a Operational.

### Planned
- Profundizar ejemplos por dominio y catalogos de error.
- Bundle unificado con referencias resueltas para tooling.
- Generacion de SDK TypeScript cuando exista aprobacion de consumo.

---

## [0.5.0] - 2026-07-07

### Changed
- `auth-service.openapi.yml` sube a `v0.5.0`.
- La API de Auth queda alineada con login manual, recuperacion de password, refresh, logout, perfil, MFA, JWKS, machine credentials, tenants, RBAC, sesiones, seguridad, contacto y auditoria.
- Se retiran del contrato los flujos de creacion publica de cuenta y proveedores externos de identidad.
- Las invitaciones quedan descritas como flujo para usuarios existentes gestionados manualmente.

### Version Updates
- `operational-service.openapi.yml`: `v0.3.0`.
- `agent-core.openapi.yml`: `v0.3.0`.
- `whatsapp-gateway.openapi.yml`: `v0.2.0`.
- `flowkron-public-api.openapi.yml`: `v0.2.0`.

---

## [0.3.0] - 2026-07-05

### Added
- Cobertura amplia de Auth, Tenants, RBAC, Sessions, Audit y Security.
- Spec completo de Operational Service con ingest WhatsApp, dashboard, datos operacionales, contexto interno y migraciones.

---

## [0.2.0] - 2026-07-04

### Added
- Spec de Agent Core para contexto de negocio, documentos, formularios, reglas, simulacion y trazas.

---

## [0.1.0] - 2026-06-23

### Added
- Fundacion inicial del repositorio `flowkron-api-contracts`.
- Contratos base de respuesta, error, paginacion, jobs, IA, eventos, webhooks y auditoria.
- OpenAPI inicial para contacto publico.
- Documentacion agent-first, ADRs, skills y scripts de validacion.
