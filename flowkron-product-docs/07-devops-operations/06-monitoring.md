# Monitoreo

**Versión:** 1.0
**Tipo:** `NOT_IMPLEMENTED`
**Última verificación:** 2026-06-22

Los health checks de Docker comprueban que cada proceso responde, pero no constituyen una plataforma de monitoreo. No se encontraron Prometheus, Grafana, OpenTelemetry, Sentry, APM, agregación de métricas, dashboards ni alertas.

## Cobertura objetivo

- disponibilidad y latencia de IAM y operacional;
- errores HTTP, autenticación fallida y throttling;
- conexiones, capacidad y errores de PostgreSQL/Redis;
- salud y consumo de contenedores;
- métricas del frontend y errores del navegador;
- tiempos y fallos del aprovisionamiento de tenants;
- cuando exista IA: latencia, errores, tokens, costo y calidad.

La selección de herramientas y umbrales permanece pendiente. Un control se considera implementado solo cuando genera una señal consultable y una alerta probada.
