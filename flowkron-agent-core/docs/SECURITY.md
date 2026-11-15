# Security

Agent Core debe operar con JWT RS256 emitido por `flowkron-auth-service` en entornos reales. `X-Tenant-Id` solo se permite en desarrollo local cuando `ALLOW_INSECURE_TENANT_HEADER=true`.

Principios:

- No loguear secretos ni payloads completos con PII.
- Validar tenant entre header/token y payload.
- Mantener respuestas bajo el contrato `ApiResponse`/problem details.
- No ejecutar acciones externas reales desde endpoints demo.
- Devolver handoff humano cuando no exista contexto suficiente.
- Tratar `INTERNAL_TOKEN` como secreto servicio-a-servicio; nunca exponerlo al frontend.
- Validar extension y tamano antes de extraer texto de documentos. Los binarios subidos no se persisten en Agent Core.
