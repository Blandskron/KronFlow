# ADR-005 — Modelo de confianza JWT

Estado: Propuesto (`PROPOSED`)

## Contexto

Auth emite JWT humanos con el par Simple JWT y JWT de service account con signing keys administradas. JWKS publica solo la segunda familia.

## Decisión propuesta

Formalizar emisores, audiencias, claims, distribución/rotación de claves y consumidores autorizados por familia. Ningún consumidor debe asumir que JWKS valida automáticamente tokens humanos.

## Trabajo pendiente

- Inventario de consumidores.
- Estrategia de rotación con grace period.
- Runbook de pérdida/compromiso.
- Tests criptográficos end-to-end.
- Decisión sobre revocación/introspection por tipo de token.
