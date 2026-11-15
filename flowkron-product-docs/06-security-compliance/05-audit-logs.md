# Auditoría técnica

**Versión:** 1.0
**Tipo:** Implementación parcial
**Última verificación:** 2026-06-22

## Evidencia actual

- IAM registra eventos relevantes de identidad y sincronización/aprovisionamiento.
- El servicio operacional mantiene `system_events` dentro del esquema del tenant.
- Los servicios emiten logs de aplicación al flujo estándar del contenedor.

## Cobertura faltante

- No existe almacén central e inmutable de auditoría.
- No hay correlación extremo a extremo estandarizada entre frontend, IAM y operacional.
- No existe auditoría de agentes, prompts, herramientas, modelos o billing porque esos runtimes no están implementados.
- No se evidencian alertas, exportación a SIEM, política automatizada de retención ni revisión periódica.

## Requisitos para completar

Definir un esquema común con actor, tenant, acción, recurso, resultado, fecha, origen y correlation ID; separar auditoría de logs diagnósticos; proteger integridad y acceso; y probar búsqueda, exportación y retención.
