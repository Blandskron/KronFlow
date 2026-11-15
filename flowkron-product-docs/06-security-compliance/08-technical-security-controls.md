# Controles técnicos de seguridad

Versión: 1.1
Tipo: matriz técnica
Última verificación: 2026-07-23

| Control | Estado | Evidencia |
| --- | --- | --- |
| JWT RS256 | `IMPLEMENTED` | Auth emite; Operational/Agent Core validan |
| Tenant membership y RBAC Auth | `IMPLEMENTED` | Permisos y entitlements |
| Schema por tenant | `IMPLEMENTED` | Operational + `schema_translate_map` |
| Autorización granular Operational | `NOT_IMPLEMENTED` | `require_permission` no usado por routers |
| Hash de secrets/API/ingest keys | `IMPLEMENTED` | Modelos/servicios propietarios |
| MFA backend | `IMPLEMENTED` | TOTP y recovery codes |
| CSRF contacto | `IMPLEMENTED` | Landing + Auth |
| Correlation IDs | `PARTIAL` | App/backends |
| Rate limit ingest distribuido | `NOT_IMPLEMENTED` | Estado en memoria por proceso |
| Secret manager | `NOT_IMPLEMENTED` | Variables/archivos locales |
| TLS/WAF/proxy global | `NOT_IMPLEMENTED` | Sin infraestructura productiva |
| SAST/DAST/secret scan | `NOT_IMPLEMENTED` | Sin CI/CD |
| Backups/restore | `NOT_IMPLEMENTED` | Sin jobs ni evidencia |
| Observabilidad/alertas | `NOT_IMPLEMENTED` | Sin stack |

## Reglas para desarrollo

- No registrar tokens, passwords, MFA, secrets ni payloads personales completos.
- No aceptar `schema_name` desde clientes externos.
- Mantener JWT, tenant y permisos como validaciones backend.
- Tratar cambios de auth, tenant resolver y migraciones como alto riesgo.
- Probar accesos cross-tenant y casos negativos.
- Usar `.env.example`; nunca documentar `.env`.

Esta carpeta documenta controles técnicos observables, no declaraciones legales o certificaciones.
