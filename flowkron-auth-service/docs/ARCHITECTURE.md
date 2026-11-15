# Arquitectura

## Responsabilidad

`flowkron-auth-service` es el IAM central de Flowkron. Gestiona identidad humana y de máquina, tenants, membresías, RBAC/entitlements, sesiones, material criptográfico y auditoría. No administra CRM, agentes, WhatsApp, RAG ni datos operacionales.

## Componentes

```text
Cliente / servicio
        |
        v
Django REST Framework
  accounts  -> login, perfil, tokens humanos
  tenants   -> tenants, membresías, invitaciones, suscripción y runtime
  rbac      -> roles, permisos y asignaciones
  sessions  -> sesiones, revocación y señales de riesgo
  security  -> MFA, JWKS, signing keys, service accounts y API keys
  audit     -> audit trail sincrónico
  shared    -> permisos, errores, uploads, logs y correlación
```

`django.contrib.auth.User` es la identidad raíz; `UserProfile` la extiende. La base IAM es compartida y las entidades tenantizadas se filtran por membership/tenant en aplicación.

## Login humano y onboarding

1. Valida email/password mediante Django y django-axes.
2. Exige usuario activo y correo verificado.
3. Si el perfil tiene MFA, valida TOTP.
4. Si el usuario tiene membership activa, crea `UserSession` tenantizada y emite access/refresh Simple JWT con tenant, membership, sesión, roles, permisos efectivos, suscripción y `amr`.
5. Si el usuario no tiene tenant activo, crea una sesión limitada con `onboarding_required=true`, sin `tenant_id`, roles ni permisos.
6. El frontend debe llamar `/api/v1/tenants/onboarding/` para crear la empresa inicial. El servicio crea `Tenant`, `TenantMembership`, roles base, asigna `TENANT_OWNER`, marca `onboarding_completed_at` y devuelve nuevos tokens con tenant.
7. Escribe `AuditLog` sincrónicamente.

Los permisos efectivos son la intersección de los permisos RBAC con los entitlements habilitados por el plan/suscripción.

No existe registro público abierto. La cuenta nace por administración interna o por una invitación válida de tenant. La confirmación de email puede definir la password inicial mediante `new_password`; una invitación válida también puede activar una cuenta nueva cerrada al email invitado.

## Machine-to-machine

Una `ServiceAccount` activa intercambia `client_id`/`client_secret` por un JWT RS256. Los scopes solicitados deben ser subconjunto de los asignados. Introspection exige otro bearer de service account con `auth.verify_token`.

## Dos familias de firma

- JWT humanos: Simple JWT firma con `JWT_PRIVATE_KEY(_PATH)` y valida con `JWT_PUBLIC_KEY(_PATH)`.
- JWT de service account: usan la clave activa de `iam_signing_key`, cifrada en DB, y llevan `kid`.

JWKS publica signing keys de base de datos vigentes; no incorpora automáticamente la clave pública configurada para Simple JWT. La rotación del endpoint administrativo aplica a la segunda familia.

## Integración operacional

Los datos de negocio schema-per-tenant viven en `flowkron-operational-service`. Auth conserva una proyección `TenantOperationalRuntime` y llama endpoints internos con `X-Internal-Token` para:

- aprovisionar runtime al activar una suscripción o mediante acción explícita;
- consultar la proyección guardada;
- rotar la ingest key.

La creación inicial del tenant Free no aprovisiona automáticamente el schema. Las llamadas son síncronas, tienen timeout de 15 segundos y pueden producir 502. Si la provisión falla, el runtime queda `provision_failed` con `last_error`.

## Sesiones y revocación

`UserSession` soporta revocación y estado comprometido. Logout y cambios de password actualizan esta tabla. La autenticación JWT estándar no consulta la sesión en cada request; introspection y `/sessions/status/` sí consideran su estado. Aunque existe una función para marcar refresh reuse, el endpoint de refresh actual no la llama.

## Auditoría y observabilidad

Eventos sensibles se insertan en `iam_audit_log` desde el request actual. `CorrelationIdMiddleware` establece `X-Request-ID` y `X-Correlation-ID`; logs se emiten como JSON. No hay cola asíncrona de auditoría ni garantía de inmutabilidad a nivel DB en este repositorio.

## Extensión

Mantén serializers para validación/contratos, views para coordinación, services para reglas reutilizables, permisos en `apps/shared/permissions.py`, auditoría de acciones sensibles y tests por comportamiento. La implementación histórica contiene lógica en views/serializers; no asumas una capa `selectors.py` existente.
