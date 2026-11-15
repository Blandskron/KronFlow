# Telemetría y costos LLM

Versión: 1.1
Tipo: estado actual + objetivo
Estado: `NOT_IMPLEMENTED` para control de costos
Última verificación técnica: 2026-07-23


## Telemetría requerida

- tenant y request/correlation ID;
- tarea/agente;
- provider/model/deployment/version;
- tokens de entrada/salida/cache;
- latencia, retry y status;
- costo estimado con tabla versionada;
- fallback/handoff;
- sin prompt/PII innecesaria.

## Controles

- rate/concurrency limits;
- budgets por tenant/ambiente;
- alertas;
- reducción de contexto;
- caching validado;
- routing al modelo suficiente;
- circuit breaker;
- degradación segura.

## Criterio de implementación
