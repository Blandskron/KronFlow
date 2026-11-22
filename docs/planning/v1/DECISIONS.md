# Índice de decisiones Community v1

| Decisión | Estado y evidencia |
| --- | --- |
| Modularizar Campaigns y Analytics en Operational con worker separado del proceso HTTP | Propuesta. Medir contención, frescura y latencia antes de extraer. [ADR Community](02-architecture-adrs.md) |
| Mantener IAM como autoridad de identidad y Operational como fuente de recursos de negocio | Base observada, extensión para contactos y pipeline propuesta. [Arquitectura actual](../../../ARCHITECTURE.md) · [Límites objetivo](02-architecture-adrs.md#límites-y-flujo) |
| PostgreSQL para trabajos y transiciones durables, Redis para aceleración y cuotas | Patrón observado en turnos de WhatsApp, extensión propuesta a campañas y eventos. [Turnos activos](../../../flowkron-operational-service/docs/TURN_RECOVERY.md) · [ADR Community](02-architecture-adrs.md#persistencia-contratos-y-rollout) |
| Conservar contratos versionados y metadata tenant | Base observada. Las extensiones requieren esquemas por evento y prueba de compatibilidad. [ADR contrato](../../../flowkron-api-contracts/docs/decisions/ADR-0001-api-contracts-repository.md) · [ADR envelope](../../../flowkron-api-contracts/docs/decisions/ADR-0002-standard-json-response.md) · [ADR eventos](../../../flowkron-api-contracts/docs/decisions/ADR-0004-event-contracts.md) |
| Priorizar email habilitable y condicionar WhatsApp real | Propuesta de alcance. Usar stub en demo; autorización y pruebas por canal como gate. [Campañas](04-campaigns.md#alcance-v1-y-proveedores) |
| Evolucionar la instalación desde el source preview verificable | Base observada; preparación RC y estable pendiente de gates. [Estado de release](../../../RELEASE_READINESS.md) · [Alcance](FINAL_SCOPE.md) |
