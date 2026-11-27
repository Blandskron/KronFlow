# GitHub Copilot Instructions — KronFlow

Sigue el protocolo canónico del repositorio en [`AGENTS.md`](../AGENTS.md) y las skills especializadas en `.agents/skills/`.

Reglas rápidas:
- Respeta aislamiento multi-tenant (`schema_translate_map`, nunca `schema_name` desde clientes) y las 3 fronteras de autenticación (`JWT RS256`, `X-Tenant-Code` + `X-Ingest-Key`, `X-Internal-Token`).
- Mantén Angular 21 Zoneless (`OnPush`, standalone, `HttpClient` + interceptor).
- No leas ni modifiques `.env`, claves privadas PEM ni credenciales reales.
- No crees carpetas `docs/` adicionales por microservicio ni archivos de Railway; actualiza únicamente el `README.md` del módulo afectado o la documentación raíz.
