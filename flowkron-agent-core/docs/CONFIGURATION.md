# Configuration

El runtime usa `requirements.txt` para instalacion y Docker, igual que `flowkron-auth-service` y `flowkron-operational-service`. `pyproject.toml` se conserva para metadata y tooling moderno; las dependencias no se duplican alli.

Variables principales:

- `PERSISTENCE_MODE=operational`: modo integrado por defecto.
- `ALLOW_LOCAL_DB_BOOTSTRAP=false`: evita crear tablas en ejecucion integrada.
- `OPERATIONAL_SERVICE_URL`: endpoint interno de Operational.
- `INTERNAL_TOKEN`: credencial servicio-a-servicio para `/internal/*` de Operational.
- `DATABASE_URL`: solo para modo local/test.
- `DATABASE_SCHEMA`: metadata local; no define schemas productivos.
- `ALLOW_INSECURE_TENANT_HEADER`: solo desarrollo.
- `CORS_ALLOWED_ORIGINS`: lista JSON o separada por comas.
- `JWT_PUBLIC_KEY`, `JWT_PUBLIC_KEY_PATH`, `JWT_ALGORITHM`, `JWT_AUDIENCE`, `JWT_ISSUER`: validacion de identidad emitida por Auth.
- `MAX_UPLOAD_BYTES`: limite de carga, por defecto `5242880`.
- `ALLOWED_UPLOAD_EXTENSIONS`: por defecto `.pdf`, `.docx`, `.csv`, `.xlsx`, `.txt`, `.md`; el extractor implementado lee texto desde `.pdf`, `.docx`, `.csv`, `.txt` y `.md`.
- `LOW_CONFIDENCE_THRESHOLD`: umbral para handoff/fallback.
- `CHAT_PROVIDER=auto`: usa Groq cuando hay clave y el contexto local cuando falta. Usa `CHAT_PROVIDER=local` para trabajar sin llamadas al proveedor.
- `GROQ_API_KEY`: secreto de Groq. `GROQ_MODEL`: identificador de modelo, con `openai/gpt-oss-20b` por defecto.
- `CHAT_COMPLETION_MAX_TOKENS`, `CHAT_COMPLETION_TEMPERATURE`, `CHAT_COMPLETION_TIMEOUT_SECONDS`: chat completion.

Los `.env` reales son locales y no deben commitearse. Los ejemplos deben usar placeholders. No reintroducir flags de persistencia in-memory para documentos empresariales; `DEMO_IN_MEMORY_CONTEXT_ENABLED` no existe en `Settings` y no debe volver al ejemplo.
