# Arquitectura de servicios

Versión: 1.2
Tipo: estado actual
Estado: `PARTIAL`
Última verificación técnica: 2026-07-23

## Principio

Cada servicio posee su dominio y publica contratos. No comparte lógica interna ni permite que un consumidor decida el schema físico de datos.

## Mapa de ownership

| Dominio | Propietario |
| --- | --- |
| Identidad, tenant lógico, RBAC y sesión | Auth |
| Runtime y schema físico | Operational |
| CRM, conversaciones, ingest y analytics | Operational |
| Contexto empresarial persistente | Operational |
| Orquestación conversacional y extracción | Agent Core |
| Experiencia privada | App Angular |
| Experiencia pública | Landing Angular |
| Contratos compartidos | API Contracts |
| Integración local | Deploy |

## Comunicación síncrona actual

- App → Auth/Operational/Agent Core mediante HTTP y JWT.
- Landing → Auth mediante HTTP y CSRF.
- Auth → Operational mediante HTTP interno.
- Agent Core → Operational mediante HTTP interno.

No hay bus de eventos ni cola de jobs compartida implementada.

## Reglas

- Ningún frontend conoce `schema_name`.
- Auth no almacena datos CRM.
- Agent Core no provisiona tenants ni escribe directo a PostgreSQL en modo integrado.
- Operational resuelve tenant y aplica `schema_translate_map`.
- Un servicio saludable no implica que sus dependencias o flujos de negocio estén listos.

## Brechas

- Autorización granular en Operational.
- Contratos completos y auditoría endpoint a endpoint.
- Mensajería asíncrona, resiliencia y circuit breakers.
- Observabilidad distribuida.
