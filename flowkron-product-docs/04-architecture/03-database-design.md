# Diseño de base de datos

Versión: 1.0
Tipo: Current State
Estado: `PARTIAL`
Fuentes: Auth/Operational `docs/DATA_MODEL.md`

## Modelo general

El Compose local usa una database PostgreSQL `flowkron_auth`. Auth administra tablas IAM compartidas; Operational administra tablas públicas de runtime y un schema por tenant.

## IAM compartido

Grupos principales:

- Identidad: `auth_user`, `iam_user_profile`.
- Tenant: `iam_tenant`, `iam_tenant_membership`, `iam_tenant_invitation`, `iam_tenant_operational_runtime`.
- RBAC: `iam_permission`, `iam_tenant_role`, `iam_role_permission`, `iam_membership_role`.
- Sesión/seguridad: `iam_user_session`, `iam_signing_key`, `iam_service_account`, `iam_api_key`, MFA y tokens de un solo uso.
- Auditoría: `iam_audit_log`.

La lista exacta de campos/constraints pertenece a `flowkron-auth-service/docs/DATA_MODEL.md` y sus migraciones Django.

## Operational público

| Tabla | Propósito |
| --- | --- |
| `tenant_runtime` | Tenant IAM → schema, code, ingest hash, plan y estado |
| `migration_registry` | Versión lógica/resultado por schema |
| `system_events` | Eventos operacionales/provisioning |
| `billing_reference` | Referencia no usada por routers actuales |

## Schema tenant activo

- `mensajes_procesados`
- `clientes`
- `ejecutivos`
- `leads`
- `inventario_vehiculos`
- `solicitudes_derechos`
- `log_limpiezas`
- `conversaciones`
- `mensajes_dashboard`

Los modelos alternativos en inglés (`agent_profile`, `analytics_snapshot`, etc.) son legacy no importado y no constituyen tablas/contratos activos.

## Aislamiento

Operational usa modelos con schema lógico `tenant` y `schema_translate_map` por runtime. No usa `SET search_path` por request ni confía en un schema enviado libremente por el cliente.

## Migraciones

- Auth usa migraciones Django.
- Operational crea tablas públicas al startup con `create_all`.
- Provisioning/migración tenant reaplica `create_all`, vistas y triggers.
- No hay revisiones Alembic tenant versionadas; `create_all` no altera columnas/constraints existentes.

Cualquier cambio no aditivo necesita migración explícita, prueba multi-schema, backup/restore y rollback.
