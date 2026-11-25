# Testing

Pruebas unitarias/integracion local:

```powershell
.\.venv\Scripts\python.exe -m pytest app\tests
```

Los tests activan `PERSISTENCE_MODE=local` y `ALLOW_LOCAL_DB_BOOTSTRAP=true` para validar el blueprint SQLAlchemy sin alterar la regla productiva.

Validaciones recomendadas antes de integrar:

- `pytest app\tests` en `flowkron-agent-core`.
- `npm run build` en `flowkron-front-app-angular`.
- `docker compose config --quiet` en `flowkron-deploy`.

Cobertura actual de Agent Core:

- Healthcheck y envelope estandar.
- Formularios base y submissions en modo local.
- Catalogo de cinco plantillas con descargas Word/PDF.
- Fallback al catalogo empaquetado cuando no existe raiz externa de plantillas.
- Status de contexto sin documentos sinteticos.
- Carga JSON de documentos y carga multipart DOCX con extraccion de texto.
- Respuesta contextual con fuentes y handoff cuando no hay contexto.
- Validacion de tenant y bloqueo cross-tenant.
- Desempaquetado de respuestas `ApiResponse` desde Operational.
