# Selección de modelos

Versión: 1.1
Tipo: estado actual + objetivo
Estado: `PARTIAL`
Última verificación técnica: 2026-07-23

## Estado actual

- Agent Core contiene un adapter Azure OpenAI configurable.
- Las credenciales y deployment/model name se configuran externamente.
- No existe interfaz multi-provider completa, routing por tarea ni evaluación comparativa.
- Los tests no llaman proveedores reales.

## Criterios

- calidad por tarea;
- JSON schema/tool calling;
- latencia y disponibilidad;
- región y tratamiento de datos;
- límites/context window;
- costo;
- fallback;
- observabilidad;
- soporte de versión.

## Objetivo

Definir una interfaz provider-neutral y registrar provider, deployment/model, versión, parámetros, tareas permitidas y fallback. La selección debe basarse en evaluación reproducible y no en marcas hard-coded.

## Reglas

- Credenciales fuera de Git.
- Timeouts y retries acotados.
- Fallback seguro/handoff.
- Salida validada.
- Trazar versión sin registrar prompts sensibles completos.

