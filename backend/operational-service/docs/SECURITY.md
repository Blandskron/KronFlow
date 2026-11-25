# Seguridad

## Canales de autenticación

| Canal | Control |
| --- | --- |
| Dashboard | Bearer JWT RS256 validado con clave pública, algoritmo permitido, audience, issuer y expiración |
| Ingest WhatsApp | `X-Tenant-Code` + `X-Ingest-Key`; PBKDF2-SHA256 con salt y comparación constante |
| Endpoints internos | `X-Internal-Token` con `hmac.compare_digest` |

JWT debe incluir `tenant_id`. Los roles/permisos se extraen, pero actualmente los routers no llaman `require_permission`; el control efectivo es identidad válida + runtime activo + plan pagado.

## Aislamiento tenant

El runtime se busca por tenant ID/code en schema público. Las queries usan SQLAlchemy `schema_translate_map`; no confían en un schema enviado por el cliente. Provisioning normaliza slugs a `[a-z0-9_]`, agrega prefijo `tenant_`, limita a 63 caracteres y resuelve colisiones.

La función `quote_identifier` existe, pero provisioning construye SQL de vistas/triggers con `schema_name` persistido y comillas directas. La seguridad depende de que todo schema almacenado provenga de `sanitize_schema_name`; no permitas escrituras externas arbitrarias en `tenant_runtime.schema_name`.

## Secretos y datos

- No registrar `INTERNAL_TOKEN`, JWT, ingest keys ni `.env`.
- La ingest key en claro solo aparece al crear/rotar; DB conserva PBKDF2 con 180.000 iteraciones y salt.
- Entrega la clave de ingesta a cada adaptador externo mediante un secreto administrado por la instancia.
- Evitar PII y raw WhatsApp payloads en logs/system events. Hoy el evento de ingest guarda solo message ID; errores de provisioning pueden incluir texto DB.
- La clave JWT debe ser la correspondiente a tokens humanos de auth; el JWKS de service-account keys no es sustituto automático.

## Rate limiting

El límite de ingest usa `defaultdict(deque)` en memoria por tenant code. Limitaciones:

- cada proceso/replica tiene su contador;
- reinicios lo eliminan;
- no hay TTL global ni backend Redis;
- el diccionario retiene claves de tenant vistas durante la vida del proceso.

No debe considerarse protección distribuida suficiente para producción; complementa con gateway/WAF.

## Brechas explícitas

- Falta autorización por permiso/rol en dashboard.
- No hay suite automatizada de seguridad/cross-tenant.
- Defaults locales de DB/internal token son inseguros.
- `readyz` no captura fallos DB.
- Startup y endpoints internos tienen capacidad DDL amplia.
- OpenAPI/docs quedan públicos por defecto.
- CORS permite credenciales y cualquier método/header para los orígenes configurados.
- No hay logging/correlation middleware estructurado en este repositorio.
- No hay rotación dual/grace period para ingest key: la anterior deja de validar inmediatamente.

## Producción

Usa secrets manager, red privada, TLS, usuario DB de mínimo privilegio, gateway con rate limits/RBAC, restricción de `/internal`, `/docs` y `/openapi.json`, backups/restore probados y monitoreo de eventos/errores. Ver [OPERATIONS.md](OPERATIONS.md).
