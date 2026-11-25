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
- `LOW_CONFIDENCE_THRESHOLD`: entre 0 y 1, por defecto 0,35. Se aplica a la puntuación léxica tanto en modo local como integrado. Una coincidencia por debajo del umbral prepara una derivación y omite el proveedor.

No usar:

- `DEMO_IN_MEMORY_CONTEXT_ENABLED`: no existe en `Settings`; la ruta in-memory de documentos empresariales fue retirada del modo integrado.

LLM y vector store:
- `CHAT_PROVIDER=auto`: selecciona Groq con clave disponible y permite usar `local` para trabajar sin llamadas externas.
- `GROQ_API_KEY` y `GROQ_MODEL`: clave del proveedor y modelo de chat. El modelo predeterminado es `openai/gpt-oss-20b`.
- `CHAT_INPUT_MAX_CHARS`: máximo de caracteres Unicode de la instrucción, la pregunta, los delimitadores y los extractos enviados al proveedor. Predeterminado 12000. La pregunta se conserva íntegra. Si el primer extracto no cabe, se prepara una derivación.
- `CHAT_COMPLETION_MAX_TOKENS`: máximo de tokens de salida solicitado al proveedor. Predeterminado 2000. Ambos límites deben ser positivos.
- `CHAT_COMPLETION_TEMPERATURE`, `CHAT_COMPLETION_TIMEOUT_SECONDS`.
- La recuperación de contexto es lexical y la persistencia integrada vive en Operational.

Dependencias:

- `requirements.txt`: dependencias runtime y Docker.
- `requirements-dev.txt`: runtime + tests.
- `pyproject.toml`: metadata del proyecto y configuracion de pytest/setuptools.
