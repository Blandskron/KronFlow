# Tests

Estrategia:

- Tests API con `TestClient`.
- SQLite local descartable.
- `PERSISTENCE_MODE=local` y `ALLOW_LOCAL_DB_BOOTSTRAP=true` solo durante la suite.
- Verificar tenant isolation, health, formularios, documentos, runtime y RAG mock.

Ejecutar:

```powershell
.\.venv\Scripts\python.exe -m pytest app\tests
```

Casos existentes:

- Healthcheck.
- Listado/creacion de formularios base y submission.
- Catalogo de plantillas base y descarga Word/PDF.
- Fallback al catalogo empaquetado.
- Carga de documento JSON.
- Carga DOCX multipart con extraccion de texto.
- Endpoint universal con contexto simulado.
- Endpoint universal sin contexto.
- Validacion de tenant y bloqueo de acceso cruzado.
- Desempaquetado del envelope estandar de Operational.

Agregar nuevos tests:

- Crear datos para dos tenants.
- Afirmar que toda lectura filtra por tenant.
- Cubrir permisos antes de habilitar acciones reales.
