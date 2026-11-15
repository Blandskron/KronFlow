# Auditoría documental — 2026-07-23

Se contrastaron rutas Django, configuración pública, modelos, OpenAPI compartido y documentos canónicos.

## Hechos confirmados

- Auth concentra identidad, JWT RS256, tenants, membresías, RBAC, sesiones, MFA, credenciales de servicio y contacto público.
- El contrato compartido es `flowkron-api-contracts/openapi/services/auth-service.openapi.yml` v0.5.0.
- API keys se gestionan en este servicio, pero no existe autenticación DRF `ApiKey` para consumirlas.
- La activación de suscripción llama a Operational de forma síncrona; su fallo puede devolverse como `502`.
- Los health endpoints no validan DB, Redis, migraciones ni claves de firma.

## Fuentes que deben prevalecer

`docs/API.md`, `DATA_MODEL.md`, `SECURITY.md`, `DEPLOYMENT.md` y `OPERATIONS.md`; para payloads, OpenAPI y el código propietario. No se revisaron archivos `.env` ni secretos.
