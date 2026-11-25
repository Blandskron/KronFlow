# flowkron-agent-core

Nucleo conversacional omnicanal de Flowkron. Recibe eventos normalizados desde gateways externos, construye respuestas usando contexto empresarial por tenant y devuelve un contrato estandar sin depender de WhatsApp ni de otro canal especifico.

`flowkron-agent-core` no provisiona tenants, no crea schemas y no decide en que schema escribir. La resolucion de runtime, schema fisico e industria pertenece a `flowkron-operational-service`; este core opera con contratos transversales y delega persistencia/RAG por API interna.

## Por que existe

Los canales solo deben recibir, normalizar y entregar mensajes. La inteligencia conversacional, reglas, RAG, trazabilidad y preparacion de acciones viven aqui para que un mismo agente empresarial pueda operar en WhatsApp, Instagram, Facebook, TikTok, webchat, email, voz u otros adaptadores.

## Ejecucion local

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```

El proyecto mantiene `pyproject.toml` para metadata y configuracion moderna de tooling, pero usa `requirements.txt`/`requirements-dev.txt` como contrato de instalacion para alinearse con `flowkron-auth-service` y `flowkron-operational-service`.

La estructura sigue el mapa FastAPI comun de Flowkron: `app/main.py`, `app/core`, `app/api/v1`, `app/schemas`, `app/services`, `app/models` y `docs`. Las carpetas `app/application`, `app/domain` y `app/infrastructure` son la extension intencional para runtime IA, puertos, RAG y adapters externos.

El modo por defecto es integrado: `PERSISTENCE_MODE=operational`, `ALLOW_LOCAL_DB_BOOTSTRAP=false`. En ese modo el servicio no crea tablas ni schemas; los endpoints de documentos, status y retrieval delegan en Operational. Para tests aislados se usa `PERSISTENCE_MODE=local`.

Endpoints de salud:

- `GET /health`
- `GET /ready`

## Variables de entorno

- `PERSISTENCE_MODE`: por defecto `operational`; delega persistencia a Operational.
- `ALLOW_LOCAL_DB_BOOTSTRAP`: por defecto `false`; solo tests/desarrollo aislado pueden crear tablas locales.
- `OPERATIONAL_SERVICE_URL`: URL interna del operational service.
- `INTERNAL_TOKEN`: token compartido para llamar endpoints internos de Operational.
- `DATABASE_URL`: solo para modo local/test, no para provisionamiento productivo.
- `DATABASE_SCHEMA`: metadata local; Operational decide schemas reales.
- `JWT_PUBLIC_KEY` o `JWT_PUBLIC_KEY_PATH`: clave publica RS256 emitida por `flowkron-auth-service`.
- `JWT_AUDIENCE`: por defecto `flowkron`.
- `JWT_ISSUER`: por defecto `flowkron-auth-service`.
- `ALLOW_INSECURE_TENANT_HEADER`: solo local, permite `X-Tenant-Id`.
- `MAX_UPLOAD_BYTES`, `ALLOWED_UPLOAD_EXTENSIONS`, `LOW_CONFIDENCE_THRESHOLD`.
- `CORS_ALLOWED_ORIGINS`: lista JSON o separada por comas.
- `GROQ_API_KEY`, `GROQ_MODEL` y `CHAT_PROVIDER`: habilitan y seleccionan el chat.

## Endpoints principales

- `POST /api/v1/agent/messages`: endpoint universal para canales.
- `POST /api/v1/agent/simulate`: simulacion interna del agente.
- `GET /api/v1/context/status`: estado agregado de progreso, agente, documentos activos y acciones permitidas.
- `GET /api/v1/context/documents`: documentos cargados del tenant, leidos desde Operational.
- `POST /api/v1/context/documents/upload-file`: carga multipart de plantillas completadas; extrae texto y delega chunks a Operational.
- `POST /api/v1/context/documents/upload`: carga JSON de texto ya extraido; uso tecnico.
- `GET /api/v1/context/documents/{document_id}`, `PATCH /api/v1/context/documents/{document_id}`, `DELETE /api/v1/context/documents/{document_id}`: disponibles solo en modo local; en modo operacional responden `501`.
- `GET /api/v1/context/templates`: catalogo de plantillas base con opciones Word/PDF.
- `GET /api/v1/context/templates/{template_id}`: metadata de una plantilla individual.
- `GET /api/v1/context/templates/{template_id}/download`: descarga individual de una plantilla.
- `GET /api/v1/context/forms`, `GET /api/v1/context/forms/{form_id}`, `GET /api/v1/context/forms/submissions`, `POST /api/v1/context/forms/{form_id}/submit`: flujo local de formularios base; en modo operacional responde `501`.
- `GET /api/v1/agent/conversations/{conversation_id}`: informacion base de una sesion; disponible solo en modo local/stateful.
- `GET /api/v1/agent/conversations/{conversation_id}/messages`: historial de mensajes de la sesion; disponible solo en modo local/stateful.
- `GET /api/v1/agent/conversations/{conversation_id}/traces`: trazas de recuperacion RAG; disponible solo en modo local/stateful.
- `GET /api/v1/agent/traces/{trace_id}`: detalles de una traza; disponible solo en modo local/stateful.
- `POST /api/v1/setup-chat/sessions`: asistente interactivo de onboarding/setup.
- `POST /api/v1/setup-chat/sessions/{session_id}/messages` y `POST /api/v1/setup-chat/sessions/{session_id}/generate-context`: flujo mock de setup pendiente de persistencia productiva.
- `GET|POST|PATCH|DELETE /api/v1/agent/rules`: administracion de reglas y directrices conversacionales; pendiente de adapter operacional para uso integrado.

Contrato runtime: `/openapi.json` en `agent-core` y fronteras de contrato consolidadas en [`ARCHITECTURE.md`](../../ARCHITECTURE.md).

## Flujo omnicanal

1. El gateway recibe un mensaje.
2. El gateway normaliza el evento y llama `/api/v1/agent/messages`.
3. El core valida tenant desde JWT y solicita contexto/RAG a Operational con `X-Internal-Token`.
4. Operational resuelve `TenantRuntime`, aplica `schema_translate_map` y devuelve fuentes del schema correcto.
5. El core devuelve respuesta, fuentes, confianza, acciones preparadas y proximo paso.

## Contexto empresarial

El flujo productivo soporta cinco plantillas base descargables en Word/PDF: perfil de empresa, productos/servicios, FAQ, reglas de atencion y politicas comerciales. El usuario descarga una plantilla, la completa y la sube por `upload-file`. Agent Core valida extension/tamano, extrae texto desde `.pdf`, `.docx`, `.csv`, `.txt` o `.md`, genera chunks de 900 caracteres con overlap de 120 y delega la persistencia a Operational.

Agent Core no guarda documentos, chunks ni embeddings en memoria en modo integrado. Si PostgreSQL no contiene documentos, `/api/v1/context/status` debe reportar cero documentos y el simulador no debe recuperar fuentes. El cliente interno de Operational desempaqueta respuestas estandar `ApiResponse` y entrega a FastAPI solo el campo `data`, de modo que los `response_model` de Agent Core validen contra `DocumentRead`, listas de documentos, status o fuentes. Operational es responsable de versionar cargas repetidas de un mismo `filename`.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest app\tests
```

Los tests activan `PERSISTENCE_MODE=local` y `ALLOW_LOCAL_DB_BOOTSTRAP=true` para validar el blueprint SQLAlchemy sin cambiar la regla productiva.

La suite actual cubre healthcheck, formularios locales, catalogo de plantillas Word/PDF, fallback al catalogo empaquetado, status real sin documentos sinteticos, carga JSON, extraccion DOCX en `upload-file`, respuesta contextual, handoff sin contexto, proteccion cross-tenant y desempaquetado del envelope estandar de Operational.

## Proveedores de chat

Groq usa `GROQ_API_KEY` y el modelo configurable `GROQ_MODEL`. En modo integrado, el agente genera respuestas con las fuentes obtenidas desde Operational y solicita traspaso si falla el proveedor. Consulta la [configuración de proveedores](docs/CONFIGURATION.md).

## Modelo de datos

Las tablas transversales de Agent Core deben ser creadas/provisionadas por Operational dentro del schema que corresponda al tenant/industria. Este repo conserva modelos SQLAlchemy para blueprint local y tests, pero no mantiene migraciones Alembic propias.

## Integracion con gateways

Los gateways deben enviar `Authorization: Bearer <jwt>` en entornos reales. En local puede usarse `X-Tenant-Id`. No deben ejecutar logica de negocio ni acciones externas: solo adaptan mensajes y entregan la respuesta del core al canal.
