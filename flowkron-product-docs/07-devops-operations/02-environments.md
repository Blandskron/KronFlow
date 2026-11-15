# Ambientes

Versión: 1.2
Tipo: estado actual
Última verificación: 2026-07-23

| Ambiente | Estado | Evidencia |
| --- | --- | --- |
| Local | `IMPLEMENTED` | Docker Compose base para infraestructura, backend y frontend |
| Desarrollo compartido | `NOT_IMPLEMENTED` | Sin infraestructura versionada verificable |
| QA/Staging | `NOT_IMPLEMENTED` | Sin ambiente o promoción automatizada |
| Producción | `NOT_IMPLEMENTED` | Sin configuración productiva verificable |

Los archivos Railway presentes en algunos servicios expresan intención de despliegue, no evidencia de un ambiente activo o aprobado.

## Configuración

La fuente local permitida es `.env.example`. Los secretos viven fuera de Git. Las URLs Angular se compilan en el bundle y deben ser accesibles desde el navegador; no pueden usar DNS interno de Compose.

## Gate para crear un ambiente

Un nuevo ambiente debe definir ownership, dominio/TLS, secretos, base de datos, migraciones, observabilidad, backups, controles de acceso, smoke, rollback y costos.
