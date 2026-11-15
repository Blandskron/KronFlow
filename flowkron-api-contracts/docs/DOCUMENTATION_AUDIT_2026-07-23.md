# Auditoría documental — 2026-07-23

> Historical record. The former bundled channel workflow was removed in the Flowkron transition. For the current topology, see the repository architecture.

Se revisaron las especificaciones OpenAPI, JSON Schemas, scripts de validación y reglas de versionado.

## Hechos confirmados

- Auth v0.5.0, Operational v0.3.1 y Agent Core v0.3.1 tienen especificaciones OpenAPI versionadas.
- El documento WhatsApp Gateway v0.2.0 existe, pero no publica `paths` operativos.
- Los schemas compartidos cubren respuestas, errores, IA, eventos, jobs y webhooks.
- Los validadores locales comprueban estructura JSON/YAML y documentación agent-first; no sustituyen validación semántica completa de OpenAPI.
- El flujo de canal anterior actual conserva un modo PostgreSQL legacy, por lo que no puede declararse consumidor de ingest Operational hasta que su export cambie.

Todo cambio incompatible debe seguir `VERSIONING.md`, documentar consumidores y anotarse en `CHANGELOG.md`.
