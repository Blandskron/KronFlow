# ADR-002 — Auth Service separado

Estado: Aceptado e implementado
Fecha de verificación: 2026-06-22

## Decisión

Centralizar identidad humana/máquina, tenants, memberships, RBAC, sesiones, suscripción y auditoría IAM en `flowkron-auth-service`; mantener datos y operaciones tenant en `flowkron-operational-service`.

## Contrato entre servicios

Auth llama Operational de forma síncrona con `X-Internal-Token` para provisioning, runtime, activación/suspensión, rotación ingest y migración. Auth conserva una proyección `TenantOperationalRuntime`.

## Consecuencias

- Permite IAM central y separación del dominio operacional.
- Introduce dependencia distribuida, secretos compartidos, sincronización y fallos parciales.
- Provisioning puede devolver 502 y dejar estado `provision_failed`.
- La autorización granular no se hereda automáticamente: Operational debe aplicarla explícitamente.

## Regla

Auth decide identidad/permisos/entitlements; Operational debe volver a validar token, tenant, runtime, plan y permisos requeridos.
