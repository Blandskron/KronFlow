# Auditoría documental — 2026-07-23

Se contrastaron rutas Angular, servicios HTTP, interceptor, environment y documentación existente.

## Hechos confirmados

- La SPA consume Auth, Operational y Agent Core mediante `HttpClient`; el interceptor agrega correlación y adjunta bearer/tenant a bases configuradas.
- Conversaciones son de solo lectura; workflows transforman datos existentes y no tienen CRUD propio.
- Integraciones y notificaciones son placeholders. Pricing abre WhatsApp y no activa suscripción.
- Contexto Empresarial integra plantillas, documentos, setup y simulación mediante Agent Core.
- No existe target o runner de pruebas unitarias Angular; `npm test` no es evidencia de una suite válida.

Los cambios de rutas o DTOs deben actualizar `ROUTES_AND_APIS.md` y el contrato compartido correspondiente.
