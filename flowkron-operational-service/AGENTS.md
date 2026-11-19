# AGENTS.md

Fuente única de instrucciones y contexto para asistentes de IA en `flowkron-operational-service`. `CLAUDE.md` y `GEMINI.md` son adaptadores mínimos.

## Propósito y límites

Servicio FastAPI de datos operacionales multi-tenant. Gestiona runtime público, schemas tenant, datos de concesionaria/WhatsApp, lectura de dashboard, ingesta y migración idempotente.

No asumas capacidades inexistentes:

- `app/tenant_models/operations.py`, `app/tenant_models/context.py` y `app/tenant_models/whatsapp_turn.py`, importados desde `app/tenant_models/__init__.py`, definen el esquema tenant activo. Los módulos `agent_profile.py`, `analytics_snapshot.py`, `conversation.py`, `handoff_request.py`, `lead.py`, `lead_event.py` y `message.py` son un modelo anterior no importado por el provisioning actual.
- Los endpoints `/api/v1/agents` no persisten agentes todavía.
- `require_permission()` existe, pero ningún router de negocio lo usa; hoy se valida JWT, tenant activo y plan pagado, no permisos RBAC por endpoint.
- El aislamiento usa `schema_translate_map`, no `SET search_path` en cada request.
- Alembic se reserva para tablas públicas, pero no hay archivos en `alembic/versions/`; startup usa `create_all` para el esquema público.
- Hay pruebas `unittest` de límites de seguridad, identidad de mensajes y recuperación de turnos. Las integraciones FK-01/FK-02 usan un cluster PostgreSQL temporal propio al configurar `FLOWKRON_TEST_POSTGRES_BIN`; FK-02 ejercita ASGI sin TestClient. Ver `docs/TESTING.md` para ejecución y limitaciones de dependencias.

## Mapa de código

| Ruta | Responsabilidad |
| --- | --- |
| `app/main.py` | App, CORS, routers, health y creación de tablas públicas |
| `app/core/` | Settings, DB, JWT/internal auth, tenant resolver y rate limit |
| `app/api/internal/` | Provisioning, estados, ingest key y migración masiva |
| `app/api/ingest/` | Ingesta WhatsApp autenticada por headers |
| `app/api/v1/` | Dashboard JWT: leads, conversaciones, analytics y datos operacionales |
| `app/public_models/` | `tenant_runtime`, `migration_registry`, `system_events`, `billing_reference` |
| `app/tenant_models/operations.py` | Tablas tenant activas |
| `app/services/` | Queries tenantizadas, ingesta y provisioning |
| `scripts/` | Herramientas operacionales, algunas destructivas sobre schemas temporales |

## Invariantes críticas

- Nunca construir un identificador SQL desde input sin `sanitize_schema_name` y validación/quoting apropiados.
- Toda query tenant activa debe usar `schema_translate_map` mediante helpers de `tenant_data.py` o bind equivalente.
- El `tenant_id` proviene del JWT validado; el runtime debe existir, estar `active` y tener plan distinto de `free`.
- Ingest exige tenant code/key válidos, runtime activo y plan pagado; la key se almacena PBKDF2-SHA256 con salt.
- `INTERNAL_TOKEN` protege todos los endpoints `/internal/*` y debe coincidir con auth service.
- La ingest key solo se devuelve al crear por primera vez o rotar. Reprovisionar un runtime existente no entrega una nueva.
- El cambio de modelos tenant debe considerar todos los schemas existentes y actualizar `TENANT_MIGRATION_VERSION` cuando corresponda.

## Seguridad y deudas conocidas

- Defaults locales de DB/internal token no son seguros para ambientes compartidos.
- Rate limiting de ingest vive en un diccionario por proceso: múltiples workers multiplican el límite y un reinicio lo resetea.
- No hay autorización RBAC específica en routers JWT.
- `readyz` puede devolver 500 si DB falla.
- CORS permite credenciales, todos los métodos y headers para los orígenes configurados.
- `system_events.payload` puede contener identificadores/error DB; no registrar payloads WhatsApp completos ni PII innecesaria.
- Los scripts `validate_*` ejecutan `DROP SCHEMA ... CASCADE` sobre nombres temporales fijos: requieren base de prueba autorizada.

## Configuración

No leas `.env`. Fuentes canónicas: `.env.example` y `app/core/config.py`. Variables: `APP_NAME`, `ENVIRONMENT`, `DEBUG`, `DATABASE_URL`, `DATABASE_SCHEMA`, `DATABASE_GRANT_ROLE`, `CORS_ALLOWED_ORIGINS`, `INTERNAL_TOKEN`, `JWT_PUBLIC_KEY`, `JWT_PUBLIC_KEY_PATH`, `JWT_ALGORITHM`, `JWT_AUDIENCE`, `JWT_ISSUER`, `DEFAULT_PAGE_SIZE`, `MAX_PAGE_SIZE`, `TENANT_MIGRATION_VERSION`, `INGEST_RATE_LIMIT_PER_MINUTE`; `OPERATIONAL_PORT` solo parametriza Compose.

## Autorización del agente

Permitido dentro del alcance: leer código/docs, editar aplicación/documentación, añadir pruebas y ejecutar verificaciones locales no destructivas.

Requiere aprobación humana: dependencias, CI/CD, Docker/infraestructura, migraciones, contratos incompatibles, tenant resolver/schema mapping, autenticación/autorización, scripts destructivos, ejecución contra DB compartida/productiva y despliegues.

No leer ni modificar `.env`, llaves, tokens, datos reales, workflows ni migraciones existentes. No ejecutes scripts de provisioning/migración/validación sin confirmar que la DB es descartable y está en alcance.

## Validación proporcional

```powershell
python -m compileall -q app scripts
```

- Solo docs: enlaces relativos, referencias obsoletas, fences y `git diff --check`.
- Python: compileall e import de `app.main`; luego validaciones DB/API en entorno descartable si el alcance lo autoriza.
- API: revisar `/openapi.json` y probar credencial/tenant/schema además del happy path.
- Modelos/migraciones: validar schema temporal, migración de todos los tenants y rollback operativo; estos comandos escriben DB.
- Docker: `docker compose config` puede materializar variables sensibles; evita mostrar su salida.

Reporta únicamente las pruebas ejecutadas y distingue skips o fallos de importación; no infieras aprobación de toda la suite a partir de una ejecución parcial.

## Documentos canónicos

- [Índice](docs/README.md)
- [Arquitectura](docs/ARCHITECTURE.md)
- [API](docs/API.md)
- [Datos](docs/DATA_MODEL.md)
- [Seguridad](docs/SECURITY.md)
- [Configuración](docs/CONFIGURATION.md)
- [Operación](docs/OPERATIONS.md)
- [Testing](docs/TESTING.md)

## Definición de terminado

El diff respeta el alcance, no expone secretos, mantiene aislamiento tenant, documenta límites reales y pasa las validaciones disponibles. Reporta cualquier validación no ejecutada sin asumir éxito.
