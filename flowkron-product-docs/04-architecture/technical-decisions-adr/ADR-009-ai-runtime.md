# ADR-009 - Runtime y proveedores de IA

Estado: Propuesto (`PROPOSED`)

## Contexto

Agent Core ya ofrece una API conversacional, configuración de contexto y simulación. Operational gestiona datos, aislamiento y persistencia de los tenants. Un adaptador de canal externo puede normalizar los eventos y llamar a las APIs HTTP.

## Decisión pendiente

Definir la interfaz para proveedores de IA adicionales, la persistencia de memoria, las colas de trabajo, el registro de prompts y la ejecución de herramientas. Mantener la lógica de canal fuera del runtime conversacional.

## Criterios de aceptación

- Salidas estructuradas y contratos versionados.
- Límites por tenant y plan.
- Revisión humana para acciones críticas.
- Trazabilidad que proteja secretos y datos personales.
- Pruebas de evaluación y control de costes antes de habilitar automatizaciones en producción.
