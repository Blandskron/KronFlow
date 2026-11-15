# Config

Variables:

- `APP_NAME`: nombre FastAPI.
- `ENVIRONMENT`: `local`, `staging`, `production`.
- `DEBUG`: bandera de depuracion.
- `DATABASE_URL`: solo para modo `local`/tests; no se usa en stack integrado.
- `DATABASE_SCHEMA`: metadata local; el schema productivo lo resuelve Operational.
- `PERSISTENCE_MODE`: `operational` en stack integrado; `local` solo para tests/desarrollo aislado.
- `ALLOW_LOCAL_DB_BOOTSTRAP`: `false` por defecto; no crear tablas/schemas desde agent-core en integrado.
- `OPERATIONAL_SERVICE_URL`: servicio que resuelve runtime, schema físico y persistencia.
- `INTERNAL_TOKEN`: secreto compartido para llamadas internas a Operational.
- `CORS_ALLOWED_ORIGINS`: lista JSON o separada por comas.
- `JWT_PUBLIC_KEY`, `JWT_PUBLIC_KEY_PATH`.
- `JWT_ALGORITHM`, `JWT_AUDIENCE`, `JWT_ISSUER`.
- `ALLOW_INSECURE_TENANT_HEADER`: solo local.
- `MAX_UPLOAD_BYTES`.
- `ALLOWED_UPLOAD_EXTENSIONS`.
- `LOW_CONFIDENCE_THRESHOLD`.

No usar:

- `DEMO_IN_MEMORY_CONTEXT_ENABLED`: no existe en `Settings`; la ruta in-memory de documentos empresariales fue retirada del modo integrado.

LLM y vector store:
- `AZURE_OPENAI_ENABLED`: habilita Azure OpenAI.
- `AZURE_OPENAI_API_VERSION`: versión de la API de Azure OpenAI (ej. `2024-02-01`).
- `CHAT_COMPLETION_URL`, `CHAT_COMPLETION_MODEL_NAME`, `CHAT_COMPLETION_MAX_TOKENS`, `CHAT_COMPLETION_TEMPERATURE`, `CHAT_COMPLETION_TIMEOUT_SECONDS`.
- `EMBEDDING_URL`, `EMBEDDING_MODEL_NAME`, `EMBEDDING_TIMEOUT_SECONDS`.
- `AZURE_OPENAI_API_KEY`: secreto local, nunca versionar en `.env.example`.
- El MVP conserva retrieval lexical/local; embeddings quedan como adapter listo para vector store productiva.

Dependencias:

- `requirements.txt`: dependencias runtime y Docker.
- `requirements-dev.txt`: runtime + tests.
- `pyproject.toml`: metadata del proyecto y configuracion de pytest/setuptools.
