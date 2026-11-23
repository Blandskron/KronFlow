# Catálogo y gobierno de contratos

Versión: 1.0
Tipo: Current State + gobierno
Estado: `PARTIAL`
Última verificación: 2026-11-23

`flowkron-api-contracts` es la fuente de verdad de interfaces compartidas. El código y la especificación OpenAPI del propietario prevalecen cuando esta matriz encuentre una discrepancia.

## Inventario de contratos publicados

| Productor | Artefacto | Cobertura observada | Consumidores conocidos | Estado |
| --- | --- | --- | --- | --- |
| Auth | `openapi/services/auth-service.openapi.yml` v0.5.0 | Auth, perfil, tokens, MFA, tenants, RBAC, sesiones, seguridad, audit y contacto | App privada, Landing, servicios internos | `PARTIAL` |
| Operational | [OpenAPI](../../flowkron-api-contracts/openapi/services/operational-service.openapi.yml) | Conversaciones, directorio y captación manual, leads, métricas, privacidad, contexto y conector interno | App, IAM, Agent Core y laboratorio WhatsApp | `PARTIAL` |
| Agent Core | `openapi/services/agent-core.openapi.yml` v0.3.1 | Mensajes universales, simulación, contexto, plantillas, setup, reglas y trazas | App privada, gateways futuros | `PARTIAL` |
| Compartido | `schemas/response`, `schemas/events`, `schemas/ai`, `schemas/jobs`, `schemas/webhooks` | Envelopes, errores, IA, eventos, jobs y webhooks reutilizables | Todos | `PARTIAL` por adopción runtime |

## Flujos y estado de adopción

| Flujo | Autenticación/headers | Estado | Hecho verificable | Trabajo pendiente |
| --- | --- | --- | --- | --- |
| Landing → Auth contacto | CSRF + cookie + `X-CSRFToken` | `aligned` | Landing obtiene CSRF y hace `POST /api/v1/contact/messages/`. El smoke integrado prueba el contacto institucional. | Ampliar escenarios de error y aceptación del candidato |
| App → Auth | Bearer JWT; tenant donde corresponde | `runtime-envelope` | Rutas y OpenAPI publicados | Auditar consumidores/códigos de error endpoint a endpoint |
| App → Operational | Bearer JWT y permiso por ruta. El interceptor añade `X-Tenant-ID` y el backend resuelve la empresa del JWT. | `runtime-envelope` | CRM, Bandeja, métricas y privacidad con pruebas sintéticas | Verificación E2E sobre el candidato |
| App → Agent Core | Bearer JWT + tenant | `runtime-envelope` | API de contexto/simulación publicada | Distinguir UI de rutas `501` locales |
| Auth → Operational | `X-Internal-Token` | `runtime-envelope` | Provisioning/runtime interno | Contrato de fallos/reintentos y pruebas de integración |
| Agent Core → Operational | `X-Internal-Token` | `runtime-envelope` | Documentos, status y retrieval internos | Persistencia integrada de resto de capacidades Agent Core |

## Reglas de compatibilidad

Un cambio de path, slash final, método, status, header, autenticación, payload, envelope o evento es un cambio contractual. Antes de integrarlo:

1. Actualice OpenAPI/JSON Schema, ejemplos y catálogo de errores en `flowkron-api-contracts`.
2. Identifique productor, consumidores y estado de compatibilidad.
3. Evalúe breaking change según [VERSIONING](../../flowkron-api-contracts/VERSIONING.md) y anótelo en el changelog si corresponde.
4. Actualice el runtime propietario y ejecute las validaciones disponibles.
5. Actualice los consumidores y esta documentación transversal.
