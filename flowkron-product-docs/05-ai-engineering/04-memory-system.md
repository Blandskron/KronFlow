# Memoria de agentes

Versión: 1.2
Tipo: estado actual + objetivo
Estado: `PARTIAL`
Última verificación técnica: 2026-07-23

## Estado actual

- Operational persiste conversaciones, mensajes, leads y contexto documental por tenant.
- Agent Core tiene modelos locales de conversaciones/trazas para tests/modo local.
- En modo integrado, la memoria conversacional y trazas de Agent Core no tienen adapter Operational completo.
- No existe Redis de memoria LLM ni vector memory productiva.

## Tipos

| Tipo | Estado |
| --- | --- |
| Contexto efímero de request | `IMPLEMENTED` |
| Conversaciones operacionales | `IMPLEMENTED` como datos |
| Contexto documental tenant | `IMPLEMENTED` |
| Memoria Agent Core integrada | `PARTIAL` |
| Resúmenes automáticos | `NOT_IMPLEMENTED` |
| Memoria vectorial | `NOT_IMPLEMENTED` |

## Reglas

- Resolver tenant server-side.
- Separar hechos, inferencias y respuestas.
- Registrar fuente, fecha y versión.
- No almacenar secrets o PII innecesaria.
- Definir retención/TTL y borrado.
- Impedir recuperación cross-tenant.

