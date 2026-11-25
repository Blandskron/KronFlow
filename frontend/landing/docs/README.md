# Documentación de flowkron-front-landing-angular

Documentación mantenida contra el código y configuración actuales.

| Documento | Contenido |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Estructura, rutas, estado y comportamiento |
| [CONFIGURATION.md](CONFIGURATION.md) | Build args, Angular, Docker y Nginx |
| [SECURITY_AND_CONTENT.md](SECURITY_AND_CONTENT.md) | Límites de contenido, privacidad, seguridad y accesibilidad |
| [OPERATIONS.md](OPERATIONS.md) | Desarrollo, despliegue y diagnóstico |
| [TESTING.md](TESTING.md) | Cobertura real y estrategia pendiente |

Las instrucciones agenticas se consolidan en [../AGENTS.md](../AGENTS.md). No se mantiene una segunda copia bajo `docs/agent/`.

## Regla de mantenimiento

- Cambio de CTA/configuración: actualizar `CONFIGURATION.md` y smoke.
- Cambio de formulario/legal/analytics: actualizar `SECURITY_AND_CONTENT.md`.
- Cambio de rutas/componentes: actualizar `ARCHITECTURE.md`.
- Cambio de build/Docker/Nginx: actualizar `OPERATIONS.md`.
- Documentar el formulario como integracion HTTP real contra IAM; no llamar regresion visual a simples screenshots.
