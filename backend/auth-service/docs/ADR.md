# Architecture Decision Records

> Historical record. The former bundled channel workflow was removed in the Flowkron transition. For the current topology, see the repository architecture.

Este documento registra decisiones arquitectonicas relevantes. Cada decision debe actualizarse cuando cambie el contexto o se reemplace una tecnologia.

## ADR-001: Usar django.contrib.auth como identidad base

Estado: aceptada

Contexto:

El servicio requiere usuarios humanos, password hashing, admin, permisos base y ecosistema Django estable.

Decision:

Usar `django.contrib.auth` como fuente base de usuarios y extender con `UserProfile`.

Consecuencias:

- Se reduce riesgo de implementar autenticacion desde cero.
- Se heredan validadores y hashers maduros.
- La identidad de negocio vive fuera de `auth_user`.

## ADR-002: Shared database con aislamiento tenant por aplicacion

Estado: superada (Reemplazada por ADR-008)

Contexto:

Flowkron necesita SaaS multi-tenant con velocidad de desarrollo y operacion simple inicial.

Decision:

Usar base compartida con `tenant_id` en entidades tenantizadas.

Consecuencias:

- Queries deben validar tenant siempre.
- Se requiere disciplina de permisos.
- RLS queda como hardening futuro.
- *Nota: Reemplazada por la decisión de aislar por esquemas físicos en PostgreSQL para la capa operacional (ADR-008).*

## ADR-003: RBAC tenantizado

Estado: aceptada

Contexto:

Los permisos empresariales dependen del tenant y de la membresia del usuario.

Decision:

Modelar `TenantRole`, `Permission`, `RolePermission` y `MembershipRole`.

Consecuencias:

- Un usuario puede tener roles distintos por tenant.
- Los tokens deben emitirse por tenant activo.
- Cambios de rol deben auditarse.

## ADR-004: JWT RS256 con JWKS

Estado: aceptada

Contexto:

Otros microservicios deben validar tokens sin llamar siempre al auth service.

Decision:

Usar RS256 y publicar claves publicas via JWKS.

Consecuencias:

- Consumidores validan firma con clave publica.
- El auth service conserva claves privadas.
- La rotacion exige `kid`.

## ADR-005: Service accounts para machine identity

Estado: aceptada

Contexto:

Microservicios internos no deben autenticarse como usuarios humanos.

Decision:

Crear `iam_service_account` y client credentials flow interno.

Consecuencias:

- Tokens machine-to-machine incluyen `typ=service_account`.
- Scopes reemplazan permisos tenantizados humanos.
- Los secretos deben rotarse periodicamente.

## ADR-006: API keys por tenant para integraciones externas

Estado: aceptada

Contexto:

Integraciones externas necesitan credenciales por empresa cliente.

Decision:

Crear `iam_api_key` con hash, prefix, scopes, expiracion y revocacion.

Consecuencias:

- La key solo se muestra una vez.
- Se puede auditar creacion, revocacion y rotacion.
- Scopes deben ser minimos.

## ADR-007: Entry point automatizado para despliegue

Estado: aceptada

Contexto:

El despliegue debe ejecutar tareas repetibles sin pasos manuales fragiles.

Decision:

Crear `docker-entrypoint.sh` para esperar DB, migrar, seedear, recolectar static files y crear superuser opcional.

Consecuencias:

- Menos pasos manuales.
- Variables controlan comportamiento.
- En orquestadores avanzados puede separarse migracion en job dedicado.

## ADR-008: Base de datos multi-esquema (Schema-per-Tenant) en PostgreSQL

Estado: aceptada

Contexto:

El crecimiento de clientes corporativos (B2B) en Flowkron exige un nivel estricto de aislamiento de datos operacionales (leads, chats, mensajes) para cumplir con normativas de privacidad de datos y evitar riesgos de fugas accidentales (*cross-tenant data leakage*). Además, el volumen de mensajes e integraciones con WhatsApp requiere un núcleo operacional asíncrono y de alta velocidad que no sobrecargue la base de datos de identidad (Django Auth).

Decision:

Adoptar un modelo híbrido multi-esquema:
1. **Django Auth Service** (este servicio): Gestiona de forma lógica la identidad, membresías y suscripciones en una base de datos centralizada (esquema `public`).
2. **FastAPI Core Service** (operacional): Gestiona las tablas de negocio operacionales dentro de un esquema de PostgreSQL dedicado por cada tenant (`tenant_<tenant_slug>`).
3. El aprovisionamiento físico del esquema se dispara mediante una llamada interna segura de Django a FastAPI.
4. FastAPI resuelve dinámicamente el esquema destino mediante el `tenant_id`/`tenant_slug` extraído del JWT (firmado con RS256 por Django) o mediante las cabeceras de ingesta validadas (`X-Tenant-Code` y `X-Ingest-Key`) para el adaptador de canal.

Consecuencias:

- Garantía estricta de aislamiento de datos a nivel de motor de base de datos.
- Desacoplamiento total entre la lógica de negocio en tiempo real (FastAPI) y la autenticación/suscripción (Django).
- Mayor complejidad en la gestión de migraciones de base de datos, requiriendo un comando orquestador de Alembic (`migrate_all_tenants`) para aplicar cambios secuencialmente a cada esquema activo.
- Obligatoriedad de PgBouncer en producción para evitar el agotamiento de pools de conexión de PostgreSQL debido al volumen de esquemas.
