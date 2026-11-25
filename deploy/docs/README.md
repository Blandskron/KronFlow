# Documentación de flowkron-deploy

Documentación contrastada con los modelos Compose y los contratos básicos de los repositorios hermanos.

| Documento | Contenido |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Servicios, red, dependencias y persistencia |
| [CONFIGURATION.md](CONFIGURATION.md) | Variables requeridas, defaults y puertos |
| [OPERATIONS.md](OPERATIONS.md) | Inicio, diagnóstico, parada y recuperación |
| [SECURITY.md](SECURITY.md) | Secretos, datos, JWT y brechas productivas |
| [VALIDATION.md](VALIDATION.md) | Validación estática y smoke autorizado |

Las instrucciones agenticas se consolidan en [../AGENTS.md](../AGENTS.md). No se mantiene documentación duplicada bajo `docs/agent/`.

## Mantenimiento

- Servicio/dependencia/red/volumen: actualizar `ARCHITECTURE.md`.
- Variable/puerto/build arg: actualizar `CONFIGURATION.md` y `.env.example` en la misma tarea.
- Procedimiento/startup/healthcheck: actualizar `OPERATIONS.md` y `VALIDATION.md`.
- Secretos/exposición/bootstrap/datos: actualizar `SECURITY.md`.
