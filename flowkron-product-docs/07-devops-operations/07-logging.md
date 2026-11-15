# Logging

**Versión:** 1.0
**Tipo:** Implementación parcial
**Última verificación:** 2026-06-22

## Estado actual

| Capa | Evidencia |
|---|---|
| IAM | logs Django y eventos de identidad/aprovisionamiento |
| Operacional | logs FastAPI y tabla tenant `system_events` |
| Frontends | consola/navegador y access/error logs de Nginx |
| Docker | salida estándar consultable con `docker compose logs` |

## Brechas

No existe agregación central, formato común, correlation ID extremo a extremo, retención automatizada, búsqueda transversal, alertas sobre logs ni protección inmutable de auditoría.

## Convenciones objetivo

Los servicios deben emitir logs estructurados con timestamp, nivel, servicio, ambiente, correlation ID y tenant/actor cuando sea seguro. Nunca deben registrar contraseñas, secretos, tokens completos, claves, códigos MFA ni payloads personales innecesarios.
