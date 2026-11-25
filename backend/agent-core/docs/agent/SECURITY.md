# Security

Riesgos principales:

- Fuga de datos entre tenants.
- Uso accidental de `X-Tenant-Id` fuera de local.
- Logs con PII o payloads completos.
- Documentos maliciosos o demasiado grandes.
- Acciones externas ejecutadas sin permiso.

JWT:

- Produccion debe usar `Authorization: Bearer` con JWT RS256.
- Validar `audience`, `issuer`, firma y `tenant_id`.
- `JWT_PUBLIC_KEY` o `JWT_PUBLIC_KEY_PATH` deben venir de secreto seguro.

Tenant isolation:

- Cada modelo operativo incluye `tenant_id`, pero el schema fisico lo resuelve operational.
- Las rutas rechazan payloads cuyo tenant no coincide con el contexto autenticado.
- Tests cubren proteccion cruzada basica.
- Agent core no debe recibir ni calcular `schema_name` desde requests externas.

Uploads:

- Validar extension y tamano antes de procesamiento avanzado.
- Sanitizar texto extraido.
- No persistir binarios peligrosos en este MVP.

Logs:

- No imprimir secretos, tokens, llaves ni payloads completos.
- Preferir IDs, conteos y trazas resumidas.

Acciones:

- Las acciones externas son preparadas, no ejecutadas.
- Integraciones reales requieren permisos, contrato y adapter dedicado.

Proveedores de IA:

- La API key solo debe vivir en `.env` local, secretos de despliegue o gestor de secretos.
- Groq recibe la pregunta y los extractos recuperados mediante HTTPS. La clave se lee del entorno y se oculta en las representaciones de configuración.
- No loguear prompts completos si contienen PII.
- Si el proveedor falla, responder con fallback seguro y handoff.
