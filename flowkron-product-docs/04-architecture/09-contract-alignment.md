# Alineación con `flowkron-api-contracts`

Versión: 1.2
Tipo: alineación contractual
Estado: `PARTIAL`
Última verificación técnica: 2026-07-23

## Resumen

Auth, Operational y Agent Core poseen especificaciones compartidas y envelopes runtime. La adopción es parcial porque todavía faltan pruebas sistemáticas contrato-runtime-consumidor y el gateway WhatsApp no tiene paths publicados.

## Matriz

| Flujo | Productor | Consumidor | Estado |
| --- | --- | --- | --- |
| Contacto público | Auth | Landing | `aligned` |
| Identidad y tenant | Auth | App | `runtime-envelope` |
| Leads/conversaciones/analytics | Operational | App | `runtime-envelope` |
| Contexto y simulación | Agent Core | App | `runtime-envelope` |
| Provisioning | Operational | Auth | `runtime-envelope` |
| Contexto interno | Operational | Agent Core | `runtime-envelope` |
| Ingest HTTP | Operational | Gateway futuro | `missing-consumer` |

Los estados de alineación son específicos de contratos y no reemplazan los estados de implementación globales.

## Cierre de alineación

Un endpoint queda `aligned` cuando especificación, runtime, ejemplo, catálogo de errores, consumidor y prueba de contrato coinciden. El inventario detallado está en [13-contract-catalog.md](13-contract-catalog.md).
