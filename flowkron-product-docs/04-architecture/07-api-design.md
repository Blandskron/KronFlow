# Diseño y gobierno de APIs

Versión: 1.2
Tipo: estado actual + gobierno contractual
Estado: `PARTIAL`
Última verificación técnica: 2026-07-23

## Fuente de verdad

[`flowkron-api-contracts`](../../flowkron-api-contracts/README.md) centraliza OpenAPI, JSON Schema, errores, ejemplos y versionado. Auth, Operational y Agent Core tienen especificaciones versionadas. WhatsApp Gateway aún no publica paths operativos.

## Convenciones

- Prefijo público: `/api/v1`.
- Django utiliza slash final; FastAPI normalmente no.
- Éxito JSON: `ApiResponse<T>`.
- Error JSON: `ApiError` compatible con problem details.
- Correlación: `X-Correlation-ID` y `X-Request-ID`/metadata de respuesta.
- Los consumidores no envían `schema_name`.

## Autenticación por interfaz

| Interfaz | Mecanismo |
| --- | --- |
| App → APIs | Bearer JWT RS256 y tenant lógico |
| Landing → contacto | Cookie CSRF y `X-CSRFToken` |
| Auth/Agent Core → Operational | `X-Internal-Token` |
| Gateway → Operational ingest | `X-Tenant-Code` + `X-Ingest-Key` |


## Familias de endpoints

- Auth: identidad, perfil, tokens, MFA, tenants, memberships, RBAC, sesiones, seguridad, audit y contacto.
- Operational: leads, conversaciones, analytics, colecciones operacionales, ingest, stubs de agentes e interfaces internas de tenant/contexto.
- Agent Core: mensajes, simulación, contexto, documentos, plantillas, setup, reglas y trazas.

## Compatibilidad

Se considera contractual cualquier cambio de:

- método o path;
- slash final;
- auth/header;
- status HTTP;
- request/response;
- paginación;
- error code;
- evento o webhook.

El cambio debe actualizar contrato, ejemplos, errores, productor, consumidores, tests y changelog. Consulte el [catálogo de contratos](13-contract-catalog.md).
