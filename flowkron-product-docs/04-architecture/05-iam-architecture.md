# Arquitectura IAM

Versión: 1.0
Tipo: Current State
Estado: `PARTIAL`

## Funciones implementadas

- Email/password, verificación y reset.
- Google Identity Services.
- MFA TOTP y recovery codes.
- Tenants, memberships, invitaciones y RBAC.
- Sesiones/risk flags.
- API keys, service accounts e introspection.
- Auditoría IAM síncrona.

## Roles base

`TENANT_OWNER`, `TENANT_ADMIN`, `MANAGER`, `VENDEDOR`, `AGENT_SUPERVISOR`, `AGENT_OPERATOR`, `VIEWER`.

La autorización debe basarse en permisos efectivos, no solo en rol.

## JWT humanos

Simple JWT RS256 añade `tenant_id`, `membership_id`, `session_id`, roles, permisos, suscripción y `amr`. Access dura 10 minutos y refresh 14 días según configuración canónica actual.

Logout/password actualizan sesión, pero la autenticación JWT estándar no consulta `UserSession` en cada request. Existe soporte interno para refresh reuse, aún no conectado al endpoint HTTP.

## JWT de servicio

Service accounts obtienen tokens RS256 con scopes y `kid`, firmados por `iam_signing_key`. Introspection requiere otro service token con `auth.verify_token`.

## Advertencia JWKS

`/api/v1/auth/jwks/` publica signing keys administradas en DB; no publica automáticamente la clave pública configurada para Simple JWT humano. Los consumidores deben configurar la familia correcta.

## Frontera

Auth centraliza IAM. Operational todavía valida JWT/runtime/plan, pero no permisos granulares en sus routers. El frontend guarda tokens humanos en `localStorage`, lo que eleva el impacto de XSS.
