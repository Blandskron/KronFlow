# ADR-001 — PostgreSQL multi-schema

Estado: Aceptado e implementado parcialmente
Fecha de verificación: 2026-06-22

## Contexto

Los datos operacionales de múltiples tenants requieren aislamiento, mientras IAM permanece compartido.

## Decisión

Usar PostgreSQL con tablas IAM/runtime públicas y un schema operacional por tenant. Operational resuelve el schema desde `tenant_runtime` y usa SQLAlchemy `schema_translate_map`.

## Evidencia

- Auth persiste tenants/memberships y proyección de runtime.
- Operational provisiona schemas sanitizados y modelos con schema lógico `tenant`.
- JWT/ingest resuelven runtime activo y plan antes de consultar.

## Consecuencias

Positivas: aislamiento lógico fuerte, nombres y lifecycle explícitos.
Negativas: provisioning DDL privilegiado, migraciones N schemas, backups/restores complejos y alto impacto de un error de resolución.

## Limitaciones actuales

Provisioning usa `create_all` y no revisiones tenant versionadas; no modifica columnas existentes. Falta suite cross-tenant y restore individual probado. Todo cambio no aditivo requiere migración/rollback explícitos.
