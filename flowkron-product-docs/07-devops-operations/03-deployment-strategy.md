# Estrategia de despliegue

Versión: 1.1
Tipo: estado actual + objetivo
Estado: `NOT_IMPLEMENTED` para despliegue productivo
Última verificación: 2026-07-23

## Estado actual

El stack puede construirse y ejecutarse manualmente con Docker Compose. Algunos servicios incluyen configuración Railway y existe una guía de preparación, pero no hay pipeline, promoción entre ambientes, registro de imágenes, despliegue remoto verificable ni rollback automático.


## Flujo objetivo mínimo

1. Validar contratos, formato, tests y builds.
2. Ejecutar controles de seguridad.
3. Construir imágenes inmutables por commit.
4. Publicar en registro autorizado.
5. Aplicar migraciones controladas.
6. Desplegar a staging.
7. Ejecutar smoke/E2E y pruebas tenant.
8. Requerir aprobación productiva.
9. Verificar salud, métricas y logs.
10. Permitir rollback del artefacto y de la migración.

Rolling, blue/green o canary se decidirá al seleccionar infraestructura.

## Gate productivo

No desplegar a producción sin secretos gestionados, TLS, backups/restore, migraciones versionadas, observabilidad, runbooks, tests cross-tenant y aprobación legal/operativa.
