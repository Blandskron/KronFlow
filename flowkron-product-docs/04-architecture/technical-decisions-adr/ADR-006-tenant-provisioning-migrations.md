# ADR-006 - Provisioning y migraciones tenant
> Historical record. The former bundled channel workflow was removed in the Flowkron transition. For the current topology, see the repository architecture.

Estado: Propuesto (`PROPOSED`)
Horizonte: fase posterior de validacion
> Current topology: external channel adapters use the HTTP ingestion API. Operational owns tenant schema selection and business data writes.

## Contexto

Operational crea schemas/tablas con `create_all` y registra una version logica. Esto permite el version de validacion, pero no cubre alteraciones, cambios destructivos, rollback real, control de drift ni migraciones por rubro.

El estado actual separa responsabilidades asi:

- `flowkron-auth-service` administra IAM, usuarios, tenants, RBAC, sesiones, auditoria y contacto publico mediante migraciones Django.
- `flowkron-operational-service` administra `tenant_runtime`, `migration_registry`, `system_events` y schemas `tenant_*`.
- el adaptador de canal consume Operational por HTTP y no debe escribir directo a PostgreSQL para datos de negocio.

La brecha principal es que los schemas tenant de Operational no tienen revisiones versionadas con upgrade/downgrade. `create_all` crea objetos faltantes, pero no migra columnas existentes ni ofrece rollback profesional.

## Decision propuesta

Separar provisioning inicial de migraciones versionadas. fase posterior de validacion, crear una capacidad dedicada de gobierno DB, potencialmente en un repositorio `flowkron-db-schemas`.

Ese repositorio no debe significar que todos los servicios consumen libremente la DB. Su objetivo seria concentrar migraciones, validaciones, plantillas tenant, rollback y operaciones controladas, manteniendo que cada microservicio sea propietario de sus datos y reglas de negocio.

## Alcance fase posterior de validacion

`flowkron-db-schemas` deberia cubrir:

- Migraciones versionadas de schemas tenant.
- Migraciones versionadas de tablas publicas de Operational.
- Plantillas por modulo/rubro para tenants futuros.
- Scripts de provisioning, migracion por tenant, migracion masiva y rollback.
- Validacion de drift entre metadata esperada y DB real.
- Backups pre-migracion y restore probado antes de cambios destructivos.
- Seeds validacion no productivos.
- Evidencia operativa en `migration_registry` y `system_events`.

Las migraciones Django de Auth pueden permanecer en `flowkron-auth-service` durante el version de validacion y primera etapa fase posterior de validacion, porque Django acopla modelos, apps y migraciones. Una centralizacion posterior debe evaluarse solo si reduce riesgo operativo y no rompe el flujo natural de Django.

## Modelo de propiedad de datos

La separacion recomendada es por ownership, no por acceso directo compartido:

```text
Auth Service        -> IAM, usuarios, tenants, RBAC, sesiones, auditoria.
Operational Service -> runtime operacional, schemas tenant, datos de negocio.
el adaptador de canal                 -> consumidor de APIs Operational, nunca escritor directo de DB.
Frontends           -> consumidores de APIs, nunca acceso DB.
```

La DB puede tener gobierno y migraciones centralizadas, pero las reglas de negocio deben seguir viviendo en el servicio propietario.

## Naming objetivo

Evitar nombres ambiguos como `flowkron_auth_db` si se habla de schema y no de database. Una convencion objetivo mas clara seria:

```text
Database: flowkron_platform
Schema IAM: iam
Schema Operational/public runtime: operational
Schemas tenant: tenant_<slug>
```

El cambio de nombres no es parte del version de validacion. Si se adopta despues, requiere plan de migracion, compatibilidad, backups y actualizacion de settings.

## Rubros y plantillas tenant

Para futuros rubros, FastAPI no deberia crear tablas ad hoc segun condiciones dispersas. Operational deberia provisionar tenants aplicando manifiestos versionados:

```text
tenant_core@1
automotive@1
real_estate@1
healthcare@1
legal@1
```

Ejemplo objetivo:

```text
tenant_slug = blandskron_automotora
industry = automotive
modules = [tenant_core, automotive_crm, whatsapp_agent]
```

El provisioning deberia:

1. Crear el schema tenant.
2. Aplicar migraciones core.
3. Aplicar migraciones del rubro/modulos.
4. Registrar versiones aplicadas.
5. Guardar template/modulos en runtime.
6. Entregar `tenant_code` e `ingest_key`.
7. Registrar eventos y resultado de migracion.

Los flujos del adaptador de canal pueden variar por rubro, pero deben seguir consumiendo contratos HTTP de Operational. Operational decide el modelo persistente aplicable segun tenant, rubro y modulo.

## Estructura candidata

```text
flowkron-db-schemas/
  README.md
  docs/
    architecture.md
    migration-policy.md
    rollback-policy.md
    tenant-provisioning.md
    industry-modules.md
  migrations/
    operational/
      versions/
    tenant_core/
      versions/
    industries/
      automotive/
        versions/
      real_estate/
        versions/
  manifests/
    tenant_core.yml
    automotive.yml
    real_estate.yml
  scripts/
    provision_tenant.py
    migrate_tenant.py
    migrate_all_tenants.py
    rollback_tenant.py
    validate_schema.py
    detect_drift.py
    backup_schema.py
    restore_schema.py
  seeds/
    validacion/
  tests/
    test_migrations_forward.py
    test_migrations_rollback.py
    test_cross_tenant_isolation.py
```

## No objetivos

- No mover inmediatamente migraciones Django fuera de Auth.
- No permitir que el adaptador de canal escriba directo en schemas tenant.
- No permitir que frontends o integraciones consuman tablas directamente.
- No introducir rubros antes de definir contratos, datos minimos y ownership.
- No tratar `create_all` como mecanismo suficiente para cambios no aditivos.

## Criterios

- Idempotencia y aislamiento.
- Prueba sobre multiples versiones/schemas.
- Observabilidad por tenant.
- Rollback o estrategia forward-fix documentada.
- Privilegios DB minimos compatibles.
- Separacion clara entre migracion DB y reglas de negocio.
- Contratos HTTP estables para consumidores como Angular y los adaptadores de canal.
- Ejecucion segura por lotes con locks y reintentos.
- Evidencia de backup/restore antes de cambios destructivos.
