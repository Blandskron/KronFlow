# Datos, contratos y seguridad

## 1. Propiedad de datos

### Auth: base IAM compartida

Auth mantiene usuarios, perfiles, tenants, memberships, invitaciones, roles, permisos, sesiones, signing keys, service accounts, API keys, tokens de seguridad, auditoría y la proyección del runtime operacional.

La separación tenant en Auth se aplica por relaciones y filtros de aplicación. Auth no usa un schema PostgreSQL por empresa.

### Operational: schema público

El schema público mantiene metadatos que permiten resolver un tenant:

- runtime y schema físico;
- registro lógico de migraciones;
- eventos de sistema;
- referencias de billing.

### Operational: schema por tenant

Los modelos activos cubren operación automotriz/WhatsApp y contexto empresarial:

- clientes, leads, conversaciones, mensajes e inventario;
- consentimiento, solicitudes de derechos, dashboard y asignación;
- reglas comerciales y rate limiting;
- documentos de contexto, chunks, embeddings futuros, formularios y perfil del agente.

Los módulos tenant legacy no importados no deben considerarse tablas productivas.

### Agent Core

En el stack integrado, Agent Core no es propietario del DDL productivo. Sus modelos locales existen para desarrollo y tests; Operational mantiene las tablas tenant y resuelve el schema.

## 2. Regla de aislamiento multi-tenant

1. La identidad externa aporta un tenant lógico, nunca un schema físico.
2. Operational valida JWT o credencial de ingestión.
3. Operational obtiene `TenantRuntime`.
4. Exige runtime activo y plan permitido.
5. Aplica `schema_translate_map={"tenant": runtime.schema_name}`.
6. Ejecuta consultas con helpers tenant-aware.

Riesgo principal: una resolución incorrecta puede exponer datos entre empresas. Cambios en tenant resolver, schema mapping o modelos activos requieren revisión de seguridad, migración y tests cross-tenant.

## 3. Contratos HTTP

La fuente transversal es [flowkron-api-contracts](../../flowkron-api-contracts/README.md).

| Especificación | Versión documentada | Cobertura |
| --- | --- | --- |
| Auth | v0.5.0 | Identidad, tenants, RBAC, seguridad, sesiones, audit y contacto |
| Operational | v0.3.1 | Dashboard, ingest, agentes e interfaces internas |
| Agent Core | v0.3.1 | Mensajes, contexto, plantillas, setup, reglas y trazas |
| WhatsApp Gateway | v0.2.0 | Sin paths operativos publicados |

Los servicios usan contratos de éxito `ApiResponse` y error `ApiError`/problem details. Un cambio de método, path, slash final, auth, header, status, payload, paginación o evento puede ser breaking.

## 4. Trazabilidad

- La App genera `X-Correlation-ID`.
- Auth y los servicios FastAPI preservan metadata de request/correlación en responses JSON.
- Auth escribe eventos IAM sensibles de manera síncrona.
- No existe tracing distribuido, pipeline centralizado ni garantía de inmutabilidad de auditoría.

## 5. Controles implementados

| Control | Estado |
| --- | --- |
| Contraseñas Django, recuperación y verificación | `IMPLEMENTED` |
| JWT RS256 entre servicios | `IMPLEMENTED` |
| MFA TOTP backend | `IMPLEMENTED` con UI parcial |
| RBAC y entitlements en Auth | `IMPLEMENTED` |
| Aislamiento schema-per-tenant en Operational | `IMPLEMENTED` |
| Hash de API keys, client secrets e ingest key | `IMPLEMENTED` |
| CSRF en formulario público | `IMPLEMENTED` |
| Correlation/request IDs | `PARTIAL` |
| Consentimiento y derechos en workflow WhatsApp | `PARTIAL` y dependiente del workflow |
| Autorización RBAC granular Operational | `NOT_IMPLEMENTED` |
| Rate limit distribuido de ingest | `NOT_IMPLEMENTED` |
| Secret manager, WAF, TLS global y headers completos | `NOT_IMPLEMENTED` |
| SAST/DAST/secret scan/dependency scan automatizado | `NOT_IMPLEMENTED` |
| Monitoreo, alertas y respuesta automatizada | `NOT_IMPLEMENTED` |

## 6. Riesgos de seguridad conocidos

- Tokens frontend permanecen en `localStorage`; XSS tendría impacto alto.
- Operational autentica y valida tenant/plan, pero no aplica permisos finos por router.
- Rate limit de ingest se mantiene por proceso.
- Los puertos del stack local se publican al host.
- La rotación de claves posee dos familias en Auth; JWKS administrativo no representa automáticamente la clave de Simple JWT.
- Cambiar `SIGNING_KEY_ENCRYPTION_KEY` puede volver ilegibles claves privadas almacenadas.
- Healthchecks superficiales pueden reportar vida sin probar DB, SMTP, claves o flujos.

## 7. Requisitos técnicos de privacidad

- Minimizar PII en modelos, logs, traces, prompts y ejemplos.
- Aislar datos por tenant y probar accesos negativos.
- Evitar payloads completos de WhatsApp en logs.
- Implementar borrado/exportación mediante operaciones tenant-aware.
- Definir retención como configuración aplicable y auditable.
- Cifrar tránsito, backups y secretos.
- Registrar acceso administrativo y acciones sensibles.
- Anonimizar fixtures y entornos de desarrollo.

## 8. Manejo de secretos

Los secretos se suministran externamente. Nunca deben copiarse a esta documentación:

- passwords y URLs de base de datos;
- `INTERNAL_TOKEN`;
- claves JWT;
- secretos de service accounts y API keys;
- ingest keys;
- tokens Meta, Groq o Google;
- datos reales de usuarios o conversaciones.

La referencia permitida es `.env.example` de cada repositorio, no `.env`.
